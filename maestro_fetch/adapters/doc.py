"""DocAdapter -- fetches and parses document files (PDF, Excel, CSV).

Responsibility: download document from URL, parse into text + tables.
Inputs: URL pointing to a .pdf/.xlsx/.xls/.ods/.csv file, FetchConfig.
Outputs: FetchResult with extracted text content and structured tables.
Invariants:
  - supports() matches only document file extensions
  - fetch() always returns FetchResult or raises DownloadError/ParseError
  - PDF parsing: tries docling first, falls back to pdfplumber
Failure modes: DownloadError on network/HTTP errors, ParseError on bad content.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import httpx
import pandas as pd

from maestro_fetch.adapters.base import BaseAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.errors import DownloadError, ParseError
from maestro_fetch.core.result import FetchResult

_DOC_PATTERNS = [
    r"\.pdf(\?|$)",
    r"\.(xlsx|xls|ods)(\?|$)",
    r"\.csv(\?|$)",
]


def _parse_excel(content: bytes) -> tuple[str, list[pd.DataFrame]]:
    """Parse Excel bytes into markdown text and a list of DataFrames."""
    df = pd.read_excel(io.BytesIO(content))
    return df.to_markdown(index=False) or "", [df]


def _parse_csv(content: bytes) -> tuple[str, list[pd.DataFrame]]:
    """Parse CSV bytes into markdown text and a list of DataFrames."""
    df = pd.read_csv(io.BytesIO(content))
    return df.to_markdown(index=False) or "", [df]


def _parse_pdf(content: bytes) -> tuple[str, list[pd.DataFrame]]:
    """Parse PDF bytes. Tries docling first; falls back to pdfplumber."""
    try:
        from docling.document_converter import DocumentConverter
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(content)
            tmp_path = f.name
        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            text = result.document.export_to_markdown()
            tables: list[pd.DataFrame] = []
            for table in result.document.tables:
                df = table.export_to_dataframe()
                if df is not None:
                    tables.append(df)
            return text, tables
        finally:
            os.unlink(tmp_path)
    except ImportError:
        import pdfplumber

        tables = []
        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                for table_data in page.extract_tables():
                    if table_data:
                        df = pd.DataFrame(table_data[1:], columns=table_data[0])
                        tables.append(df)
        return "\n".join(text_parts), tables


class DocAdapter(BaseAdapter):
    """Parses PDF (via Docling/pdfplumber), Excel, and CSV files from URLs."""

    def supports(self, url: str) -> bool:
        return any(re.search(p, url, re.IGNORECASE) for p in _DOC_PATTERNS)

    async def fetch(self, url: str, config: FetchConfig) -> FetchResult:
        content = await self._download(url, config)
        filename = url.split("?")[0].rstrip("/").split("/")[-1]
        ext = Path(filename).suffix.lower()
        text, tables = self._parse(content, filename, ext)

        config.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = config.cache_dir / filename
        raw_path.write_bytes(content)

        return FetchResult(
            url=url,
            source_type="doc",
            content=text,
            tables=tables,
            metadata={"filename": filename, "ext": ext},
            raw_path=raw_path,
        )

    @staticmethod
    async def _download(url: str, config: FetchConfig) -> bytes:
        """Download file content from URL. Raises DownloadError on failure."""
        try:
            client_kwargs: dict = dict(
                follow_redirects=True, timeout=config.timeout
            )
            if config.headers:
                client_kwargs["headers"] = config.headers
            if config.cookies:
                client_kwargs["cookies"] = config.cookies
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    raise DownloadError(f"HTTP {response.status_code} for {url}")
                return response.content
        except httpx.RequestError as e:
            raise DownloadError(f"Network error: {e}") from e

    @staticmethod
    def _parse(
        content: bytes, filename: str, ext: str
    ) -> tuple[str, list[pd.DataFrame]]:
        """Dispatch to the correct parser based on file extension."""
        try:
            if ext == ".pdf":
                return _parse_pdf(content)
            if ext in (".xlsx", ".xls", ".ods"):
                return _parse_excel(content)
            if ext == ".csv":
                return _parse_csv(content)
            # Unknown doc type: treat as raw text
            return content.decode("utf-8", errors="replace"), []
        except Exception as e:
            raise ParseError(f"Failed to parse {filename}: {e}") from e
