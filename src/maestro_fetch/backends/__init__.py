"""Backend discovery and priority management.

Instantiates browser backends from config and probes availability
in the order specified by ``config["backends"]["priority"]``.

Default priority:
    1. extension — real Chrome via daemon + Chrome extension (auth, JS, cookies)
"""
from __future__ import annotations

from maestro_fetch.backends.base import BrowserBackend
from maestro_fetch.backends.extension import ExtensionBackend

__all__ = [
    "BrowserBackend",
    "ExtensionBackend",
    "get_available_backends",
    "get_best_backend",
]

_DEFAULT_PRIORITY = ["extension"]


def _make_backend(name: str, cfg: dict) -> BrowserBackend | None:
    """Instantiate a single backend by name, return None if disabled."""
    backend_cfg = cfg.get("backends", {}).get(name, {})
    if not backend_cfg.get("enabled", True):
        return None

    if name == "extension":
        port = backend_cfg.get("port", 19825)
        workspace = backend_cfg.get("workspace", "mfetch")
        return ExtensionBackend(port=port, workspace=workspace)
    return None


async def get_available_backends(config: dict) -> list[BrowserBackend]:
    """Return backends that are installed and configured, in priority order.

    Priority comes from ``config["backends"]["priority"]``; falls back
    to ``["extension"]``.
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
