from typer.testing import CliRunner
from unittest.mock import patch
from maestro_fetch.interfaces.cli import app
from maestro_fetch.core.result import FetchResult

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "fetch" in result.output.lower()


def test_fetch_command_calls_sdk(tmp_path):
    mock_result = FetchResult(
        url="https://example.com",
        source_type="web",
        content="# Hello",
        tables=[],
    )
    with patch("maestro_fetch.interfaces.cli.asyncio") as mock_asyncio:
        mock_asyncio.run.return_value = mock_result
        result = runner.invoke(app, ["https://example.com", "--output", "markdown"])
    assert result.exit_code == 0
