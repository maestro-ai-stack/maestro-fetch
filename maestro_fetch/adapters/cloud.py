"""CloudAdapter -- fetches files from public Dropbox and Google Drive share links.

Responsibility: convert share URLs to direct-download URLs, download the content,
parse tabular formats (CSV, Excel) into DataFrames.

Inputs: public share URL (Dropbox or GDrive), FetchConfig
Outputs: FetchResult with parsed tables and cached raw file
Invariants:
  - supports() matches only known cloud domains
  - fetch() always returns FetchResult or raises DownloadError
Failure modes: network errors, non-200 HTTP, unparseable content
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import httpx
import pandas as pd

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError
from maestro_fetch.core.result import FetchResult

_CLOUD_PATTERNS = [
    r"dropbox\.com/",
    r"drive\.google\.com/",
    r"docs\.google\.com/",
]


_GDOC_EXPORT = {
    "document": ("txt", "text/plain"),
    "spreadsheets": ("csv", "text/csv"),
    "presentation": ("pdf", "application/pdf"),
}


def _to_direct_url(url: str) -> str:
    """Convert a share URL to a direct-download URL.

    Dropbox: replace dl=0 with dl=1, or append dl=1.
    GDrive file:  extract file ID and build /uc?export=download link.
    Google Docs/Sheets/Slides: build /export?format= link.
    """
    if "dropbox.com" in url:
        if "dl=0" in url:
            return url.replace("dl=0", "dl=1")
        if "?" in url:
            return url + "&dl=1"
        return url + "?dl=1"

    gdoc_match = re.search(
        r"docs\.google\.com/(document|spreadsheets|presentation)/d/([^/]+)", url
    )
    if gdoc_match:
        doc_type = gdoc_match.group(1)
        doc_id = gdoc_match.group(2)
        fmt = _GDOC_EXPORT[doc_type][0]
        return f"https://docs.google.com/{doc_type}/d/{doc_id}/export?format={fmt}"

    gdrive_match = re.search(r"/file/d/([^/]+)", url)
    if gdrive_match:
        file_id = gdrive_match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    return url


def _extract_filename(url: str) -> str:
    """Extract a plausible filename from the URL path."""
    gdoc_match = re.search(
        r"docs\.google\.com/(document|spreadsheets|presentation)/d/([^/]+)", url
    )
    if gdoc_match:
        doc_type = gdoc_match.group(1)
        doc_id = gdoc_match.group(2)
        ext = _GDOC_EXPORT[doc_type][0]
        return f"{doc_id}.{ext}"
    return url.split("?")[0].rstrip("/").split("/")[-1] or "download"


def _parse_content(content: bytes, filename: str) -> tuple[str, list[pd.DataFrame]]:
    """Parse downloaded bytes into markdown text and DataFrames.

    Supports CSV and Excel. Other formats fall back to UTF-8 decode.
    """
    ext = Path(filename).suffix.lower()
    tables: list[pd.DataFrame] = []
    text = ""

    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(content))
        tables = [df]
        text = df.to_markdown(index=False)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(io.BytesIO(content))
        tables = [df]
        text = df.to_markdown(index=False)
    else:
        text = content.decode("utf-8", errors="replace")

    return text, tables


class CloudAdapter(BaseAdapter):
    """Downloads files from public Dropbox and Google Drive share links."""

    def supports(self, url: str) -> bool:
        return any(re.search(p, url, re.IGNORECASE) for p in _CLOUD_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        direct_url = _to_direct_url(url)

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=config.timeout
            ) as client:
                response = await client.get(direct_url)
                if response.status_code != 200:
                    raise DownloadError(f"HTTP {response.status_code} for {url}")
                content = response.content
        except httpx.RequestError as e:
            raise DownloadError(f"Network error fetching {url}: {e}") from e

        filename = _extract_filename(url)
        text, tables = _parse_content(content, filename)

        config.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = config.cache_dir / filename
        raw_path.write_bytes(content)

        return FetchResult(
            url=url,
            source_type="cloud",
            content=text,
            tables=tables,
            metadata={"direct_url": direct_url, "filename": filename},
            raw_path=raw_path,
        )
