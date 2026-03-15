"""Default fetch command — `mfetch <url>`.

Moved from interfaces/cli.py. Delegates to the SDK async API.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Optional

import typer

from maestro_fetch.core.result import FetchResult
from maestro_fetch.interfaces.sdk import fetch, batch_fetch
from maestro_fetch.core.errors import FetchError

app = typer.Typer()


@app.command()
def main(
    url: str = typer.Argument(..., help="URL to fetch"),
    output: str = typer.Option(
        "markdown", "--output", "-o",
        help="Output format: markdown|csv|json|parquet",
    ),
    schema: Optional[Path] = typer.Option(
        None, "--schema", help="JSON schema file for LLM extraction",
    ),
    provider: str = typer.Option(
        "anthropic", "--provider",
        help="LLM provider: anthropic|openai|gemini|ollama",
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Model name override",
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Directory to save output files",
    ),
    batch: Optional[Path] = typer.Option(
        None, "--batch", help="File containing one URL per line",
    ),
    cache_dir: str = typer.Option(
        str(Path.home() / ".maestro" / "cache"), "--cache-dir", help="Cache directory",
    ),
    timeout: int = typer.Option(
        60, "--timeout", help="Request timeout in seconds",
    ),
) -> None:
    """Fetch data from any URL. Auto-detects source type."""
    schema_dict = None
    if schema:
        schema_dict = json.loads(schema.read_text())

    urls = [url]
    if batch:
        urls = [
            line.strip()
            for line in batch.read_text().splitlines()
            if line.strip()
        ]

    try:
        if len(urls) == 1:
            result = asyncio.run(fetch(
                urls[0],
                provider=provider,
                model=model,
                schema=schema_dict,
                output_format=output,
                cache_dir=cache_dir,
                timeout=timeout,
            ))
            _print_result(result, output, output_dir)
        else:
            results = asyncio.run(batch_fetch(
                urls, provider=provider, output_format=output,
            ))
            for r in results:
                _print_result(r, output, output_dir)
    except FetchError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


def _print_result(
    result: FetchResult,
    output_format: str,
    output_dir: Optional[Path],
) -> None:
    """Format and print a FetchResult to stdout (or save to file)."""
    # Binary results (images, archives, data files): copy raw file to output_dir
    if result.source_type == "binary" and output_dir and result.raw_path:
        raw_path = result.raw_path
        if raw_path.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            dest = output_dir / raw_path.name
            if dest.resolve() != raw_path.resolve():
                shutil.copy2(raw_path, dest)
            typer.echo(f"Saved to {dest}")
            return
    if output_format == "markdown":
        typer.echo(result.content)
    elif output_format == "json":
        if result.tables:
            typer.echo(result.tables[0].to_json(orient="records", indent=2))
        else:
            typer.echo(json.dumps({
                "content": result.content,
                "metadata": result.metadata,
            }))
    elif output_format in ("csv", "parquet"):
        if not result.tables:
            typer.echo("No tables found in result.", err=True)
            return
        df = result.tables[0]
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            name = result.url.split("/")[-1].split("?")[0] or "output"
            path = output_dir / f"{name}.{output_format}"
            if output_format == "csv":
                df.to_csv(path, index=False)
            else:
                df.to_parquet(path, index=False)
            typer.echo(f"Saved to {path}")
        else:
            typer.echo(df.to_csv(index=False))
    else:
        typer.echo(result.content)
