"""URL Router -- regex-based source type detection.

Responsibility: classify a URL into a source type string.
Inputs: a single URL string.
Outputs: one of "cloud", "media", "doc", "web".
Invariants: always returns a valid type; defaults to "web".
"""
from __future__ import annotations

import re

_RULES: list[tuple[str, str]] = [
    (r"dropbox\.com/", "cloud"),
    (r"drive\.google\.com/", "cloud"),
    (r"docs\.google\.com/", "cloud"),
    (r"youtube\.com/watch", "media"),
    (r"youtu\.be/", "media"),
    (r"vimeo\.com/", "media"),
    (r"\.pdf(\?|$)", "doc"),
    (r"\.(xlsx|xls|ods)(\?|$)", "doc"),
    (r"\.csv(\?|$)", "doc"),
]


def detect_type(url: str) -> str:
    """Return source type string for URL. Falls back to 'web'."""
    for pattern, source_type in _RULES:
        if re.search(pattern, url, re.IGNORECASE):
            return source_type
    return "web"
