"""Screen recorder — capture page scrolling as MP4 video.

Uses Playwright screenshot loop + ffmpeg encoding.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)


@dataclass
class RecordConfig:
    """Configuration for a single page recording."""
    url: str
    duration: float = 10.0
    fps: int = 30
    scroll_mode: Literal["auto", "none", "script"] = "auto"
    scroll_speed: float = 1.0  # pixels per frame
    width: int = 1920
    height: int = 1080
    output: str = "recording.mp4"
    scroll_script: str = ""  # custom JS for scroll_mode="script"


def _require_ffmpeg() -> str:
    """Find ffmpeg binary or raise."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found. Install via: brew install ffmpeg")
    return path


def _encode_frames(frames_dir: Path, output: Path, fps: int) -> None:
    """Encode PNG frames to H.264 MP4 using ffmpeg."""
    ffmpeg = _require_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-c:v", "libx264",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]
    log.info("Encoding: %s", " ".join(cmd[:6]))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")


async def record_page(config: RecordConfig) -> Path:
    """Record a single page as MP4 via Playwright screenshot loop.

    Returns path to the output MP4 file.
    """
    import asyncio
    from playwright.async_api import async_playwright

    output = Path(config.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    frames_dir = Path(tempfile.mkdtemp(prefix="mfetch_rec_"))
    total_frames = int(config.duration * config.fps)
    frame_interval = 1.0 / config.fps

    log.info(
        "Recording %s — %d frames @ %d fps (%0.1fs)",
        config.url, total_frames, config.fps, config.duration,
    )

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": config.width, "height": config.height},
        )
        await page.goto(config.url, wait_until="networkidle", timeout=30_000)
        await asyncio.sleep(1)  # let animations settle

        # Calculate scroll parameters
        if config.scroll_mode == "auto":
            scroll_height = await page.evaluate(
                "document.documentElement.scrollHeight - window.innerHeight"
            )
            pixels_per_frame = scroll_height / max(total_frames - 1, 1) * config.scroll_speed
        else:
            pixels_per_frame = 0

        for i in range(total_frames):
            frame_start = time.monotonic()

            # Screenshot
            frame_path = frames_dir / f"frame_{i:06d}.png"
            await page.screenshot(path=str(frame_path))

            # Scroll
            if config.scroll_mode == "auto" and pixels_per_frame > 0:
                await page.evaluate(f"window.scrollBy(0, {pixels_per_frame})")
            elif config.scroll_mode == "script" and config.scroll_script:
                await page.evaluate(config.scroll_script)

            # Maintain frame rate
            elapsed = time.monotonic() - frame_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            if (i + 1) % config.fps == 0:
                log.info("  frame %d/%d", i + 1, total_frames)

        await browser.close()
    finally:
        await pw.stop()

    # Encode to MP4
    _encode_frames(frames_dir, output, config.fps)

    # Cleanup frames
    shutil.rmtree(frames_dir, ignore_errors=True)

    size_mb = output.stat().st_size / (1024 * 1024)
    log.info("Recorded: %s (%.1f MB)", output, size_mb)
    return output


async def record_batch(
    urls: list[str],
    output_dir: str,
    *,
    duration: float = 5.0,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    scroll_mode: Literal["auto", "none", "script"] = "auto",
) -> dict[str, Any]:
    """Record multiple pages, producing {name}.mp4 + manifest.json.

    URL list can contain plain URLs or "name=url" pairs.
    Returns the manifest dict.
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {"clips": [], "settings": {
        "duration": duration, "fps": fps, "width": width, "height": height,
    }}

    for entry in urls:
        entry = entry.strip()
        if not entry or entry.startswith("#"):
            continue

        # Parse "name=url" or just "url"
        if "=" in entry and not entry.startswith("http"):
            name, _, url = entry.partition("=")
            name = name.strip()
            url = url.strip()
        else:
            url = entry
            # Derive name from URL path
            from urllib.parse import urlparse
            parsed = urlparse(url)
            name = Path(parsed.path).stem or "page"

        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        output_file = out / f"{safe_name}.mp4"

        config = RecordConfig(
            url=url,
            duration=duration,
            fps=fps,
            width=width,
            height=height,
            scroll_mode=scroll_mode,
            output=str(output_file),
        )

        log.info("Recording [%s] %s", safe_name, url)
        try:
            result_path = await record_page(config)
            manifest["clips"].append({
                "name": safe_name,
                "url": url,
                "file": result_path.name,
                "duration": duration,
            })
        except Exception as e:
            log.error("Failed to record %s: %s", url, e)
            manifest["clips"].append({
                "name": safe_name,
                "url": url,
                "file": None,
                "error": str(e),
            })

    # Write manifest
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    log.info("Manifest: %s (%d clips)", manifest_path, len(manifest["clips"]))

    return manifest
