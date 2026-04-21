from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from typer.testing import CliRunner

from maestro_fetch.cli.do_cmd import _extension_agent_loop, _parse_json_action, app

runner = CliRunner()


def test_parse_json_action_extracts_code_block() -> None:
    action = _parse_json_action("```json\n{\"action\":\"done\",\"success\":true}\n```")
    assert action == {"action": "done", "success": True}


def test_do_command_prints_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "maestro_fetch.cli.do_cmd._extension_agent_loop",
        AsyncMock(return_value={"success": True, "result": "done"}),
    )

    result = runner.invoke(app, ['open billing page', '--url', 'https://example.com'])
    assert result.exit_code == 0
    assert "done" in result.output


def test_do_command_exits_nonzero_on_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "maestro_fetch.cli.do_cmd._extension_agent_loop",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = runner.invoke(app, ['open billing page'])
    assert result.exit_code == 1
    assert "Error: boom" in result.output


@pytest.mark.asyncio
async def test_extension_agent_loop_runs_multi_step_plan(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.is_available = AsyncMock(return_value=True)
    backend.navigate = AsyncMock()
    backend.eval_js = AsyncMock(side_effect=["page text", "clicked", "final page"])

    responses = iter(
        [
            '{"action":"exec","code":"document.body.click()"}',
            '{"action":"read"}',
            '{"action":"done","success":true,"result":"ok"}',
        ]
    )

    async def fake_llm(_messages):
        return next(responses)

    monkeypatch.setattr("maestro_fetch.backends.extension.ExtensionBackend", lambda: backend)
    monkeypatch.setattr("maestro_fetch.cli.do_cmd._get_llm_caller", lambda _model: fake_llm)

    result = await _extension_agent_loop("click", "https://example.com", "model", 30)
    assert result["success"] is True
    assert result["result"] == "ok"
    backend.navigate.assert_awaited_once_with("https://example.com")
