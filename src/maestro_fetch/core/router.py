"""URL Router -- regex-based source type detection.

Responsibility: classify a URL into a source type string.
Inputs: a single URL string.
Outputs: one of "binary", "cloud", "doc", "media", "web".
Invariants: always returns a valid type; defaults to "web".
"""
from __future__ import annotations

import re

_RULES: list[tuple[str, str]] = [
    # Baidu Pan (must precede generic cloud rules)
    (r"pan\.baidu\.com/", "baidu_pan"),
    # Cloud storage (domain-based — check before extension rules)
    (r"dropbox\.com/", "cloud"),
    (r"drive\.google\.com/", "cloud"),
    (r"docs\.google\.com/", "cloud"),
    # Media (domain-based)
    (r"youtube\.com/watch", "media"),
    (r"youtu\.be/", "media"),
    (r"vimeo\.com/", "media"),
    # Email (before generic documents)
    (r"\.(eml|msg)(\?|$)", "email"),
    # Parseable documents (extension-based)
    (r"\.pdf(\?|$)", "doc"),
    (r"\.(xlsx|xls|ods)(\?|$)", "doc"),
    (r"\.(csv|tsv)(\?|$)", "doc"),
    (r"\.jsonl?(\?|$)", "doc"),
    # Binary / archive / geospatial / data science (stream to disk)
    (r"\.(zip|gz|bz2|7z|rar|xz|lz4|zst)(\?|$)", "binary"),
    (r"\.tar(\.(gz|bz2|xz|lz4|zst))?(\?|$)", "binary"),
    (r"\.(shp|shx|dbf|prj|cpg|sbn|sbx)(\?|$)", "binary"),
    (r"\.(geojson|topojson|kml|kmz|gpx)(\?|$)", "binary"),
    (r"\.(tif|tiff|geotiff|img|adf|dem|bil)(\?|$)", "binary"),
    (r"\.nc(\?|$)", "binary"),
    (r"\.(gpkg|gdb|mdb)(\?|$)", "binary"),
    (r"\.(parquet|feather|arrow|orc)(\?|$)", "binary"),
    (r"\.(h5|hdf5|hdf)(\?|$)", "binary"),
    (r"\.(dta|sas7bdat|sav|por)(\?|$)", "binary"),
    (r"\.(npy|npz|mat|pkl|pickle)(\?|$)", "binary"),
    (r"\.(rds|rda|rdata)(\?|$)", "binary"),
]


def _extract_embedded_filename(url: str) -> str:
    """Extract filename embedded in query parameters (e.g. ABS openagent URLs).

    ABS subscriber URLs look like:
      .../log?openagent&some_file.zip&...&Latest
    The filename is the first query token that contains a file extension.
    Returns empty string if none found.
    """
    q = url.split("?", 1)
    if len(q) < 2:
        return ""
    for token in q[1].split("&"):
        if re.search(r"\.[a-z0-9]{2,8}$", token, re.IGNORECASE):
            return token
    return ""


def detect_type(url: str) -> str:
    """Return source type string for URL. Falls back to 'web'.

    Also checks filenames embedded inside query strings (e.g. ABS openagent
    subscriber URLs where the filename appears as a query parameter token).
    """
    for pattern, source_type in _RULES:
        if re.search(pattern, url, re.IGNORECASE):
            return source_type
    # Fallback: check for filename embedded in query params
    embedded = _extract_embedded_filename(url)
    if embedded:
        for pattern, source_type in _RULES:
            if re.search(pattern, embedded, re.IGNORECASE):
                return source_type
    return "web"
