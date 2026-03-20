"""CLI entry point for maestro-fetch.

Registers all subcommand groups and the default fetch command.
"""
from __future__ import annotations

import typer

from maestro_fetch.cli.fetch import app as fetch_app
from maestro_fetch.cli.source import app as source_app
from maestro_fetch.cli.session import app as session_app
from maestro_fetch.cli.cache_cmd import app as cache_app
from maestro_fetch.cli.config_cmd import app as config_app
from maestro_fetch.cli.discover_cmd import app as discover_app
from maestro_fetch.cli.do_cmd import app as do_app

app = typer.Typer(
    name="maestro-fetch",
    help="Fetch everything, for agents. Universal data acquisition with smart routing.",
    add_completion=False,
    invoke_without_command=True,
)

# Register subcommands
app.add_typer(source_app, name="source", help="Manage source adapters.")
app.add_typer(session_app, name="session", help="Interactive browser sessions.")
app.add_typer(cache_app, name="cache", help="Cache management.")
app.add_typer(config_app, name="config", help="Configuration management.")
app.add_typer(discover_app, name="discover", help="Discover site APIs via opencli.")
app.add_typer(do_app, name="do", help="Natural language browser tasks.")

# Register the default fetch command directly on the main app
app.registered_commands += fetch_app.registered_commands
