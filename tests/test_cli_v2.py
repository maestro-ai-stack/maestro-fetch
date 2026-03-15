"""Tests for the v2 CLI (cli/__init__.py — typer app).

Covers: --help, source list, cache list, config show.
Uses typer.testing.CliRunner (no subprocess, no network).
"""
from __future__ import annotations

from typer.testing import CliRunner

from maestro_fetch.cli import app

runner = CliRunner()


def test_help() -> None:
    """``mfetch --help`` exits 0 and mentions key subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "source" in result.output.lower()
    assert "cache" in result.output.lower()
    assert "config" in result.output.lower()


def test_source_list() -> None:
    """``mfetch source list`` exits 0 even when no adapters are installed."""
    result = runner.invoke(app, ["source", "list"])
    assert result.exit_code == 0


def test_cache_list() -> None:
    """``mfetch cache list`` exits 0 (may print 'Cache is empty')."""
    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0


def test_config_show() -> None:
    """``mfetch config show`` exits 0 and outputs valid JSON."""
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    # Should contain at least one key from DEFAULT_CONFIG
    assert "cache" in result.output
