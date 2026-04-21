"""Tests for configuration (core/config.py).

Covers: defaults, loading with/without file, write/read roundtrip.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from maestro_fetch.core.config import (
    DEFAULT_CONFIG,
    load_config,
    write_default_config,
)


def test_default_config() -> None:
    """DEFAULT_CONFIG contains sensible top-level sections."""
    assert "cache" in DEFAULT_CONFIG
    assert "browser" in DEFAULT_CONFIG
    assert "sources" in DEFAULT_CONFIG
    assert "output" in DEFAULT_CONFIG
    assert "backends" in DEFAULT_CONFIG
    # Specific defaults
    assert DEFAULT_CONFIG["cache"]["default_ttl"] == "1d"
    assert DEFAULT_CONFIG["output"]["format"] == "markdown"
    assert isinstance(DEFAULT_CONFIG["backends"]["priority"], list)


def test_load_config_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no config.toml exists, load_config returns defaults."""
    # Point CONFIG_PATH to a non-existent file so it falls through
    fake_path = tmp_path / "nonexistent" / "config.toml"
    monkeypatch.setattr("maestro_fetch.core.config.CONFIG_PATH", fake_path)

    config = load_config()
    assert config["cache"]["default_ttl"] == "1d"
    assert config["output"]["format"] == "markdown"


def test_load_config_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """User TOML overrides are deep-merged with defaults."""
    toml_file = tmp_path / "config.toml"
    toml_file.write_text(
        '[cache]\ndefault_ttl = "7d"\n\n[output]\nformat = "json"\n',
        encoding="utf-8",
    )
    # Prevent the global CONFIG_PATH from interfering
    monkeypatch.setattr(
        "maestro_fetch.core.config.CONFIG_PATH",
        tmp_path / "no_such_global.toml",
    )

    config = load_config(path=toml_file)
    assert config["cache"]["default_ttl"] == "7d"
    assert config["output"]["format"] == "json"
    # Un-overridden keys still present
    assert "browser" in config
    assert config["backends"]["priority"] == ["extension"]


def test_write_default_config(tmp_path: Path) -> None:
    """write_default_config writes a valid TOML that can be re-read."""
    dest = tmp_path / "config.toml"
    returned = write_default_config(path=dest)
    assert returned == dest
    assert dest.exists()

    # Re-read through load_config (explicit path override)
    # Monkeypatch CONFIG_PATH to avoid picking up the real file
    import maestro_fetch.core.config as cfg_mod

    original = cfg_mod.CONFIG_PATH
    try:
        cfg_mod.CONFIG_PATH = tmp_path / "nope.toml"
        config = load_config(path=dest)
    finally:
        cfg_mod.CONFIG_PATH = original

    assert config["cache"]["default_ttl"] == "1d"
    assert config["output"]["format"] == "markdown"
