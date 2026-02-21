import pytest
from unittest.mock import AsyncMock, patch
from maestro_fetch.core.fetcher import Fetcher
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.result import FetchResult
from maestro_fetch.core.errors import UnsupportedURLError


@pytest.mark.asyncio
async def test_fetcher_routes_to_matching_adapter():
    fetcher = Fetcher()
    mock_result = FetchResult(url="https://dropbox.com/sh/x", source_type="cloud", content="data")

    mock_adapter = AsyncMock()
    mock_adapter.supports = lambda url: "dropbox" in url
    mock_adapter.fetch = AsyncMock(return_value=mock_result)
    fetcher._adapters = [mock_adapter]

    config = FetchConfig()
    result = await fetcher.fetch("https://dropbox.com/sh/x/file.csv", config)
    assert result.source_type == "cloud"
    mock_adapter.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_fetcher_raises_on_unsupported():
    fetcher = Fetcher()
    mock_adapter = AsyncMock()
    mock_adapter.supports = lambda url: False
    fetcher._adapters = [mock_adapter]

    with pytest.raises(UnsupportedURLError):
        await fetcher.fetch("ftp://unsupported.example", FetchConfig())
