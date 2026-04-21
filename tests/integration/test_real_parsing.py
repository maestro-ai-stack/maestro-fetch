"""Integration tests that exercise real parsers on real fixture files.

No mocks. No network. Just real parsing logic.
"""
from pathlib import Path
from maestro_fetch.adapters.doc import _parse_excel, _parse_csv
from maestro_fetch.adapters.cloud import _parse_content
from maestro_fetch.core.router import detect_type
from maestro_fetch.core.fetcher import Fetcher
from maestro_fetch.core.config import FetchConfig

FIXTURES = Path(__file__).parent.parent / "unit" / "fixtures"


class TestExcelParsing:
    """Real Excel parsing without mocks."""

    def test_parse_sample_xlsx(self):
        content = (FIXTURES / "sample.xlsx").read_bytes()
        text, tables = _parse_excel(content)
        assert len(tables) == 1
        df = tables[0]
        assert "name" in df.columns
        assert "value" in df.columns
        assert len(df) == 2
        assert df.iloc[0]["name"] == "alpha"
        assert df.iloc[0]["value"] == 10

    def test_parse_multi_sheet_xlsx(self):
        content = (FIXTURES / "multi_sheet.xlsx").read_bytes()
        text, tables = _parse_excel(content)
        assert len(tables) == 2
        df = tables[0]
        assert "country" in df.columns
        assert "gdp_billion" in df.columns
        assert len(df) == 3
        assert df.iloc[0]["country"] == "US"
        assert "population_million" in tables[1].columns

    def test_excel_to_markdown_contains_data(self):
        content = (FIXTURES / "sample.xlsx").read_bytes()
        text, _ = _parse_excel(content)
        assert "alpha" in text
        assert "beta" in text
        assert "10" in text


class TestCSVParsing:
    """Real CSV parsing without mocks."""

    def test_parse_csv_file(self):
        content = (FIXTURES / "sample.csv").read_bytes()
        text, tables = _parse_csv(content)
        assert len(tables) == 1
        df = tables[0]
        assert list(df.columns) == ["city", "temp_c", "humidity"]
        assert len(df) == 4
        assert df.iloc[0]["city"] == "Singapore"

    def test_csv_to_markdown(self):
        content = (FIXTURES / "sample.csv").read_bytes()
        text, _ = _parse_csv(content)
        assert "Singapore" in text
        assert "Tokyo" in text

    def test_cloud_parse_content_csv(self):
        """Test CloudAdapter's _parse_content with real CSV bytes."""
        content = (FIXTURES / "sample.csv").read_bytes()
        text, tables = _parse_content(content, "data.csv")
        assert len(tables) == 1
        assert "Singapore" in text

    def test_cloud_parse_content_xlsx(self):
        """Test CloudAdapter's _parse_content with real Excel bytes."""
        content = (FIXTURES / "sample.xlsx").read_bytes()
        text, tables = _parse_content(content, "report.xlsx")
        assert len(tables) == 1
        assert "alpha" in text


class TestRouterIntegration:
    """Test that router + fetcher adapter selection works end-to-end."""

    def test_router_consistency_with_adapters(self):
        """Verify router detect_type aligns with adapter.supports() for key URLs."""
        from maestro_fetch.adapters.cloud import CloudAdapter
        from maestro_fetch.adapters.doc import DocAdapter
        from maestro_fetch.adapters.web import WebAdapter

        cloud = CloudAdapter()
        doc = DocAdapter()
        web = WebAdapter()

        test_cases = [
            ("https://www.dropbox.com/sh/abc/file.csv?dl=0", "cloud", cloud),
            ("https://drive.google.com/file/d/abc/view", "cloud", cloud),
            ("https://example.com/report.pdf", "doc", doc),
            ("https://example.com/data.xlsx", "doc", doc),
            ("https://example.com/data.csv", "doc", doc),
            ("https://example.com/page", "web", web),
            ("https://example.com/page.html", "web", web),
        ]

        for url, expected_type, expected_adapter in test_cases:
            assert detect_type(url) == expected_type, f"Router failed for {url}"
            assert expected_adapter.supports(url), f"Adapter.supports() failed for {url}"

    def test_fetcher_adapter_priority(self):
        """Cloud URLs with file extensions should go to CloudAdapter, not DocAdapter."""
        from maestro_fetch.adapters.cloud import CloudAdapter

        cloud = CloudAdapter()
        # Dropbox CSV link -- CloudAdapter should match, DocAdapter should NOT
        url = "https://www.dropbox.com/sh/abc/data.csv?dl=0"
        assert cloud.supports(url) is True
        # DocAdapter also matches .csv -- but Fetcher tries Cloud first
        # This verifies the priority ordering is correct
        fetcher = Fetcher()
        # First adapter that matches should be CloudAdapter
        for adapter in fetcher._adapters:
            if adapter.supports(url):
                assert isinstance(adapter, CloudAdapter)
                break


class TestFetchConfigDefaults:
    """Verify FetchConfig works with real Path operations."""

    def test_cache_dir_creation(self, tmp_path):
        config = FetchConfig(cache_dir=tmp_path / "test_cache")
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        assert config.cache_dir.exists()

    def test_config_defaults(self):
        config = FetchConfig()
        assert config.provider == "anthropic"
        assert config.timeout == 60
        assert config.max_retries == 3
        assert config.output_format == "markdown"
