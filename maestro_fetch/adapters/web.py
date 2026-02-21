"""WebAdapter: fetches JS-rendered web pages via Crawl4AI, outputs Markdown.

Responsibility: handle generic web URLs (HTML pages, JS-rendered SPAs).
Non-goals: PDF, spreadsheets, cloud storage, media -- those are excluded
via _NON_WEB_PATTERNS and handled by dedicated adapters.

Invariants:
- supports() returns False for URLs matching known non-web patterns
- fetch() always returns FetchResult with source_type="web"
- fetch() raises DownloadError on crawl failure, never swallows
"""
from __future__ import annotations
import re
from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.result import FetchResult
from maestro_fetch.core.errors import DownloadError

_NON_WEB_PATTERNS = [
    r"dropbox\.com/",
    r"drive\.google\.com/",
    r"docs\.google\.com/",
    r"youtube\.com/watch",
    r"youtu\.be/",
    r"\.pdf(\?|$)",
    r"\.(xlsx|xls|ods|csv)(\?|$)",
]


class WebAdapter(BaseAdapter):
    """Fetches JS-rendered web pages via Crawl4AI, outputs Markdown."""

    def supports(self, url: str) -> bool:
        return not any(re.search(p, url, re.IGNORECASE) for p in _NON_WEB_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as e:
            raise ImportError(
                "crawl4ai is required for WebAdapter: pip install crawl4ai"
            ) from e

        try:
            async with AsyncWebCrawler() as crawler:
                crawl_kwargs: dict = dict(url=url)
                if config.headers:
                    crawl_kwargs["headers"] = config.headers
                crawl_result = await crawler.arun(**crawl_kwargs)
                if not crawl_result.success:
                    raise DownloadError(f"Crawl4AI failed for {url}")
                content = crawl_result.markdown or ""
        except Exception as e:
            if isinstance(e, (DownloadError, ImportError)):
                raise
            raise DownloadError(f"Web fetch failed for {url}: {e}") from e

        return FetchResult(
            url=url,
            source_type="web",
            content=content,
            tables=[],
            metadata={"adapter": "crawl4ai"},
        )
