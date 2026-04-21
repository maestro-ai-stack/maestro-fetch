from __future__ import annotations

import argparse
import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from aiohttp import WSMsgType, web

log = logging.getLogger(__name__)


@dataclass
class DaemonState:
    """Shared state between HTTP handlers and the extension websocket."""

    extension_ws: web.WebSocketResponse | None = None
    pending: dict[str, asyncio.Future[Any]] = field(default_factory=dict)

    @property
    def extension_connected(self) -> bool:
        ws = self.extension_ws
        return ws is not None and not ws.closed


async def _json_response(data: dict[str, Any], *, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


async def health(_request: web.Request) -> web.Response:
    return await _json_response({"ok": True, "service": "mfetch-daemon"})


async def status(request: web.Request) -> web.Response:
    state: DaemonState = request.app["state"]
    return await _json_response(
        {
            "ok": True,
            "extension": state.extension_connected,
            "pending": len(state.pending),
        }
    )


async def command(request: web.Request) -> web.Response:
    state: DaemonState = request.app["state"]
    if not state.extension_connected:
        return await _json_response(
            {"ok": False, "error": "Extension is not connected"},
            status=503,
        )

    payload = await request.json()
    command_id = str(payload.get("id") or "")
    if not command_id:
        return await _json_response(
            {"ok": False, "error": "Command must include an id"},
            status=400,
        )

    loop = asyncio.get_running_loop()
    future: asyncio.Future[Any] = loop.create_future()
    state.pending[command_id] = future

    try:
        assert state.extension_ws is not None
        await state.extension_ws.send_str(json.dumps(payload))
        result = await asyncio.wait_for(future, timeout=180.0)
    except asyncio.TimeoutError:
        state.pending.pop(command_id, None)
        return await _json_response(
            {"ok": False, "error": f"Command timed out: {command_id}"},
            status=504,
        )
    except Exception as exc:  # noqa: BLE001
        state.pending.pop(command_id, None)
        return await _json_response(
            {"ok": False, "error": str(exc)},
            status=500,
        )

    return await _json_response(result)


async def extension_ws(request: web.Request) -> web.StreamResponse:
    state: DaemonState = request.app["state"]
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    previous = state.extension_ws
    if previous is not None and not previous.closed:
        await previous.close(code=1000, message=b"superseded")
    state.extension_ws = ws
    log.info("Extension connected")

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                log.warning("Ignoring non-JSON websocket message")
                continue

            if payload.get("type") == "log":
                log_fn = log.info
                if payload.get("level") == "warn":
                    log_fn = log.warning
                elif payload.get("level") == "error":
                    log_fn = log.error
                log_fn("extension: %s", payload.get("msg", ""))
                continue

            message_id = str(payload.get("id") or "")
            future = state.pending.pop(message_id, None)
            if future is not None and not future.done():
                future.set_result(payload)
        elif msg.type == WSMsgType.ERROR:
            log.warning("Extension websocket error: %s", ws.exception())

    if state.extension_ws is ws:
        state.extension_ws = None
    for future in list(state.pending.values()):
        if not future.done():
            future.set_exception(RuntimeError("Extension disconnected"))
    state.pending.clear()
    log.info("Extension disconnected")
    return ws


def build_app() -> web.Application:
    app = web.Application()
    app["state"] = DaemonState()
    app.router.add_get("/health", health)
    app.router.add_get("/status", status)
    app.router.add_post("/command", command)
    app.router.add_get("/ext", extension_ws)
    return app


async def serve(*, host: str, port: int) -> None:
    app = build_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info("mfetch daemon listening on http://%s:%d", host, port)
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        await runner.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the mfetch browser daemon.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19825)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    with suppress(KeyboardInterrupt):
        asyncio.run(serve(host=args.host, port=args.port))
    return 0

