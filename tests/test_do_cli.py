from __future__ import annotations

import asyncio
import base64
import copy
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
    backend.type_text = AsyncMock(return_value="typed")
    backend.click_at = AsyncMock(return_value="clicked")
    backend.screenshot_current = AsyncMock(return_value=b"png-bytes")
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


@pytest.mark.asyncio
async def test_extension_agent_loop_enforces_timeout(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.is_available = AsyncMock(return_value=True)
    backend.navigate = AsyncMock()
    backend.eval_js = AsyncMock(return_value="page text")

    async def slow_llm(_messages):
        await asyncio.sleep(0.05)
        return '{"action":"done","success":true,"result":"ok"}'

    monkeypatch.setattr("maestro_fetch.backends.extension.ExtensionBackend", lambda: backend)
    monkeypatch.setattr("maestro_fetch.cli.do_cmd._get_llm_caller", lambda _model: slow_llm)

    with pytest.raises(Exception, match="timed out while waiting for LLM response"):
        await _extension_agent_loop("click", None, "model", 0.01)


@pytest.mark.asyncio
async def test_extension_agent_loop_supports_screenshot_and_native_actions(monkeypatch) -> None:
    backend = type("Backend", (), {})()
    backend.is_available = AsyncMock(return_value=True)
    backend.navigate = AsyncMock()
    backend.eval_js = AsyncMock(return_value="page text")
    backend.screenshot_current = AsyncMock(return_value=b"png-bytes")
    backend.type_text = AsyncMock(return_value="typed")
    backend.click_at = AsyncMock(return_value="clicked")

    seen_message_batches = []
    responses = iter(
        [
            '{"action":"screenshot"}',
            '{"action":"type","text":"hello"}',
            '{"action":"click_at","x":12,"y":34}',
            '{"action":"done","success":true,"result":"ok"}',
        ]
    )

    async def fake_llm(messages):
        seen_message_batches.append(copy.deepcopy(messages))
        return next(responses)

    monkeypatch.setattr("maestro_fetch.backends.extension.ExtensionBackend", lambda: backend)
    monkeypatch.setattr("maestro_fetch.cli.do_cmd._get_llm_caller", lambda _model: fake_llm)

    result = await _extension_agent_loop("interact", None, "model", 30)

    assert result["success"] is True
    backend.screenshot_current.assert_awaited_once()
    backend.type_text.assert_awaited_once_with("hello")
    backend.click_at.assert_awaited_once_with(12, 34)
    screenshot_message = seen_message_batches[1][-1]
    assert screenshot_message["role"] == "user"
    assert screenshot_message["content"][0]["type"] == "text"
    assert screenshot_message["content"][1]["type"] == "image_url"
    assert screenshot_message["content"][1]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii")
    )
