"""Configuration management — `mfetch config init|show`."""
from __future__ import annotations

import json

import typer

from maestro_fetch.core.config import CONFIG_PATH, load_config, write_default_config

app = typer.Typer(help="Configuration management.")


@app.command("init")
def init_config() -> None:
    """Generate default config file at ~/.maestro-fetch/config.toml."""
    if CONFIG_PATH.exists():
        overwrite = typer.confirm(f"{CONFIG_PATH} already exists. Overwrite?", default=False)
        if not overwrite:
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    dest = write_default_config()
    typer.echo(f"Config written to {dest}")


@app.command()
def show() -> None:
    """Show current configuration."""
    config = load_config()
    typer.echo(json.dumps(config, indent=2))
