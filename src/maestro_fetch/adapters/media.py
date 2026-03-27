"""MediaAdapter -- downloads video/audio and transcribes to text.

Responsibilities:
- Detect media URLs (YouTube, Vimeo, etc.) via regex
- Download audio track using yt-dlp (optional dependency)
- Transcribe audio using OpenAI Whisper local model (optional dependency)
- Return transcript as FetchResult with source_type="media"

Invariants:
- supports() is pure regex, no network calls
- fetch() runs blocking yt-dlp and Whisper in thread pool to stay async-safe
- yt-dlp and whisper are lazy-imported; ImportError guides user to install extras
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError, ParseError
from maestro_fetch.core.result import FetchResult

_MEDIA_PATTERNS = [
    r"youtube\.com/watch",
    r"youtu\.be/",
    r"vimeo\.com/\d+",
    r"bilibili\.com/video/",
    r"tiktok\.com/.+/video/",
]


def _download_audio(url: str, out_dir: Path) -> Path:
    """Download audio track from video URL using yt-dlp. Returns path to audio file."""
    try:
        import yt_dlp
    except ImportError as e:
        raise ImportError("pip install maestro-fetch[media]") from e

    out_template = str(out_dir / "audio.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    for f in out_dir.glob("audio.*"):
        return f
    raise DownloadError(f"yt-dlp did not produce output for {url}")


def _transcribe(audio_path: Path) -> str:
    """Transcribe audio file using OpenAI Whisper (local model)."""
    try:
        import whisper
    except ImportError as e:
        raise ImportError("pip install maestro-fetch[media]") from e

    model = whisper.load_model("base")
    result = model.transcribe(str(audio_path))
    return result["text"]


class MediaAdapter(BaseAdapter):
    """Downloads video/audio and transcribes to text via yt-dlp + Whisper."""

    def supports(self, url: str) -> bool:
        return any(re.search(p, url, re.IGNORECASE) for p in _MEDIA_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        media_dir = config.cache_dir / "media"
        media_dir.mkdir(exist_ok=True)

        try:
            loop = asyncio.get_event_loop()
            audio_path = await loop.run_in_executor(
                None, _download_audio, url, media_dir
            )
            transcript = await loop.run_in_executor(
                None, _transcribe, audio_path
            )
        except (DownloadError, ParseError):
            raise
        except Exception as e:
            raise DownloadError(f"Media fetch failed for {url}: {e}") from e

        content = f"## Transcript\n\n{transcript}"
        return FetchResult(
            url=url,
            source_type="media",
            content=content,
            tables=[],
            metadata={"audio_path": str(audio_path)},
            raw_path=audio_path,
        )
