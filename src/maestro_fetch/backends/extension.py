"""Extension backend -- real Chrome via opencli daemon + Chrome extension.

Architecture:
    mfetch (Python)  --HTTP-->  daemon (port 19825)  --WebSocket-->  Chrome extension
                                                                        |
                                                                   chrome.debugger API
                                                                        |
                                                                   real browser tab

The daemon is an Axum HTTP+WS server bundled with opencli-rs.
The Chrome extension uses chrome.debugger to control pages in a
dedicated automation window, isolated from the user's browsing.

Connection lifecycle (ported from opencli-rs bridge.rs):
    1. GET /health      -> daemon running?
    2. spawn daemon     -> opencli-rs --daemon --port {port}
    3. poll /health     -> wait 10s for daemon ready
    4. GET /status      -> extension connected?
    5. wake Chrome      -> open -a "Google Chrome" about:blank
    6. poll /status     -> wait 30s for extension

Protocol:
    POST /command  with X-OpenCLI header
    Body: {"id": uuid, "action": "navigate|exec|screenshot|tabs|cookies", ...}
    Response: {"id": uuid, "ok": bool, "data": ..., "error": ...}
"""
from __future__ import annotations

import asyncio
import base64
import logging
import platform
import re
import shutil
import subprocess
import uuid
from typing import Any

from maestro_fetch.core.errors import FetchError

log = logging.getLogger(__name__)

_DEFAULT_PORT = 19825
_READY_TIMEOUT = 10.0  # seconds
_READY_POLL_INTERVAL = 0.2
_EXTENSION_INITIAL_WAIT = 5.0
_EXTENSION_REMAINING_WAIT = 25.0
_EXTENSION_POLL_INTERVAL = 0.5
_COMMAND_TIMEOUT = 120.0
_RETRY_DELAYS = [0.2, 0.5, 1.0, 2.0]


class ExtensionBackend:
    """Browser backend via opencli Chrome extension + daemon.

    Uses the real Chrome browser with full auth/cookies/JS support.
    Requires: opencli-rs binary + Chrome extension installed.
    """

    name: str = "extension"

    def __init__(
        self,
        port: int = _DEFAULT_PORT,
        workspace: str = "mfetch",
        daemon_binary: str = "opencli-rs",
    ) -> None:
        self._port = port
        self._workspace = workspace
        self._daemon_binary = daemon_binary
        self._base_url = f"http://127.0.0.1:{port}"
        self._connected = False

    # -- HTTP helpers -------------------------------------------------------

    async def _http_get(self, path: str, timeout: float = 5.0) -> dict | None:
        """GET request to daemon. Returns parsed JSON or None on failure."""
        try:
            import httpx
        except ImportError:
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    f"{self._base_url}{path}",
                    headers={"X-OpenCLI": "1"},
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None

    async def _send_command(self, cmd: dict) -> Any:
        """POST /command with retry and exponential backoff."""
        try:
            import httpx
        except ImportError:
            raise FetchError("httpx is required for extension backend")

        url = f"{self._base_url}/command"
        last_err: str | None = None

        for attempt, delay in enumerate(_RETRY_DELAYS):
            try:
                async with httpx.AsyncClient(timeout=_COMMAND_TIMEOUT) as client:
                    resp = await client.post(
                        url,
                        headers={"X-OpenCLI": "1"},
                        json=cmd,
                    )

                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("ok"):
                        return result.get("data")
                    err_msg = result.get("error", "Unknown daemon error")
                    raise FetchError(f"Extension command failed: {err_msg}")

                if 400 <= resp.status_code < 500:
                    raise FetchError(
                        f"Extension command error (HTTP {resp.status_code}): "
                        f"{resp.text}"
                    )

                last_err = f"HTTP {resp.status_code}: {resp.text}"
            except FetchError:
                raise
            except Exception as e:
                last_err = str(e)

            if attempt < len(_RETRY_DELAYS) - 1:
                log.warning(
                    "Extension command retry %d/%d: %s",
                    attempt + 1, len(_RETRY_DELAYS), last_err,
                )
                await asyncio.sleep(delay)

        raise FetchError(
            f"Extension command failed after {len(_RETRY_DELAYS)} attempts: {last_err}"
        )

    def _make_command(self, action: str, **kwargs: Any) -> dict:
        """Build a daemon command with workspace."""
        cmd: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "action": action,
            "workspace": self._workspace,
        }
        for k, v in kwargs.items():
            if v is not None:
                # Convert snake_case to camelCase for protocol
                camel = re.sub(r"_([a-z])", lambda m: m.group(1).upper(), k)
                cmd[camel] = v
        return cmd

    # -- connection lifecycle -----------------------------------------------

    async def _is_daemon_running(self) -> bool:
        """Check if daemon is listening on the port."""
        try:
            import httpx
        except ImportError:
            return False
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            pass
        # Also check if something is listening (could be original opencli daemon)
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(
                    f"{self._base_url}/health",
                    headers={"X-OpenCLI": "1"},
                )
                return resp.status_code in (200, 403)
        except Exception:
            return False

    async def _is_extension_connected(self) -> bool:
        """Check if Chrome extension is connected to daemon."""
        result = await self._http_get("/status")
        if result is None:
            return False
        # opencli-rs format: {"extension": bool}
        # original opencli: {"extensionConnected": bool}
        return bool(
            result.get("extension") or result.get("extensionConnected")
        )

    async def _spawn_daemon(self) -> None:
        """Spawn daemon as a detached subprocess."""
        binary = shutil.which(self._daemon_binary)
        if binary is None:
            raise FetchError(
                f"Cannot find '{self._daemon_binary}' on PATH. "
                "Install opencli-rs or set daemon_binary in config."
            )

        log.info("Spawning daemon: %s --daemon --port %d", binary, self._port)
        subprocess.Popen(
            [binary, "--daemon", "--port", str(self._port)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    async def _wait_for_daemon(self) -> None:
        """Poll /health until daemon is ready (10s timeout)."""
        deadline = asyncio.get_event_loop().time() + _READY_TIMEOUT
        while asyncio.get_event_loop().time() < deadline:
            if await self._is_daemon_running():
                log.info("Daemon is ready on port %d", self._port)
                return
            await asyncio.sleep(_READY_POLL_INTERVAL)
        raise FetchError(
            f"Daemon did not become ready within {_READY_TIMEOUT}s"
        )

    @staticmethod
    def _is_chrome_running() -> bool:
        """Check if Chrome/Chromium is running."""
        system = platform.system()
        try:
            if system == "Darwin":
                return subprocess.run(
                    ["pgrep", "-x", "Google Chrome"],
                    capture_output=True,
                ).returncode == 0
            elif system == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                    capture_output=True, text=True,
                )
                return "chrome.exe" in result.stdout
            else:
                return subprocess.run(
                    ["pgrep", "-x", "chrome|chromium"],
                    capture_output=True,
                ).returncode == 0
        except Exception:
            return False

    @staticmethod
    def _wake_chrome() -> None:
        """Open a Chrome window to wake the extension Service Worker."""
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(
                    ["open", "-a", "Google Chrome", "about:blank"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif system == "Windows":
                subprocess.Popen(
                    ["cmd", "/C", "start", "chrome", "about:blank"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    ["xdg-open", "about:blank"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            log.info("Woke Chrome to activate extension")
        except Exception as e:
            log.warning("Failed to wake Chrome: %s", e)

    async def _ensure_connected(self) -> None:
        """Full connection lifecycle: daemon + extension."""
        if self._connected:
            # Quick re-check
            if await self._is_extension_connected():
                return
            self._connected = False

        # Step 1: Check Chrome
        if not self._is_chrome_running():
            raise FetchError(
                "Chrome is not running. Please open Google Chrome "
                "with the maestro-fetch extension installed."
            )

        # Step 2: Ensure daemon
        if not await self._is_daemon_running():
            await self._spawn_daemon()
            await self._wait_for_daemon()

        # Step 3: Wait for extension (5s initial)
        deadline = asyncio.get_event_loop().time() + _EXTENSION_INITIAL_WAIT
        while asyncio.get_event_loop().time() < deadline:
            if await self._is_extension_connected():
                self._connected = True
                log.info("Extension connected")
                return
            await asyncio.sleep(_EXTENSION_POLL_INTERVAL)

        # Step 4: Wake Chrome and wait remaining 25s
        log.info("Extension not connected, waking Chrome...")
        self._wake_chrome()

        deadline = asyncio.get_event_loop().time() + _EXTENSION_REMAINING_WAIT
        while asyncio.get_event_loop().time() < deadline:
            if await self._is_extension_connected():
                self._connected = True
                log.info("Extension connected after wake")
                return
            await asyncio.sleep(_EXTENSION_POLL_INTERVAL)

        raise FetchError(
            "Chrome extension not connected after 30s. "
            "Make sure the maestro-fetch extension is installed and enabled in Chrome."
        )

    # -- BrowserBackend protocol --------------------------------------------

    async def is_available(self) -> bool:
        """Check if extension backend can be used.

        Returns True if: httpx importable AND daemon reachable AND
        extension connected. Does NOT auto-spawn — that happens on
        first fetch_content() call.
        """
        try:
            import httpx as _httpx  # noqa: F401
            _ = _httpx
        except ImportError:
            return False

        # Quick check: if daemon is running and extension connected, we're good
        if await self._is_daemon_running() and await self._is_extension_connected():
            self._connected = True
            return True

        # Also available if we can find the daemon binary (will auto-spawn on use)
        if shutil.which(self._daemon_binary) is not None and self._is_chrome_running():
            return True

        return False

    async def fetch_content(self, url: str) -> str:
        """Fetch page content as markdown via Chrome extension.

        1. Navigate to URL in automation window
        2. Wait for page load
        3. Extract HTML via JS
        4. Convert to markdown
        """
        await self._ensure_connected()

        # Navigate
        nav_cmd = self._make_command("navigate", url=url)
        await self._send_command(nav_cmd)

        # Small delay for dynamic content
        await asyncio.sleep(1.0)

        # Extract HTML
        exec_cmd = self._make_command(
            "exec",
            code="document.documentElement.outerHTML",
        )
        html = await self._send_command(exec_cmd)

        if not html or not isinstance(html, str):
            # Try getting just text content
            exec_cmd = self._make_command(
                "exec",
                code="document.body.innerText",
            )
            text = await self._send_command(exec_cmd)
            return str(text) if text else ""

        # Convert HTML to markdown
        try:
            import html2text
            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.ignore_images = True
            converter.body_width = 0
            converter.skip_internal_links = True
            return converter.handle(html)
        except ImportError:
            # Fallback: strip tags
            text = re.sub(r"<[^>]+>", " ", html)
            return re.sub(r"\s+", " ", text).strip()

    async def fetch_screenshot(self, url: str) -> bytes:
        """Capture full-page screenshot as PNG bytes."""
        await self._ensure_connected()

        # Navigate first
        nav_cmd = self._make_command("navigate", url=url)
        await self._send_command(nav_cmd)
        await asyncio.sleep(1.0)

        # Screenshot
        ss_cmd = self._make_command(
            "screenshot",
            format="png",
            full_page=True,
        )
        result = await self._send_command(ss_cmd)

        if isinstance(result, str):
            return base64.b64decode(result)
        elif isinstance(result, dict) and "data" in result:
            return base64.b64decode(result["data"])
        raise FetchError("Unexpected screenshot result format")

    async def eval_js(self, js: str) -> Any:
        """Execute JavaScript in the current page context."""
        await self._ensure_connected()
        cmd = self._make_command("exec", code=js)
        return await self._send_command(cmd)

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Run a site-specific operation via JS execution."""
        await self._ensure_connected()

        parts = adapter_name.split("/", 1)
        site = parts[0]
        action = parts[1] if len(parts) > 1 else "default"

        # Navigate to site if URL provided in args
        if args:
            nav_cmd = self._make_command("navigate", url=args[0])
            await self._send_command(nav_cmd)
            await asyncio.sleep(1.0)

        # Execute site-specific JS
        exec_cmd = self._make_command(
            "exec",
            code=f"document.title + '\\n' + document.body.innerText",
        )
        result = await self._send_command(exec_cmd)
        return {"site": site, "action": action, "output": result}

    # -- Extra methods (beyond BrowserBackend protocol) ---------------------

    async def navigate(self, url: str) -> None:
        """Navigate to a URL without extracting content."""
        await self._ensure_connected()
        cmd = self._make_command("navigate", url=url)
        await self._send_command(cmd)

    async def get_cookies(self, domain: str | None = None) -> Any:
        """Get cookies from the browser."""
        await self._ensure_connected()
        cmd = self._make_command("cookies", domain=domain)
        return await self._send_command(cmd)

    async def close_window(self) -> None:
        """Close the automation window."""
        if self._connected:
            try:
                cmd = self._make_command("close-window")
                await self._send_command(cmd)
            except Exception:
                pass
            self._connected = False
