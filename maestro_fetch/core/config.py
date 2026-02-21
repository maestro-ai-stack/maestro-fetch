from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FetchConfig:
    """Global configuration for a maestro-fetch session.

    Invariants:
    - provider defaults to "anthropic"; model=None means use provider default.
    - output_format is one of "markdown", "json", "text".
    - timeout and max_retries are positive integers.
    """

    provider: str = "anthropic"
    model: str | None = None
    schema: dict | None = None
    output_format: str = "markdown"
    cache_dir: Path = Path(".maestro_cache")
    timeout: int = 60
    max_retries: int = 3
