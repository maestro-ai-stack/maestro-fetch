"""``mfetch tab`` — interact with existing Chrome tabs via extension backend."""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer

app = typer.Typer(help="Interact with existing Chrome tabs.")


def _run(coro):
    return asyncio.run(coro)


def _backend():
    from maestro_fetch.backends.extension import ExtensionBackend

    backend = ExtensionBackend()
    if not _run(backend.is_available()):
        typer.echo(
            "Extension backend not available. "
            "Ensure Chrome + extension + daemon are running.",
            err=True,
        )
        raise typer.Exit(code=1)
    return backend


@app.command("list")
def list_tabs() -> None:
    """List all open Chrome tabs."""
    backend = _backend()
    tabs = _run(backend.list_all_tabs())
    if not tabs:
        typer.echo("No tabs found.")
        return
    for tab in tabs:
        tid = tab.get("tabId", "?")
        url = tab.get("url", "")
        title = tab.get("title", "")
        active = " *" if tab.get("active") else ""
        typer.echo(f"  [{tid}]{active}  {title[:60]}")
        typer.echo(f"         {url[:100]}")


@app.command("find")
def find_tab(
    pattern: str = typer.Argument(..., help="URL or title substring to match"),
) -> None:
    """Find a tab by URL or title substring."""
    backend = _backend()
    tab = _run(backend.find_tab(pattern))
    if not tab:
        typer.echo(f"No tab matching '{pattern}'", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Tab {tab['tabId']}: {tab.get('title', '')}")
    typer.echo(f"URL: {tab.get('url', '')}")


@app.command("snapshot")
def snapshot(
    tab_id: int = typer.Argument(..., help="Tab ID from 'mfetch tab list'"),
) -> None:
    """Get page content as markdown from an existing tab."""
    backend = _backend()
    content = _run(backend.snapshot_tab(tab_id))
    if content:
        typer.echo(content)
    else:
        typer.echo("No content returned", err=True)


@app.command("screenshot")
def screenshot(
    tab_id: int = typer.Argument(..., help="Tab ID"),
    output: str = typer.Option("screenshot.png", "--output", "-o", help="Output file path"),
) -> None:
    """Take a screenshot of an existing tab."""
    backend = _backend()
    png_bytes = _run(backend.screenshot_tab(tab_id))
    out_path = Path(output)
    out_path.write_bytes(png_bytes)
    typer.echo(f"Screenshot saved to {out_path}")


@app.command("fill")
def fill(
    tab_id: int = typer.Argument(..., help="Tab ID"),
    selector: str = typer.Argument(..., help="CSS selector for the input"),
    value: str = typer.Argument(..., help="Value to fill"),
) -> None:
    """Fill a form field in an existing tab."""
    backend = _backend()
    result = _run(backend.fill_tab(tab_id, selector, value))
    typer.echo(result)


@app.command("click")
def click(
    tab_id: int = typer.Argument(..., help="Tab ID"),
    selector: str = typer.Argument(..., help="CSS selector for the element"),
) -> None:
    """Click an element in an existing tab."""
    backend = _backend()
    result = _run(backend.click_tab(tab_id, selector))
    typer.echo(result)


@app.command("type")
def type_text(
    tab_id: int = typer.Argument(..., help="Tab ID"),
    text: str = typer.Argument(..., help="Text to type via CDP keyboard events"),
) -> None:
    """Type text into focused element via real keyboard events (CDP-level).

    Unlike 'fill', this produces real Input.dispatchKeyEvent events that
    JSF/Mojarra and other server-side frameworks recognize.
    Focus the target element first with 'exec' or 'click'.
    """
    backend = _backend()
    result = _run(backend.type_tab(tab_id, text))
    typer.echo(result)


@app.command("exec")
def exec_js(
    tab_id: int = typer.Argument(..., help="Tab ID"),
    code: str = typer.Argument(..., help="JavaScript code to execute"),
) -> None:
    """Execute JavaScript in an existing tab."""
    backend = _backend()
    result = _run(backend.exec_tab(tab_id, code))
    typer.echo(result)
