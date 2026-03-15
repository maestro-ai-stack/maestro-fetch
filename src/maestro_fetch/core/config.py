from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path

# tomllib is stdlib in 3.11+; fall back to tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError as exc:
        msg = "Install 'tomli' for Python < 3.11: pip install tomli"
        raise ImportError(msg) from exc

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path.home() / ".maestro-fetch"
CONFIG_PATH = BASE_DIR / "config.toml"
CACHE_DB_PATH = BASE_DIR / "cache.db"
CACHE_DIR = BASE_DIR / "cache"

# ---------------------------------------------------------------------------
# Default configuration (mirrors config.toml structure)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "cache": {
        "dir": str(CACHE_DIR),
        "default_ttl": "1d",
        "max_size": "5GB",
    },
    "browser": {
        "bb_browser": True,
        "playwright": True,
    },
    "sources": {
        "repo": "maestro-ai-stack/maestro-fetch-sources",
        "auto_update": True,
        "custom_dir": str(BASE_DIR / "custom"),
    },
    "output": {
        "format": "markdown",
    },
    "backends": {
        "priority": ["bb-browser", "cloudflare", "playwright"],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: Path | None = None) -> dict:
    """Load TOML configuration, falling back to defaults.

    Resolution order:
    1. DEFAULT_CONFIG (always present)
    2. ~/.maestro-fetch/config.toml (if it exists)
    3. Explicit *path* override (if provided)
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    # Layer 1 – default location
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as f:
            user_cfg = tomllib.load(f)
        config = _deep_merge(config, user_cfg)

    # Layer 2 – explicit override
    if path is not None and path.exists():
        with path.open("rb") as f:
            override_cfg = tomllib.load(f)
        config = _deep_merge(config, override_cfg)

    return config


def write_default_config(path: Path | None = None) -> Path:
    """Write the default config.toml to disk and return its path."""
    dest = path or CONFIG_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# maestro-fetch configuration",
        "# https://github.com/maestro-ai-stack/maestro-fetch",
        "",
        "[cache]",
        f'dir = "{CACHE_DIR}"',
        'default_ttl = "1d"',
        'max_size = "5GB"',
        "",
        "[browser]",
        "bb_browser = true",
        "playwright = true",
        "",
        "[sources]",
        'repo = "maestro-ai-stack/maestro-fetch-sources"',
        "auto_update = true",
        f'custom_dir = "{BASE_DIR / "custom"}"',
        "",
        "[output]",
        'format = "markdown"',
        "",
        "[backends]",
        'priority = ["bb-browser", "cloudflare", "playwright"]',
        "",
    ]
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# FetchConfig dataclass (existing)
# ---------------------------------------------------------------------------


@dataclass
class FetchConfig:
    """Global configuration for a maestro-fetch session.

    Invariants:
    - provider defaults to "anthropic"; model=None means use provider default.
    - output_format is one of "markdown", "json", "text".
    - timeout and max_retries are positive integers.
    - headers/cookies are passed through to HTTP clients (httpx, crawl4ai).
    """

    provider: str = "anthropic"
    model: str | None = None
    schema: dict | None = None
    output_format: str = "markdown"
    cache_dir: Path = CACHE_DIR
    timeout: int = 60
    max_retries: int = 3
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
