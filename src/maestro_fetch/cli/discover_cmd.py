"""``mfetch discover <url>`` — discover site content via extension backend."""
from __future__ import annotations

import asyncio

import typer

app = typer.Typer(help="Discover site content and structure.")


def _run(coro):
    return asyncio.run(coro)


@app.callback(invoke_without_command=True, context_settings={"allow_interspersed_args": True})
def discover(
    url: str = typer.Argument(..., help="URL to explore"),
) -> None:
    """Fetch and explore a URL via the extension backend."""
    from maestro_fetch.backends.extension import ExtensionBackend

    backend = ExtensionBackend()

    if not _run(backend.is_available()):
        typer.echo(
            "Extension backend not available. "
            "Ensure Chrome is running with the maestro-fetch extension.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Fetching {url} via extension...")
    try:
        content = _run(backend.fetch_content(url))
        if content:
            typer.echo(content)
        else:
            typer.echo("No content returned", err=True)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
