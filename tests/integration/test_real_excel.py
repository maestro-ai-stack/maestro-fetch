"""Integration tests: fetch and parse REAL Excel files from the internet.

No mocks. All tests require network access and are marked @pytest.mark.network.

Sources:
  - UN GDP data (no file extension in URL): direct download + _parse_excel
  - Japan Population by Age (.xlsx): DocAdapter.fetch()
  - Japan Life Expectancy (.xlsx): DocAdapter.fetch()
"""
from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pandas as pd
import pytest

from maestro_fetch.adapters.doc import DocAdapter, _parse_excel
from maestro_fetch.core.config import FetchConfig

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
UN_GDP_URL = "https://unstats.un.org/unsd/amaapi/api/file/2"
JAPAN_POP_URL = (
    "https://www.stat.go.jp/data/nenkan/75nenkan/zuhyou/y750207000.xlsx"
)
JAPAN_LIFE_URL = (
    "https://www.stat.go.jp/data/nenkan/75nenkan/zuhyou/y750224000.xlsx"
)

# Shared temp cache directory for all tests in this module
_CACHE_DIR = Path(".maestro_cache_integration_test")


@pytest.fixture(autouse=True)
def _clean_cache():
    """Create and clean up the integration test cache directory."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if _CACHE_DIR.exists():
        shutil.rmtree(_CACHE_DIR)


def _make_config(timeout: int = 120) -> FetchConfig:
    return FetchConfig(cache_dir=_CACHE_DIR, timeout=timeout)


# =========================================================================
# 1) UN GDP -- URL has no .xlsx extension, so DocAdapter.supports() is False.
#    We download with httpx, then call _parse_excel() directly.
# =========================================================================
class TestUnGdp:
    """UN GDP Excel file (no extension in URL)."""

    @pytest.mark.network
    def test_supports_returns_false_for_extensionless_url(self):
        adapter = DocAdapter()
        assert adapter.supports(UN_GDP_URL) is False

    @pytest.mark.network
    def test_parse_excel_from_raw_download(self):
        """Download UN GDP file via httpx, parse with _parse_excel()."""
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            resp = client.get(UN_GDP_URL)
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        content = resp.content

        # Parse
        text, tables = _parse_excel(content)

        # Must return at least one DataFrame
        assert len(tables) >= 1
        df = tables[0]
        assert isinstance(df, pd.DataFrame)

        # Non-empty
        assert len(df) > 0, "DataFrame has zero rows"
        assert len(df.columns) > 0, "DataFrame has zero columns"

        # Markdown text should be non-empty
        assert len(text) > 100, "Markdown text too short for GDP dataset"

    @pytest.mark.network
    def test_raw_bytes_are_valid_excel(self):
        """Verify downloaded bytes start with Excel magic bytes (PK zip)."""
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            resp = client.get(UN_GDP_URL)
        assert resp.status_code == 200
        # XLSX files are ZIP archives: first 2 bytes = PK (0x50, 0x4B)
        assert resp.content[:2] == b"PK", "File does not start with PK (ZIP) magic"


# =========================================================================
# 2) Japan Population by Age -- .xlsx URL, use DocAdapter.fetch()
# =========================================================================
class TestJapanPopulation:
    """Japan Population by Age Excel file from stat.go.jp."""

    @pytest.mark.network
    def test_supports_matches_xlsx_url(self):
        adapter = DocAdapter()
        assert adapter.supports(JAPAN_POP_URL) is True

    @pytest.mark.network
    async def test_fetch_returns_valid_result(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_POP_URL, config)

        # FetchResult basics
        assert result.url == JAPAN_POP_URL
        assert result.source_type == "doc"
        assert result.metadata["ext"] == ".xlsx"

        # Tables
        assert len(result.tables) >= 1
        df = result.tables[0]
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0, "DataFrame has zero rows"
        assert len(df.columns) > 0, "DataFrame has zero columns"

        # Content (markdown)
        assert len(result.content) > 0, "Content is empty"

    @pytest.mark.network
    async def test_raw_file_cached(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_POP_URL, config)

        assert result.raw_path is not None
        assert result.raw_path.exists(), "Cached raw file does not exist"
        assert result.raw_path.stat().st_size > 0, "Cached raw file is empty"
        assert result.raw_path.suffix == ".xlsx"

    @pytest.mark.network
    async def test_dataframe_has_rows_and_columns(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_POP_URL, config)

        df = result.tables[0]
        # Japanese demographic table should have a reasonable number of rows
        assert len(df) >= 5, f"Expected >= 5 rows, got {len(df)}"
        assert len(df.columns) >= 2, f"Expected >= 2 columns, got {len(df.columns)}"


# =========================================================================
# 3) Japan Life Expectancy -- .xlsx URL, use DocAdapter.fetch()
# =========================================================================
class TestJapanLifeExpectancy:
    """Japan Life Expectancy Excel file from stat.go.jp."""

    @pytest.mark.network
    def test_supports_matches_xlsx_url(self):
        adapter = DocAdapter()
        assert adapter.supports(JAPAN_LIFE_URL) is True

    @pytest.mark.network
    async def test_fetch_returns_valid_result(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_LIFE_URL, config)

        assert result.url == JAPAN_LIFE_URL
        assert result.source_type == "doc"
        assert result.metadata["ext"] == ".xlsx"

        assert len(result.tables) >= 1
        df = result.tables[0]
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    @pytest.mark.network
    async def test_raw_file_cached(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_LIFE_URL, config)

        assert result.raw_path is not None
        assert result.raw_path.exists()
        assert result.raw_path.stat().st_size > 0
        assert result.raw_path.suffix == ".xlsx"

    @pytest.mark.network
    async def test_dataframe_shape(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_LIFE_URL, config)

        df = result.tables[0]
        # Life expectancy data should have multiple rows and columns
        assert len(df) >= 3, f"Expected >= 3 rows, got {len(df)}"
        assert len(df.columns) >= 2, f"Expected >= 2 columns, got {len(df.columns)}"

    @pytest.mark.network
    async def test_content_is_markdown(self):
        adapter = DocAdapter()
        config = _make_config()
        result = await adapter.fetch(JAPAN_LIFE_URL, config)

        # Markdown table format uses pipe characters
        assert "|" in result.content, "Content does not look like markdown table"
        assert len(result.content) > 50, "Content too short for life expectancy data"
