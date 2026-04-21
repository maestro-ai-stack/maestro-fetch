import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from maestro_fetch.adapters.cloud import CloudAdapter
from maestro_fetch.core.config import FetchConfig


def test_supports_dropbox():
    a = CloudAdapter()
    assert a.supports("https://www.dropbox.com/sh/abc/def/file.xlsx") is True


def test_supports_gdrive():
    a = CloudAdapter()
    assert a.supports("https://drive.google.com/file/d/abc/view") is True


def test_does_not_support_other():
    a = CloudAdapter()
    assert a.supports("https://example.com/file.xlsx") is False


def test_dropbox_direct_url_transform():
    from maestro_fetch.adapters.cloud import _to_direct_url
    url = "https://www.dropbox.com/sh/abc/def/report.pdf?dl=0"
    assert _to_direct_url(url) == "https://www.dropbox.com/sh/abc/def/report.pdf?dl=1"


def test_gdrive_direct_url_transform():
    from maestro_fetch.adapters.cloud import _to_direct_url
    url = "https://drive.google.com/file/d/FILE_ID/view?usp=sharing"
    direct = _to_direct_url(url)
    assert "export=download" in direct or "uc?id=" in direct


@pytest.mark.asyncio
async def test_fetch_dropbox_csv(tmp_path):
    a = CloudAdapter()
    config = FetchConfig(cache_dir=tmp_path)
    fake_csv = b"col1,col2\n1,2\n3,4\n"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = fake_csv
        mock_response.headers = {"content-type": "text/csv"}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        result = await a.fetch(
            "https://www.dropbox.com/sh/abc/def/data.csv?dl=0", config
        )

    assert result.source_type == "cloud"
    assert len(result.tables) == 1
    assert list(result.tables[0].columns) == ["col1", "col2"]
