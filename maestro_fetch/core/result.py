from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class FetchResult:
    """Unified result returned by every fetch adapter.

    Invariants:
    - url and source_type are always set (non-empty strings).
    - tables defaults to empty list; metadata defaults to empty dict.
    - raw_path is None unless the adapter stored a local copy.
    """

    url: str
    source_type: str  # "web" | "pdf" | "excel" | "cloud" | "media" | "image"
    content: str
    tables: list[pd.DataFrame] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw_path: Path | None = None
