"""Browser adapter -- dispatches to pluggable browser backends.

Called by the router when a URL needs authenticated or anti-bot access.
Tries backends in priority order and returns a FetchResult on the first
success.
"""
from __future__ import annotations

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.backends import get_available_backends
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import FetchError
from maestro_fetch.core.result import FetchResult


class BrowserAdapter(BaseAdapter):
    """Fetch web pages through pluggable browser backends.

    The adapter iterates backends by config priority and returns the
    content from the first backend that succeeds.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._backend_config = config or {}

    def supports(self, url: str) -> bool:
        """The browser adapter is a fallback -- it supports any HTTP(S) URL."""
        return url.startswith("http://") or url.startswith("https://")

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:  # noqa: ARG002
        """Try each available backend in priority order.

        Returns the result from the first backend that succeeds.
        Raises FetchError if all backends fail or none are available.
        """
        backends = await get_available_backends(self._backend_config)
        if not backends:
            raise FetchError(
                "No browser backends available. "
                "Install bb-browser, configure Cloudflare, or "
                "pip install maestro-fetch[browser] for Playwright."
            )

        last_error: Exception | None = None
        for backend in backends:
            try:
                content = await backend.fetch_content(url)
                return FetchResult(
                    url=url,
                    source_type="browser",
                    content=content,
                    metadata={"backend": backend.name},
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise FetchError(
            f"All browser backends failed for {url}: {last_error}"
        )
