"""Source adapter management -- ``mfetch source update|list|info|run``.

Wires the source loader into the CLI so users can discover, inspect,
and execute community adapters from maestro-fetch-sources.
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import typer

from maestro_fetch.sources.loader import (
    SourceAdapter,
    SourceContext,
    load_sources,
    run_adapter,
)

app = typer.Typer(help="Manage source adapters.")

_SOURCES_REPO = "https://github.com/maestro-ai-stack/maestro-fetch.git"
_BASE_DIR = Path.home() / ".maestro-fetch"
_SOURCES_DIR = _BASE_DIR / "sources"
_CUSTOM_DIR = _BASE_DIR / "custom"
_BUNDLED_DIR = Path(__file__).resolve().parent.parent / "sources" / "community"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_dirs() -> list[Path]:
    """Return source directories in priority order (custom > external > bundled)."""
    return [_CUSTOM_DIR, _SOURCES_DIR, _BUNDLED_DIR]


def _find_adapter(name: str) -> SourceAdapter | None:
    """Look up an adapter by name across custom, external, and bundled dirs."""
    for directory in _source_dirs():
        adapters = load_sources(directory)
        for adapter in adapters:
            if adapter.meta.name == name:
                return adapter
    return None


def _all_adapters() -> list[SourceAdapter]:
    """Return all adapters, custom overriding community by name."""
    seen: dict[str, SourceAdapter] = {}
    for directory in _source_dirs():
        for adapter in load_sources(directory):
            if adapter.meta.name not in seen:
                seen[adapter.meta.name] = adapter
    return list(seen.values())


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def update() -> None:
    """Pull latest community source adapters via git."""
    _BASE_DIR.mkdir(parents=True, exist_ok=True)

    if (_SOURCES_DIR / ".git").is_dir():
        typer.echo("Updating maestro-fetch-sources...")
        subprocess.run(
            ["git", "-C", str(_SOURCES_DIR), "pull", "--ff-only"],
            check=True,
        )
    else:
        typer.echo("Cloning maestro-fetch-sources...")
        subprocess.run(
            ["git", "clone", _SOURCES_REPO, str(_SOURCES_DIR)],
            check=True,
        )
    typer.echo(f"Sources directory: {_SOURCES_DIR}")


@app.command("list")
def list_sources(
    category: str = typer.Option(None, "--category", help="Filter by category"),
) -> None:
    """List available source adapters."""
    adapters = _all_adapters()
    if category:
        adapters = [a for a in adapters if a.meta.category == category]

    if not adapters:
        typer.echo("No source adapters found. Try 'mfetch source update' or reinstall.")
        raise typer.Exit(code=0)

    # Table header
    typer.echo(f"{'Name':<30} {'Category':<15} {'Description'}")
    typer.echo("-" * 75)
    for adapter in sorted(adapters, key=lambda a: a.meta.name):
        typer.echo(
            f"{adapter.meta.name:<30} "
            f"{adapter.meta.category:<15} "
            f"{adapter.meta.description}"
        )


@app.command()
def info(
    name: str = typer.Argument(..., help="Adapter name (e.g. worldbank/gdp)"),
) -> None:
    """Show details for a source adapter."""
    adapter = _find_adapter(name)
    if adapter is None:
        typer.echo(f"Adapter '{name}' not found.", err=True)
        raise typer.Exit(code=1)

    meta = adapter.meta
    typer.echo(f"Name:        {meta.name}")
    typer.echo(f"Description: {meta.description}")
    typer.echo(f"Category:    {meta.category}")
    typer.echo(f"Output:      {meta.output}")
    typer.echo(f"Requires:    {', '.join(meta.requires) or 'none'}")
    typer.echo(f"File:        {adapter.file_path}")

    if meta.args:
        typer.echo("\nArguments:")
        for arg_name, arg_spec in meta.args.items():
            req = "required" if arg_spec.get("required") else "optional"
            desc = arg_spec.get("description", "")
            default = arg_spec.get("default", "")
            example = arg_spec.get("example", "")
            line = f"  {arg_name} ({req}): {desc}"
            if default:
                line += f"  [default: {default}]"
            if example:
                line += f"  [example: {example}]"
            typer.echo(line)


@app.command()
def run(
    name: str = typer.Argument(..., help="Adapter name"),
    args: list[str] = typer.Argument(None, help="Adapter arguments"),
) -> None:
    """Execute a source adapter."""
    adapter = _find_adapter(name)
    if adapter is None:
        typer.echo(f"Adapter '{name}' not found.", err=True)
        raise typer.Exit(code=1)

    # Build kwargs from positional args matched to declared meta.args
    kwargs: dict[str, str] = {}
    arg_names = list(adapter.meta.args.keys())
    for i, val in enumerate(args or []):
        if i < len(arg_names):
            kwargs[arg_names[i]] = val
        else:
            typer.echo(f"Warning: extra argument ignored: {val}", err=True)

    # Fill defaults for missing optional args
    for arg_name, arg_spec in adapter.meta.args.items():
        if arg_name not in kwargs and "default" in arg_spec:
            kwargs[arg_name] = arg_spec["default"]

    ctx = SourceContext()
    result = asyncio.run(run_adapter(adapter, ctx, **kwargs))

    # Print result
    content = result.get("content", "")
    if content:
        typer.echo(content)
    else:
        import json

        typer.echo(json.dumps(result, indent=2, default=str))
