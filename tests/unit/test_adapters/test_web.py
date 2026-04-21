import pytest
from unittest.mock import AsyncMock, patch
from maestro_fetch.adapters.web import WebAdapter
from maestro_fetch.core.config import FetchConfig


def test_supports_html():
    a = WebAdapter()
    assert a.supports("https://example.com") is True
    assert a.supports("https://example.com/page.html") is True

def test_does_not_support_pdf():
    a = WebAdapter()
    assert a.supports("https://example.com/report.pdf") is False

def test_does_not_support_dropbox():
    a = WebAdapter()
    assert a.supports("https://dropbox.com/sh/abc") is False

@pytest.mark.asyncio
async def test_fetch_returns_markdown():
    a = WebAdapter()
    config = FetchConfig()

    with patch("maestro_fetch.adapters.web._extension_fetch", new_callable=AsyncMock, return_value=None), \
         patch("maestro_fetch.adapters.web._httpx_fetch", new_callable=AsyncMock, return_value="# Hello\n\nWorld"):
        result = await a.fetch("https://example.com", config)

    assert result.source_type == "web"
    assert result.content == "# Hello\n\nWorld"
    assert result.metadata["adapter"] == "httpx"
    assert result.tables == []
