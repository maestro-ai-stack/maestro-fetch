"""Integration tests that scrape REAL public web pages via WebAdapter.

No mocks. These tests hit live URLs and verify that the public web path returns
meaningful Markdown content with correct metadata.

All tests are marked @pytest.mark.network and will be skipped when
network is unavailable or the marker is deselected.
"""
import pytest

from maestro_fetch.adapters.web import WebAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.fetcher import Fetcher
from maestro_fetch.core.router import detect_type

network = pytest.mark.network

# Shared timeout for all real-web tests (seconds).
_TIMEOUT = 60


# ---------------------------------------------------------------------------
# TestWebAdapterRealPages -- direct WebAdapter usage
# ---------------------------------------------------------------------------

@network
class TestWebAdapterRealPages:
    """Scrape real public pages through WebAdapter directly."""

    @pytest.fixture
    def adapter(self) -> WebAdapter:
        return WebAdapter()

    @pytest.fixture
    def config(self) -> FetchConfig:
        return FetchConfig(timeout=_TIMEOUT)

    # -- Wikipedia GDP table ------------------------------------------------

    @pytest.mark.asyncio
    async def test_wikipedia_gdp_table(self, adapter: WebAdapter, config: FetchConfig):
        """Wikipedia GDP page contains country names and substantial content."""
        url = "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"
        result = await adapter.fetch(url, config)

        assert result.source_type == "web"
        assert len(result.content) > 10000, (
            f"Expected >10000 chars, got {len(result.content)}"
        )

        content_lower = result.content.lower()
        assert "united states" in content_lower or "china" in content_lower, (
            "Expected 'United States' or 'China' in GDP page content"
        )

        assert result.tables == []
        assert result.metadata["adapter"] in {"httpx", "extension"}

    # -- Japan Statistics Bureau --------------------------------------------

    @pytest.mark.asyncio
    async def test_japan_statistics_bureau(self, adapter: WebAdapter, config: FetchConfig):
        """Japan Statistics Bureau handbook page has expected keywords."""
        url = "https://www.stat.go.jp/english/data/handbook/index.html"
        result = await adapter.fetch(url, config)

        assert result.source_type == "web"
        assert len(result.content) > 1000, (
            f"Expected >1000 chars, got {len(result.content)}"
        )

        content_lower = result.content.lower()
        assert "statistical handbook" in content_lower, (
            "Expected 'Statistical Handbook' in Japan Stats page"
        )

        assert result.tables == []
        assert result.metadata["adapter"] in {"httpx", "extension"}

    # -- UNdata Portal ------------------------------------------------------

    @pytest.mark.asyncio
    async def test_undata_portal(self, adapter: WebAdapter, config: FetchConfig):
        """UN data portal contains expected branding keywords."""
        url = "https://data.un.org/"
        result = await adapter.fetch(url, config)

        assert result.source_type == "web"
        assert len(result.content) > 1000, (
            f"Expected >1000 chars, got {len(result.content)}"
        )

        content_lower = result.content.lower()
        assert "undata" in content_lower or "united nations" in content_lower, (
            "Expected 'UNdata' or 'United Nations' in UN portal"
        )

        assert result.tables == []
        assert result.metadata["adapter"] in {"httpx", "extension"}

    # -- MAFF Agriculture Page (English) ------------------------------------

    @pytest.mark.asyncio
    async def test_maff_agriculture_page(self, adapter: WebAdapter, config: FetchConfig):
        """Japan MAFF English page contains agriculture ministry keywords."""
        url = "https://www.maff.go.jp/e/index.html"
        result = await adapter.fetch(url, config)

        assert result.source_type == "web"
        assert len(result.content) > 100, (
            f"Expected non-trivial content, got {len(result.content)} chars"
        )

        content_lower = result.content.lower()
        assert "ministry of agriculture" in content_lower or "maff" in content_lower, (
            "Expected 'Ministry of Agriculture' or 'MAFF' in page content"
        )

        assert result.tables == []
        assert result.metadata["adapter"] in {"httpx", "extension"}


# ---------------------------------------------------------------------------
# TestRouterToWeb -- verify Fetcher routes HTML URLs to WebAdapter
# ---------------------------------------------------------------------------

@network
class TestRouterToWeb:
    """Verify that HTML URLs are routed to WebAdapter (not DocAdapter
    or CloudAdapter) both at the router level and end-to-end via Fetcher."""

    _HTML_URLS = [
        "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)",
        "https://www.stat.go.jp/english/data/handbook/index.html",
        "https://data.un.org/",
        "https://www.maff.go.jp/e/index.html",
    ]

    def test_router_detects_web_for_html_urls(self):
        """All test URLs should be classified as 'web' by the router."""
        for url in self._HTML_URLS:
            detected = detect_type(url)
            assert detected == "web", (
                f"Router classified {url} as '{detected}', expected 'web'"
            )

    def test_web_adapter_supports_html_urls(self):
        """WebAdapter.supports() returns True for all test URLs."""
        adapter = WebAdapter()
        for url in self._HTML_URLS:
            assert adapter.supports(url), (
                f"WebAdapter.supports() returned False for {url}"
            )

    @pytest.mark.asyncio
    async def test_fetcher_routes_to_web_adapter(self):
        """End-to-end: Fetcher dispatches an HTML URL and returns web result."""
        fetcher = Fetcher()
        config = FetchConfig(timeout=_TIMEOUT)

        # Use a lightweight page to keep the test fast.
        result = await fetcher.fetch("https://data.un.org/", config)

        assert result.source_type == "web"
        assert result.metadata["adapter"] in {"httpx", "extension"}
        assert len(result.content) > 100
