"""BinaryAdapter -- streaming download for archives and binary data files.

Responsibility: download any binary/archive/data file via streaming httpx,
with cache-hit detection and progress reporting.

Handles: .zip .gz .tar .bz2 .7z .rar .nc .tiff .tif .geotiff .parquet
         .dta .shp .dbf .prj .cpg .h5 .hdf5 .feather .arrow .npy .npz

Invariants:
  - supports() matches known binary file extensions
  - fetch() streams to disk (never loads full content into memory)
  - Cache hit: if file exists AND Content-Length matches, skip download
  - raw_path always set; content = human-readable summary (not file bytes)
  - Raises DownloadError on HTTP errors or IO failures
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError
from maestro_fetch.core.result import FetchResult

# Binary / archive / geospatial / data science file extensions
_BINARY_PATTERNS = [
    # Archives
    r"\.(zip|gz|bz2|7z|rar|xz|lz4|zst)(\?|$)",
    r"\.tar(\.(gz|bz2|xz|lz4|zst))?(\?|$)",
    # Geospatial
    r"\.(shp|shx|dbf|prj|cpg|sbn|sbx|fbn|fbx|ain|aih|atx|ixs|mxs)(\?|$)",
    r"\.(geojson|topojson|kml|kmz|gpx)(\?|$)",
    r"\.(tif|tiff|geotiff|img|adf|dem|bil|bip|bsq)(\?|$)",
    r"\.nc(\?|$)",  # NetCDF
    r"\.(gdb|gpkg|mdb)(\?|$)",
    # Data science / statistics
    r"\.(parquet|feather|arrow|orc)(\?|$)",
    r"\.(h5|hdf5|hdf)(\?|$)",
    r"\.(dta|sas7bdat|sav|por)(\?|$)",  # Stata, SAS, SPSS
    r"\.(npy|npz|mat|pkl|pickle)(\?|$)",
    r"\.(rds|rda|rdata)(\?|$)",
]

_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB chunks


def _format_size(n_bytes: int) -> str:
    if n_bytes >= 1e9:
        return f"{n_bytes / 1e9:.1f} GB"
    if n_bytes >= 1e6:
        return f"{n_bytes / 1e6:.1f} MB"
    return f"{n_bytes / 1e3:.1f} KB"


class BinaryAdapter(BaseAdapter):
    """Streams binary/archive/data files to disk with cache detection."""

    def supports(self, url: str) -> bool:
        return any(re.search(p, url, re.IGNORECASE) for p in _BINARY_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        filename = self._filename_from_url(url)
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = config.cache_dir / filename

        # --- cache hit check ---
        cached_size = raw_path.stat().st_size if raw_path.exists() else -1
        remote_size = await self._head_content_length(url, config)

        if cached_size > 0 and (remote_size is None or cached_size == remote_size):
            size_str = _format_size(cached_size)
            print(f"[cache hit] {filename} ({size_str})", file=sys.stderr)
            return FetchResult(
                url=url,
                source_type="binary",
                content=f"[cached] {filename}  {size_str}",
                tables=[],
                metadata={"filename": filename, "size_bytes": cached_size, "cached": True},
                raw_path=raw_path,
            )

        # --- streaming download (with resume support) ---
        # Attempt Range resume if partial file exists and remote supports it.
        # Falls back to fresh download if server returns 200 (no Range support).
        resume_from = cached_size if cached_size > 0 else 0
        size_str = _format_size(remote_size) if remote_size else "unknown size"
        if resume_from > 0 and remote_size and resume_from < remote_size:
            print(f"[resume] {filename} from {_format_size(resume_from)} / {size_str} ...", file=sys.stderr)
        else:
            resume_from = 0
            print(f"[download] {filename} ({size_str}) ...", file=sys.stderr)

        max_retries = 5
        for attempt in range(max_retries):
            try:
                headers = dict(config.headers or {})
                if resume_from > 0:
                    headers["Range"] = f"bytes={resume_from}-"

                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=httpx.Timeout(connect=30.0, read=3600.0, write=60.0, pool=30.0),
                    headers=headers,
                ) as client:
                    async with client.stream("GET", url) as response:
                        if response.status_code == 206:
                            # Server supports Range — append to existing file
                            file_mode = "ab"
                            downloaded = resume_from
                        elif response.status_code == 200:
                            # Server ignored Range header — restart from scratch
                            file_mode = "wb"
                            downloaded = 0
                            resume_from = 0
                        else:
                            raise DownloadError(f"HTTP {response.status_code} for {url}")

                        with raw_path.open(file_mode) as f:
                            async for chunk in response.aiter_bytes(chunk_size=_CHUNK_SIZE):
                                f.write(chunk)
                                downloaded += len(chunk)
                                if remote_size:
                                    pct = downloaded / remote_size * 100
                                    bar = "#" * int(pct / 2)
                                    print(
                                        f"\r  [{bar:<50}] {pct:5.1f}%  "
                                        f"{_format_size(downloaded)} / {_format_size(remote_size)}",
                                        end="",
                                        file=sys.stderr,
                                    )
                        if remote_size:
                            print(file=sys.stderr)  # newline after progress bar
                break  # success — exit retry loop

            except httpx.RequestError as e:
                final_size = raw_path.stat().st_size if raw_path.exists() else 0
                if attempt < max_retries - 1 and final_size > 0:
                    resume_from = final_size
                    print(
                        f"\n[retry {attempt+1}/{max_retries}] {filename} — "
                        f"resuming from {_format_size(resume_from)}",
                        file=sys.stderr,
                    )
                else:
                    raise DownloadError(f"Network error downloading {url}: {e}") from e

        final_size = raw_path.stat().st_size
        print(f"[done] {raw_path}  ({_format_size(final_size)})", file=sys.stderr)

        return FetchResult(
            url=url,
            source_type="binary",
            content=f"{filename}  {_format_size(final_size)}\nSaved to: {raw_path}",
            tables=[],
            metadata={"filename": filename, "size_bytes": final_size, "cached": False},
            raw_path=raw_path,
        )

    @staticmethod
    def _filename_from_url(url: str) -> str:
        """Extract filename from URL, stripping query string."""
        path = url.split("?")[0].rstrip("/")
        return path.split("/")[-1] or "download"

    @staticmethod
    async def _head_content_length(url: str, config: FetchConfig) -> int | None:
        """Try HEAD request to get Content-Length. Returns None if unavailable."""
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=10.0),
                headers=config.headers or {},
            ) as client:
                r = await client.head(url)
                if r.status_code == 200:
                    cl = r.headers.get("content-length")
                    return int(cl) if cl else None
        except Exception:
            pass
        return None
