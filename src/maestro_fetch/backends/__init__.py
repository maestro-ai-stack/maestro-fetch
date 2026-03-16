"""Backend discovery and priority management.

Instantiates (materialize) browser backends from config and probes
(detect) availability in the order specified by
``config["backends"]["priority"]``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from maestro_fetch.backends.base import BrowserBackend
from maestro_fetch.backends.bb_browser import BbBrowserBackend
from maestro_fetch.backends.cdp import CDPBackend
from maestro_fetch.backends.cloudflare import CloudflareBackend
from maestro_fetch.backends.playwright import PlaywrightBackend

if TYPE_CHECKING:
    pass

__all__ = [
    "BrowserBackend",
    "BbBrowserBackend",
    "CDPBackend",
    "CloudflareBackend",
    "PlaywrightBackend",
    "get_available_backends",
    "get_best_backend",
]

_DEFAULT_PRIORITY = ["bb-browser", "cdp", "cloudflare", "playwright"]


def _make_backend(name: str, cfg: dict) -> BrowserBackend | None:
    """Instantiate a single backend by name, return None if disabled."""
    backend_cfg = cfg.get("backends", {}).get(name, {})
    if not backend_cfg.get("enabled", True):
        return None

    if name == "bb-browser":
        return BbBrowserBackend()
    if name == "cdp":
        endpoint = backend_cfg.get("endpoint")
        return CDPBackend(endpoint=endpoint)
    if name == "cloudflare":
        account_id = backend_cfg.get("account_id", "")
        api_token = backend_cfg.get("api_token", "")
        return CloudflareBackend(account_id=account_id, api_token=api_token)
    if name == "playwright":
        headless = backend_cfg.get("headless", True)
        return PlaywrightBackend(headless=headless)
    return None


async def get_available_backends(config: dict) -> list[BrowserBackend]:
    """Return backends that are installed and configured, in priority order.

    Priority comes from ``config["backends"]["priority"]``; falls back
    to ``["bb-browser", "cloudflare", "playwright"]``.
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
