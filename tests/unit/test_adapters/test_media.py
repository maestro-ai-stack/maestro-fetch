import pytest
from unittest.mock import patch
from maestro_fetch.adapters.media import MediaAdapter
from maestro_fetch.core.config import FetchConfig


def test_supports_youtube():
    a = MediaAdapter()
    assert a.supports("https://www.youtube.com/watch?v=abc") is True
    assert a.supports("https://youtu.be/abc") is True

def test_supports_vimeo():
    a = MediaAdapter()
    assert a.supports("https://vimeo.com/123456") is True

def test_does_not_support_web():
    a = MediaAdapter()
    assert a.supports("https://example.com") is False

@pytest.mark.asyncio
async def test_fetch_returns_transcript(tmp_path):
    a = MediaAdapter()
    config = FetchConfig(cache_dir=tmp_path)

    with patch("maestro_fetch.adapters.media._download_audio") as mock_dl, \
         patch("maestro_fetch.adapters.media._transcribe") as mock_tr:
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake")
        mock_dl.return_value = audio_path
        mock_tr.return_value = "This is the transcript."

        result = await a.fetch("https://www.youtube.com/watch?v=abc", config)

    assert result.source_type == "media"
    assert "transcript" in result.content.lower() or "this is" in result.content.lower()
