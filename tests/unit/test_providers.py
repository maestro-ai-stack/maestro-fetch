import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from maestro_fetch.providers.registry import get_provider


def test_registry_returns_anthropic():
    p = get_provider("anthropic")
    from maestro_fetch.providers.anthropic import AnthropicProvider
    assert isinstance(p, AnthropicProvider)

def test_registry_returns_openai():
    p = get_provider("openai")
    from maestro_fetch.providers.openai import OpenAIProvider
    assert isinstance(p, OpenAIProvider)

def test_registry_raises_on_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("nonexistent")


anthropic = pytest.importorskip("anthropic", reason="anthropic SDK not installed")


@pytest.mark.asyncio
async def test_anthropic_extract(monkeypatch):
    from maestro_fetch.providers.anthropic import AnthropicProvider

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"country": "US", "gdp": 25.0}')]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_message)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        provider = AnthropicProvider()
        result = await provider.extract(
            content="US GDP is $25 trillion",
            schema={"country": "str", "gdp": "float"},
        )

    assert result == {"country": "US", "gdp": 25.0}
