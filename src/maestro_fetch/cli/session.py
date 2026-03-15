"""Interactive browser sessions — `mfetch session start|click|fill|snapshot|end`.

Stub for Phase 2 implementation.
"""
from __future__ import annotations

import typer

app = typer.Typer(help="Interactive browser sessions.")


@app.command()
def start(url: str = typer.Argument(..., help="URL to open")) -> None:
    """Start a new browser session."""
    typer.echo(f"session start {url}: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def click(selector: str = typer.Argument(..., help="CSS selector")) -> None:
    """Click an element in the active session."""
    typer.echo(f"session click {selector}: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def fill(
    selector: str = typer.Argument(..., help="CSS selector"),
    text: str = typer.Argument(..., help="Text to fill"),
) -> None:
    """Fill a form field in the active session."""
    typer.echo(f"session fill {selector} '{text}': not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def snapshot() -> None:
    """Capture current page as markdown."""
    typer.echo("session snapshot: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def screenshot() -> None:
    """Take a screenshot of the active session."""
    typer.echo("session screenshot: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command("eval")
def eval_js(js: str = typer.Argument(..., help="JavaScript to evaluate")) -> None:
    """Evaluate JavaScript in the active session."""
    typer.echo(f"session eval '{js}': not yet implemented (Phase 2)")
    raise typer.Exit(code=0)


@app.command()
def end() -> None:
    """End the active browser session."""
    typer.echo("session end: not yet implemented (Phase 2)")
    raise typer.Exit(code=0)
