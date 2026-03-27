"""MediaAdapter -- extracts subtitles or transcribes video/audio to text.

Strategy (fast-first, like WebAdapter):
    1. Try extracting existing subtitles via yt-dlp (no download, ~1-2s)
    2. Fall back to downloading audio + Whisper transcription (~minutes)

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


def _extract_subtitles(url: str, out_dir: Path, langs: list[str] | None = None) -> str | None:
    """Try extracting existing subtitles via yt-dlp (no video download). Returns text or None."""
    try:
        import yt_dlp
    except ImportError:
        return None

    if langs is None:
        langs = ["en", "zh-Hans", "zh", "ja", "ko"]

    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "subtitlesformat": "vtt",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)

    # Find the downloaded .vtt file
    vtt_files = sorted(out_dir.glob("*.vtt"))
    if not vtt_files:
        return None

    # Parse VTT: strip headers, timestamps, and deduplicate repeated lines
    text = vtt_files[0].read_text(encoding="utf-8")
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        if line.isdigit() or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if not lines or line != lines[-1]:
            lines.append(line)

    return " ".join(lines) if lines else None


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
    """Extracts subtitles or transcribes video/audio.

    Strategy (fast-first):
        1. Extract existing subtitles via yt-dlp (~1-2s, no download)
        2. Download audio + Whisper transcription (fallback, ~minutes)
    """

    def supports(self, url: str) -> bool:
        return any(re.search(p, url, re.IGNORECASE) for p in _MEDIA_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        media_dir = config.cache_dir / "media"
        media_dir.mkdir(exist_ok=True)

        loop = asyncio.get_event_loop()

        # --- Tier 1: Extract existing subtitles (fast, no download) ---
        try:
            subtitle_text = await loop.run_in_executor(
                None, _extract_subtitles, url, media_dir, None
            )
            if subtitle_text and len(subtitle_text) > 50:
                return FetchResult(
                    url=url,
                    source_type="media",
                    content=f"## Subtitles\n\n{subtitle_text}",
                    tables=[],
                    metadata={"method": "subtitles"},
                )
        except Exception:
            pass  # Fall through to audio transcription

        # --- Tier 2: Download audio + Whisper transcription (slow) ---
        try:
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

        return FetchResult(
            url=url,
            source_type="media",
            content=f"## Transcript\n\n{transcript}",
            tables=[],
            metadata={"method": "whisper", "audio_path": str(audio_path)},
            raw_path=audio_path,
        )
