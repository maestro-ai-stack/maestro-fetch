"""``mfetch discover <url>`` — discover site APIs via opencli explore + synthesize."""
from __future__ import annotations

import asyncio

import typer

app = typer.Typer(help="Discover site APIs and available commands.")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@app.callback(invoke_without_command=True)
def discover(
    url: str = typer.Argument(..., help="URL to explore"),
    task: str = typer.Option(None, "--task", "-t", help="Optional task for pipeline synthesis"),
) -> None:
    """Discover available APIs and commands for a website via opencli."""
    from maestro_fetch.backends.opencli import OpencliBackend

    backend = OpencliBackend()

    if not _run(backend.is_available()):
        typer.echo("opencli is not installed. Install with: npm install -g @jackwener/opencli", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Exploring {url}...")
    try:
        result = _run(backend.explore(url))
        output = result.get("output", "")
        if output:
            typer.echo(output)
        else:
            import json

            typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        typer.echo(f"Error exploring: {e}", err=True)
        raise typer.Exit(code=1)

    if task:
        typer.echo(f"\nSynthesizing pipeline for: {task}")
        try:
            syn_result = _run(backend.synthesize(url, task))
            syn_output = syn_result.get("output", "")
            if syn_output:
                typer.echo(syn_output)
            else:
                import json

                typer.echo(json.dumps(syn_result, indent=2, ensure_ascii=False))
        except Exception as e:
            typer.echo(f"Error synthesizing: {e}", err=True)
            raise typer.Exit(code=1)
