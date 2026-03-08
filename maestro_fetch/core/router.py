"""URL Router -- regex-based source type detection.

Responsibility: classify a URL into a source type string.
Inputs: a single URL string.
Outputs: one of "binary", "cloud", "doc", "media", "web".
Invariants: always returns a valid type; defaults to "web".
"""
from __future__ import annotations

import re

_RULES: list[tuple[str, str]] = [
    # Cloud storage (domain-based — check before extension rules)
    (r"dropbox\.com/", "cloud"),
    (r"drive\.google\.com/", "cloud"),
    (r"docs\.google\.com/", "cloud"),
    # Media (domain-based)
    (r"youtube\.com/watch", "media"),
    (r"youtu\.be/", "media"),
    (r"vimeo\.com/", "media"),
    # Parseable documents (extension-based)
    (r"\.pdf(\?|$)", "doc"),
    (r"\.(xlsx|xls|ods)(\?|$)", "doc"),
    (r"\.csv(\?|$)", "doc"),
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


def detect_type(url: str) -> str:
    """Return source type string for URL. Falls back to 'web'."""
    for pattern, source_type in _RULES:
        if re.search(pattern, url, re.IGNORECASE):
            return source_type
    return "web"
