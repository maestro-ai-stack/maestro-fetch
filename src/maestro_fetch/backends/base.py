"""Pluggable browser backend protocol.

Backends provide authenticated web access through real browsers.
Each backend implements the same async interface so the router can
try them in priority order without knowing implementation details.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrowserBackend(Protocol):
    """Contract for browser backends.

    Implementations: extension, cdp, playwright.
    The router iterates backends by config priority and uses the first
    one where ``is_available()`` returns True.
    """

    name: str

    async def is_available(self) -> bool:
        """Check if this backend is installed and configured."""
        ...

    async def fetch_content(self, url: str) -> str:
        """Fetch page content as markdown (with login state if available)."""
        ...

    async def fetch_screenshot(self, url: str) -> bytes:
        """Capture page screenshot as PNG bytes."""
        ...

    async def eval_js(self, js: str) -> Any:
        """Execute JavaScript in page context and return the result."""
        ...

    async def site_adapter(self, adapter_name: str, *args: str) -> dict:
        """Run a site-specific adapter command."""
        ...
