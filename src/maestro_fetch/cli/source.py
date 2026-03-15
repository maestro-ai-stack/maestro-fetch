"""Source adapter management — `mfetch source update|list|info|run`.

Stub for Phase 2 implementation.
"""
from __future__ import annotations

import typer

app = typer.Typer(help="Manage source adapters.")


@app.command()
def update() -> None:
    """Pull latest community source adapters."""
    typer.echo("source update: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command("list")
def list_sources(
    category: str = typer.Option(None, "--category", help="Filter by category"),
) -> None:
    """List available source adapters."""
    typer.echo(f"source list (category={category}): not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def info(name: str = typer.Argument(..., help="Adapter name (e.g. worldbank/gdp)")) -> None:
    """Show details for a source adapter."""
    typer.echo(f"source info {name}: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def run(
    name: str = typer.Argument(..., help="Adapter name"),
    args: list[str] = typer.Argument(None, help="Adapter arguments"),
) -> None:
    """Execute a source adapter."""
    typer.echo(f"source run {name} {args}: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)
