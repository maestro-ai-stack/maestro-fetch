from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from maestro_fetch.cli.tab_cmd import app

runner = CliRunner()


def test_tab_list_renders_rows(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.list_all_tabs = AsyncMock(
        return_value=[
            {
                "tabId": 7,
                "url": "https://example.com",
                "title": "Example Domain",
                "active": True,
            }
        ]
    )
    monkeypatch.setattr("maestro_fetch.cli.tab_cmd._backend", lambda: backend)

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "[7]" in result.output
    assert "Example Domain" in result.output


def test_tab_find_returns_error_when_missing(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.find_tab = AsyncMock(return_value=None)
    monkeypatch.setattr("maestro_fetch.cli.tab_cmd._backend", lambda: backend)

    result = runner.invoke(app, ["find", "missing"])
    assert result.exit_code == 1
    assert "No tab matching" in result.output


def test_tab_screenshot_writes_file(monkeypatch, tmp_path: Path) -> None:
    backend = type("Backend", (), {})()
    backend.screenshot_tab = AsyncMock(return_value=b"png-bytes")
    monkeypatch.setattr("maestro_fetch.cli.tab_cmd._backend", lambda: backend)

    out = tmp_path / "shot.png"
    result = runner.invoke(app, ["screenshot", "9", "--output", str(out)])
    assert result.exit_code == 0
    assert out.read_bytes() == b"png-bytes"


def test_tab_type_calls_backend(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.type_tab = AsyncMock(return_value="typed")
    monkeypatch.setattr("maestro_fetch.cli.tab_cmd._backend", lambda: backend)

    result = runner.invoke(app, ["type", "5", "hello"])
    assert result.exit_code == 0
    assert "typed" in result.output


def test_tab_fill_returns_nonzero_when_selector_missing(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.fill_tab = AsyncMock(return_value='selector not found: [id="missing"]')
    monkeypatch.setattr("maestro_fetch.cli.tab_cmd._backend", lambda: backend)

    result = runner.invoke(app, ["fill", "5", '[id="missing"]', "hello"])
    assert result.exit_code == 1
    assert "Fill failed: selector not found" in result.output


def test_tab_click_returns_nonzero_when_selector_missing(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.click_tab = AsyncMock(return_value='selector not found: [id="missing"]')
    monkeypatch.setattr("maestro_fetch.cli.tab_cmd._backend", lambda: backend)

    result = runner.invoke(app, ["click", "5", '[id="missing"]'])
    assert result.exit_code == 1
    assert "Click failed: selector not found" in result.output
