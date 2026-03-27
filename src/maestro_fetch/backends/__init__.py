"""Backend discovery and priority management.

Instantiates browser backends from config and probes availability
in the order specified by ``config["backends"]["priority"]``.

Default priority:
    1. extension  — real Chrome via daemon + Chrome extension (auth, JS, cookies)
    2. cdp        — Chrome with --remote-debugging-port=9222 (no extension)
    3. playwright — headless Chromium fallback (CI/servers)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from maestro_fetch.backends.base import BrowserBackend
from maestro_fetch.backends.browser_use import BrowserUseBackend
from maestro_fetch.backends.cdp import CDPBackend
from maestro_fetch.backends.extension import ExtensionBackend
from maestro_fetch.backends.playwright import PlaywrightBackend

if TYPE_CHECKING:
    pass

__all__ = [
    "BrowserBackend",
    "BrowserUseBackend",
    "CDPBackend",
    "ExtensionBackend",
    "PlaywrightBackend",
    "get_available_backends",
    "get_best_backend",
]

_DEFAULT_PRIORITY = ["extension", "cdp", "playwright"]


def _make_backend(name: str, cfg: dict) -> BrowserBackend | None:
    """Instantiate a single backend by name, return None if disabled."""
    backend_cfg = cfg.get("backends", {}).get(name, {})
    if not backend_cfg.get("enabled", True):
        return None

    if name == "extension":
        port = backend_cfg.get("port", 19825)
        workspace = backend_cfg.get("workspace", "mfetch")
        daemon_binary = backend_cfg.get("daemon_binary", "opencli-rs")
        return ExtensionBackend(
            port=port, workspace=workspace, daemon_binary=daemon_binary
        )
    if name == "cdp":
        endpoint = backend_cfg.get("endpoint")
        return CDPBackend(endpoint=endpoint)
    if name == "playwright":
        headless = backend_cfg.get("headless", True)
        return PlaywrightBackend(headless=headless)
    if name == "browser-use":
        model = backend_cfg.get("model", "claude-sonnet-4-20250514")
        timeout = backend_cfg.get("timeout", 120)
        return BrowserUseBackend(model=model, timeout=timeout)
    return None


async def get_available_backends(config: dict) -> list[BrowserBackend]:
    """Return backends that are installed and configured, in priority order.

    Priority comes from ``config["backends"]["priority"]``; falls back
    to ``["extension", "cdp", "playwright"]``.
    """
    priority = (
        config.get("backends", {}).get("priority", _DEFAULT_PRIORITY)
    )
    available: list[BrowserBackend] = []
    for name in priority:
        backend = _make_backend(name, config)
        if backend is not None and await backend.is_available():
            available.append(backend)
    return available


async def get_best_backend(config: dict) -> BrowserBackend | None:
    """Return the first available backend, or None."""
    backends = await get_available_backends(config)
    return backends[0] if backends else None
