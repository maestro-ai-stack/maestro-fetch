"""``mfetch do "natural language task"`` — direct browser-use execution."""
from __future__ import annotations

import asyncio
import json

import typer

app = typer.Typer(help="Execute natural language browser tasks.")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@app.callback(invoke_without_command=True)
def do(
    task: str = typer.Argument(..., help="Natural language task description"),
    url: str = typer.Option(None, "--url", "-u", help="Starting URL"),
) -> None:
    """Execute a natural language task via browser-use (LLM-driven browser).

    Skips platform registry and routing — sends directly to browser-use.
    """
    from maestro_fetch.backends.browser_use import BrowserUseBackend
    from maestro_fetch.core.config import load_config

    config = load_config()
    backend_cfg = config.get("backends", {}).get("browser-use", {})
    model = backend_cfg.get("model", "claude-sonnet-4-20250514")
    timeout = backend_cfg.get("timeout", 120)

    backend = BrowserUseBackend(model=model, timeout=timeout)

    if not _run(backend.is_available()):
        typer.echo(
            "browser-use is not installed. Install with: pip install 'maestro-fetch[ai-browser]'",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Executing: {task}")
    if url:
        typer.echo(f"Starting at: {url}")

    try:
        result = _run(backend.execute_task(task, url=url))
        content = result.get("result", "")
        if content:
            typer.echo(content)
        else:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
