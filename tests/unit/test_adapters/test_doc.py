import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from maestro_fetch.adapters.doc import DocAdapter
from maestro_fetch.core.config import FetchConfig

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_supports_pdf():
    a = DocAdapter()
    assert a.supports("https://example.com/report.pdf") is True

def test_supports_excel():
    a = DocAdapter()
    assert a.supports("https://example.com/data.xlsx") is True

def test_does_not_support_html():
    a = DocAdapter()
    assert a.supports("https://example.com/page.html") is False

@pytest.mark.asyncio
async def test_fetch_excel_from_url(tmp_path):
    a = DocAdapter()
    config = FetchConfig(cache_dir=tmp_path)
    xlsx_bytes = (FIXTURES / "sample.xlsx").read_bytes()

    with patch("httpx.AsyncClient") as mock_class:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xlsx_bytes
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_class.return_value = mock_client

        result = await a.fetch("https://example.com/sample.xlsx", config)

    assert result.source_type == "doc"
    assert len(result.tables) == 1
    assert "name" in result.tables[0].columns
    assert "value" in result.tables[0].columns
