"""Fetcher -- main router that dispatches URLs to the correct adapter.

Responsibility: match a URL against registered adapters (in priority order)
and delegate the actual fetching to the first match.

Inputs: URL string, FetchConfig
Outputs: FetchResult (from the matched adapter)
Invariants:
  - Adapter order matters: CloudAdapter > DocAdapter > WebAdapter (fallback)
  - If no adapter matches, raises UnsupportedURLError
  - batch_fetch respects concurrency limit via asyncio.Semaphore
Failure modes: UnsupportedURLError if no adapter matches
"""
from __future__ import annotations

from maestro_fetch.adapters.baidu_pan import BaiduPanAdapter
from maestro_fetch.adapters.binary import BinaryAdapter
from maestro_fetch.adapters.cloud import CloudAdapter
from maestro_fetch.adapters.doc import DocAdapter
from maestro_fetch.adapters.web import WebAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.result import FetchResult
from maestro_fetch.core.errors import UnsupportedURLError

# Order matters:
#   BaiduPan > Cloud (both match baidu; BaiduPan more specific)
#   Binary > Doc (binary handles archives; Doc handles parseable docs)
#   Web is final fallback
_DEFAULT_ADAPTERS = [BaiduPanAdapter, CloudAdapter, BinaryAdapter, DocAdapter, WebAdapter]


class Fetcher:
    """Dispatches fetch requests to the correct adapter."""

    def __init__(self) -> None:
        self._adapters = [cls() for cls in _DEFAULT_ADAPTERS]

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        for adapter in self._adapters:
            if adapter.supports(url):
                return await adapter.fetch(url, config)
        raise UnsupportedURLError(f"No adapter supports URL: {url}")

    async def batch_fetch(
        self, urls: list[str], config: FetchConfig, concurrency: int = 5
    ) -> list[FetchResult]:
        import asyncio

        semaphore = asyncio.Semaphore(concurrency)

        async def _fetch_one(url: str) -> FetchResult:
            async with semaphore:
                return await self.fetch(url, config)

        return await asyncio.gather(
            *[_fetch_one(u) for u in urls], return_exceptions=False
        )
