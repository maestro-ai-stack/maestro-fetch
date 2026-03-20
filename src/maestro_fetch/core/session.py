"""Session manager — persistent browser across CLI invocations.

Architecture:
  session start  → launch Chromium with --remote-debugging-port,
                   save CDP endpoint + PID to ~/.maestro/sessions/active.json
  session click  → connect via CDP, perform action, disconnect (browser stays)
  session end    → kill Chromium process, delete session file
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SESSIONS_DIR = Path.home() / ".maestro" / "sessions"
_ACTIVE_FILE = _SESSIONS_DIR / "active.json"

# Port range for auto-selection
_CDP_PORT_START = 9400
_CDP_PORT_END = 9500


@dataclass
class SessionState:
    session_id: str
    cdp_port: int
    pid: int
    url: str
    user_data_dir: str
    managed: bool = True  # True = we launched it, False = external Chrome
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def cdp_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"

    def save(self) -> None:
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        _ACTIVE_FILE.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> SessionState | None:
        if not _ACTIVE_FILE.exists():
            return None
        try:
            data = json.loads(_ACTIVE_FILE.read_text())
            return cls(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    @classmethod
    def clear(cls) -> None:
        if _ACTIVE_FILE.exists():
            _ACTIVE_FILE.unlink()


def _find_free_port() -> int:
    """Find a free port in the CDP range."""
    import socket

    for port in range(_CDP_PORT_START, _CDP_PORT_END):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {_CDP_PORT_START}-{_CDP_PORT_END}")


def _find_chromium() -> str:
    """Find Chromium binary: Playwright's bundled > system Chrome."""
    # 1) Playwright bundled
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and os.path.isfile(path):
                return path
    except Exception:
        pass

    # 2) macOS system Chrome
    sys_chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.isfile(sys_chrome):
        return sys_chrome

    raise RuntimeError("No Chromium/Chrome binary found. Install playwright browsers: playwright install chromium")


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


async def _wait_for_cdp(endpoint: str, timeout: float = 15.0) -> bool:
    """Poll CDP /json/version until it responds."""
    import httpx

    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(timeout=2) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{endpoint}/json/version")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await _async_sleep(0.3)
    return False


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


def _get_pid_on_port(port: int) -> int:
    """Find PID listening on a port using lsof (macOS-friendly, no root)."""
    try:
        out = subprocess.check_output(
            ["lsof", "-ti", f":{port}"], text=True, timeout=5
        ).strip()
        if out:
            return int(out.splitlines()[0])
    except Exception:
        pass
    return 0


def _kill_stale_playwright_drivers() -> int:
    """Kill orphaned Playwright driver processes that block CDP connections.

    Returns the number of processes killed.
    """
    killed = 0
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "playwright/driver/package/cli.js run-driver"],
            text=True, timeout=5,
        ).strip()
        for line in out.splitlines():
            pid = int(line)
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
                log.info("Killed stale Playwright driver PID %d", pid)
            except (OSError, ProcessLookupError):
                pass
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass  # no matching processes
    return killed


# ---- Public API ----


def get_active_session() -> SessionState | None:
    """Load and validate the active session. Returns None if no valid session."""
    state = SessionState.load()
    if state is None:
        return None
    # For managed sessions, check if process is still alive
    if state.managed and not _is_process_alive(state.pid):
        log.warning("Session process %d is dead, cleaning up", state.pid)
        SessionState.clear()
        return None
    return state


async def start_session(url: str, cdp: bool = False, cdp_port: int = 9222) -> SessionState:
    """Launch Chromium with CDP and navigate to URL.

    Args:
        url: URL to navigate to.
        cdp: If True, connect to an already-running Chrome on cdp_port
             (reuses login state). If False, launch a new Chromium instance.
        cdp_port: CDP port when cdp=True. Default 9222.
    """
    # Check for existing session
    existing = get_active_session()
    if existing is not None:
        raise RuntimeError(
            f"Session already active (PID {existing.pid}, port {existing.cdp_port}). "
            "Run 'mfetch session end' first."
        )

    if cdp:
        # Connect to already-running Chrome
        endpoint = f"http://127.0.0.1:{cdp_port}"
        ready = await _wait_for_cdp(endpoint, timeout=5.0)
        if not ready:
            raise RuntimeError(
                f"No Chrome found on port {cdp_port}. Start Chrome with:\n"
                f"  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome "
                f"--remote-debugging-port={cdp_port}"
            )
        # Find Chrome PID from port
        pid = _get_pid_on_port(cdp_port)

        import uuid

        state = SessionState(
            session_id=str(uuid.uuid4())[:8],
            cdp_port=cdp_port,
            pid=pid,
            url=url,
            user_data_dir="external",
            managed=False,  # we didn't launch it, don't kill it
        )

        # Navigate to URL in a new tab
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(endpoint)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        finally:
            await pw.stop()

        state.save()
        return state

    # Launch new Chromium
    port = _find_free_port()
    chromium = _find_chromium()
    user_data_dir = str(_SESSIONS_DIR / f"profile-{port}")

    cmd = [
        chromium,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]

    log.info("Launching: %s", " ".join(cmd[:3]))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach from parent
    )

    # Wait for CDP to be ready
    endpoint = f"http://127.0.0.1:{port}"
    ready = await _wait_for_cdp(endpoint, timeout=15.0)
    if not ready:
        proc.kill()
        raise RuntimeError(f"Chromium failed to start CDP on port {port}")

    import uuid

    state = SessionState(
        session_id=str(uuid.uuid4())[:8],
        cdp_port=port,
        pid=proc.pid,
        url=url,
        user_data_dir=user_data_dir,
    )
    state.save()
    return state


async def connect_page(
    state: SessionState, *, timeout: float = 15.0
) -> tuple[Any, Any, Any]:
    """Connect to active session, return (playwright_ctx, browser, page).

    The caller MUST call disconnect() when done.
    Finds the page whose URL matches the session's target URL domain.

    If the connection hangs (stale Playwright driver blocking CDP), kills
    orphaned drivers and retries once.
    """
    import asyncio

    try:
        return await asyncio.wait_for(
            _connect_page_inner(state), timeout=timeout
        )
    except asyncio.TimeoutError:
        killed = _kill_stale_playwright_drivers()
        if killed:
            log.warning(
                "connect_page timed out, killed %d stale drivers, retrying", killed
            )
            await _async_sleep(1)
            return await asyncio.wait_for(
                _connect_page_inner(state), timeout=timeout
            )
        raise RuntimeError(
            f"connect_page timed out after {timeout}s "
            "(no stale drivers found — Chrome may be unresponsive)"
        )


async def _connect_page_inner(state: SessionState) -> tuple[Any, Any, Any]:
    """Inner connection logic — separated for timeout wrapping."""
    from urllib.parse import urlparse

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(state.cdp_endpoint)
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

    # Find page matching session URL domain
    target_host = urlparse(state.url).hostname or ""
    matched_page = None
    for p in reversed(ctx.pages):
        page_host = urlparse(p.url).hostname or ""
        if target_host and target_host in page_host:
            matched_page = p
            break

    page = matched_page or (ctx.pages[-1] if ctx.pages else await ctx.new_page())
    return pw, browser, page


async def disconnect(pw: Any, browser: Any) -> None:
    """Disconnect from CDP without closing the browser."""
    try:
        browser.close  # just ensure no close is called
        await pw.stop()
    except Exception:
        pass


def end_session() -> bool:
    """Kill the browser process (if managed) and clean up session state."""
    state = SessionState.load()
    if state is None:
        return False

    # Only kill the process if we launched it
    if state.managed and _is_process_alive(state.pid):
        try:
            os.kill(state.pid, signal.SIGTERM)
            for _ in range(10):
                if not _is_process_alive(state.pid):
                    break
                time.sleep(0.2)
            else:
                os.kill(state.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass

    SessionState.clear()
    return True
