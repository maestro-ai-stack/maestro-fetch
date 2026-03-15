"""Cache management — `mfetch cache list|clear`.

Stub for Phase 2 implementation.
"""
from __future__ import annotations

import typer

app = typer.Typer(help="Cache management.")


@app.command("list")
def list_cache() -> None:
    """List cached entries."""
    typer.echo("cache list: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def clear(
    older_than: str = typer.Option(None, "--older-than", help="Remove entries older than (e.g. 7d)"),
) -> None:
    """Clear cached entries."""
    typer.echo(f"cache clear (older_than={older_than}): not yet implemented (Phase 2)")
    raise typer.Exit(code=0)
