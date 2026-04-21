import pytest
from unittest.mock import AsyncMock

from maestro_fetch.core.fetcher import Fetcher
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.result import FetchResult
from maestro_fetch.core.errors import UnsupportedURLError


@pytest.mark.asyncio
async def test_fetcher_routes_to_matching_adapter():
    fetcher = Fetcher()
    mock_result = FetchResult(url="https://dropbox.com/sh/x", source_type="cloud", content="data")

    class MockAdapter:
        def supports(self, url: str) -> bool:
            return "dropbox" in url

    mock_adapter = MockAdapter()
    mock_adapter.fetch = AsyncMock(return_value=mock_result)
    fetcher._adapters = [mock_adapter]

    config = FetchConfig()
    result = await fetcher.fetch("https://dropbox.com/sh/x/file.csv", config)
    assert result.source_type == "cloud"
    mock_adapter.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_fetcher_raises_on_unsupported():
    fetcher = Fetcher()

    class MockAdapter:
        def supports(self, _url: str) -> bool:
            return False

        async def fetch(self, _url: str, _config: FetchConfig) -> FetchResult:  # pragma: no cover
            raise AssertionError("fetch should not be called for unsupported URLs")

    mock_adapter = MockAdapter()
    fetcher._adapters = [mock_adapter]

    with pytest.raises(UnsupportedURLError):
        await fetcher.fetch("ftp://unsupported.example", FetchConfig())
