"""BinaryAdapter -- streaming download for archives, binary data files, and images.

Responsibility: download any binary/archive/data/image file via streaming httpx,
with cache-hit detection and progress reporting.

Handles: .zip .gz .tar .bz2 .7z .rar .nc .tiff .tif .geotiff .parquet
         .dta .shp .dbf .prj .cpg .h5 .hdf5 .feather .arrow .npy .npz
         .jpg .jpeg .png .gif .webp .bmp .svg .ico .avif .heic .heif

Invariants:
  - supports() matches known binary file extensions
  - fetch() streams to disk (never loads full content into memory)
  - Cache hit: if file exists AND Content-Length matches, skip download
  - raw_path always set; content = human-readable summary (not file bytes)
  - Raises DownloadError on HTTP errors or IO failures
"""
from __future__ import annotations

import asyncio
import re
import sys

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
    # Images
    r"\.(jpg|jpeg|png|gif|webp|bmp|svg|ico|avif|heic|heif)(\?|$)",
]

_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB chunks

# Dataset formats that get a schema/head preview after download
_PREVIEWABLE = {".parquet", ".dta", ".feather", ".arrow", ".orc"}

# Default user-agent for binary downloads.
# Wikimedia and many CDNs block generic or missing UAs, or rate-limit them.
# Wikimedia recommends the format: ClientName/Version (contact_info)
# We provide both a Wikimedia-friendly UA and a browser fallback.
_DEFAULT_UA = "maestro-fetch/1.0 (https://github.com/maestro-ai/maestro; bot)"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _format_size(n_bytes: int) -> str:
    if n_bytes >= 1e9:
        return f"{n_bytes / 1e9:.1f} GB"
    if n_bytes >= 1e6:
        return f"{n_bytes / 1e6:.1f} MB"
    return f"{n_bytes / 1e3:.1f} KB"


def _embedded_filename(url: str) -> str:
    """Extract filename embedded in query parameters (e.g. ABS openagent URLs).

    ABS subscriber URLs look like:
      .../log?openagent&some_file.zip&...&Latest
    Returns the first query token that looks like a filename (has an extension).
    """
    parts = url.split("?", 1)
    if len(parts) < 2:
        return ""
    for token in parts[1].split("&"):
        if re.search(r"\.[a-z0-9]{2,8}$", token, re.IGNORECASE):
            return token
    return ""


def _generate_preview(path, filename: str) -> tuple[str, list]:
    """Generate schema + head preview for dataset files. Returns (markdown, tables)."""
    from pathlib import Path
    ext = Path(filename).suffix.lower()
    if ext not in _PREVIEWABLE:
        return "", []

    try:
        import pandas as pd

        if ext == ".parquet":
            df = pd.read_parquet(path)
        elif ext == ".dta":
            df = pd.read_stata(path)
        elif ext in (".feather", ".arrow"):
            df = pd.read_feather(path)
        elif ext == ".orc":
            df = pd.read_orc(path)
        else:
            return "", []

        rows, cols = df.shape
        size_mb = path.stat().st_size / 1e6

        # Schema table
        schema_rows = []
        for col in df.columns:
            non_null_pct = f"{df[col].notna().mean() * 100:.0f}%"
            first_valid = df[col].dropna().iloc[0] if df[col].notna().any() else ""
            example = str(first_valid)[:40]
            schema_rows.append(f"| {col} | {df[col].dtype} | {non_null_pct} | {example} |")

        schema_md = "| Column | Type | Non-null | Example |\n|--------|------|----------|---------|\n" + "\n".join(schema_rows)

        head_df = df.head(20)
        head_md = head_df.to_markdown(index=False) or ""

        preview = f"## Dataset: {filename}\n\n- **Rows:** {rows:,}\n- **Columns:** {cols}\n- **Size:** {size_mb:.1f} MB\n\n### Schema\n\n{schema_md}\n\n### Head (first {len(head_df)} rows)\n\n{head_md}"
        return preview, [df]

    except Exception as exc:
        print(f"[preview] skipped for {filename}: {exc}", file=sys.stderr)
        return "", []


class BinaryAdapter(BaseAdapter):
    """Streams binary/archive/data files to disk with cache detection."""

    def supports(self, url: str) -> bool:
        if any(re.search(p, url, re.IGNORECASE) for p in _BINARY_PATTERNS):
            return True
        # Also check filenames embedded in query parameters (e.g. ABS openagent URLs)
        embedded = _embedded_filename(url)
        return bool(embedded and any(re.search(p, embedded, re.IGNORECASE) for p in _BINARY_PATTERNS))

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        from pathlib import Path as _Path

        # --- Handle local files ---
        local_path = None
        if url.startswith("file://"):
            local_path = _Path(url.removeprefix("file://"))
        elif not url.startswith(("http://", "https://")) and _Path(url).is_file():
            local_path = _Path(url)

        if local_path and local_path.is_file():
            filename = local_path.name
            size = local_path.stat().st_size
            preview, tables = _generate_preview(local_path, filename)
            content = preview if preview else f"{filename}  {_format_size(size)}\nPath: {local_path}"
            return FetchResult(
                url=url,
                source_type="binary",
                content=content,
                tables=tables,
                metadata={"filename": filename, "size_bytes": size, "cached": False},
                raw_path=local_path,
            )

        filename = self._filename_from_url(url)
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = config.cache_dir / filename

        # --- cache hit check ---
        cached_size = raw_path.stat().st_size if raw_path.exists() else -1
        remote_size = await self._head_content_length(url, config)

        if cached_size > 0 and (remote_size is None or cached_size == remote_size):
            size_str = _format_size(cached_size)
            print(f"[cache hit] {filename} ({size_str})", file=sys.stderr)
            preview, tables = _generate_preview(raw_path, filename)
            content = preview if preview else f"[cached] {filename}  {size_str}"
            return FetchResult(
                url=url,
                source_type="binary",
                content=content,
                tables=tables,
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

        # On the first attempt use a browser UA; rotate to Wikimedia-friendly UA on retry
        _ua_rotation = [_BROWSER_UA, _DEFAULT_UA, _BROWSER_UA, _DEFAULT_UA, _BROWSER_UA]
        max_retries = 5
        for attempt in range(max_retries):
            try:
                headers = dict(config.headers or {})
                # Inject a browser User-Agent if caller didn't supply one.
                # Many CDNs (Wikimedia, etc.) return 403/429 for headless requests.
                headers.setdefault("User-Agent", _ua_rotation[attempt])
                if resume_from > 0:
                    headers["Range"] = f"bytes={resume_from}-"

                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=httpx.Timeout(connect=30.0, read=3600.0, write=60.0, pool=30.0),
                    headers=headers,
                ) as client:
                    async with client.stream("GET", url) as response:
                        if response.status_code == 429:
                            # Rate-limited: honour Retry-After header, capped at 60s
                            raw_retry = response.headers.get("Retry-After", "10")
                            try:
                                retry_after = min(int(raw_retry), 60)
                            except ValueError:
                                retry_after = 10
                            print(
                                f"\n[rate-limit] {filename} — waiting {retry_after}s (attempt {attempt+1}/{max_retries})",
                                file=sys.stderr,
                            )
                            await asyncio.sleep(retry_after)
                            continue
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

        preview, tables = _generate_preview(raw_path, filename)
        content = preview if preview else f"{filename}  {_format_size(final_size)}\nSaved to: {raw_path}"
        return FetchResult(
            url=url,
            source_type="binary",
            content=content,
            tables=tables,
            metadata={"filename": filename, "size_bytes": final_size, "cached": False},
            raw_path=raw_path,
        )

    @staticmethod
    def _filename_from_url(url: str) -> str:
        """Extract filename from URL.

        For standard URLs: use the path component before the query string.
        For ABS-style openagent URLs: the filename is embedded as the first
        query-parameter token that contains a file extension (e.g.
        ``log?openagent&cg_sa2_2011_sa2_2016.zip&...``).
        """
        embedded = _embedded_filename(url)
        if embedded:
            return embedded
        path = url.split("?")[0].rstrip("/")
        return path.split("/")[-1] or "download"

    @staticmethod
    async def _head_content_length(url: str, config: FetchConfig) -> int | None:
        """Try HEAD request to get Content-Length. Returns None if unavailable."""
        try:
            head_headers = dict(config.headers or {})
            head_headers.setdefault("User-Agent", _DEFAULT_UA)
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=10.0),
                headers=head_headers,
            ) as client:
                r = await client.head(url)
                if r.status_code == 200:
                    cl = r.headers.get("content-length")
                    return int(cl) if cl else None
        except Exception:
            pass
        return None
