from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from maestro_fetch.daemon.server import STATE_KEY, build_app


class _RoundTripWS:
    def __init__(self, state) -> None:
        self.closed = False
        self._state = state

    async def send_str(self, payload: str) -> None:
        message = json.loads(payload)
        future = self._state.pending[message["id"]]
        future.set_result(
            {
                "id": message["id"],
                "ok": True,
                "data": {"action": message["action"]},
            }
        )


@pytest.mark.asyncio
async def test_health_and_status_endpoints() -> None:
    app = build_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        health = await client.get("/health")
        assert await health.json() == {"ok": True, "service": "mfetch-daemon"}

        status = await client.get("/status")
        assert await status.json() == {"ok": True, "extension": False, "pending": 0}
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_command_requires_connected_extension() -> None:
    app = build_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.post("/command", json={"id": "abc", "action": "tabs"})
        assert resp.status == 503
        payload = await resp.json()
        assert payload["ok"] is False
        assert "not connected" in payload["error"].lower()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_command_roundtrip_with_connected_extension() -> None:
    app = build_app()
    state = app[STATE_KEY]
    state.extension_ws = _RoundTripWS(state)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.post("/command", json={"id": "abc", "action": "tabs"})
        assert resp.status == 200
        payload = await resp.json()
        assert payload["ok"] is True
        assert payload["data"] == {"action": "tabs"}
    finally:
        await client.close()
