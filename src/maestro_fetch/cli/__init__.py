"""CLI entry point for maestro-fetch.

Registers all subcommand groups. The default command (no subcommand)
fetches a URL directly: ``mfetch <url>`` is equivalent to ``mfetch main <url>``.
"""
from __future__ import annotations

import sys

import typer

from maestro_fetch.cli.fetch import app as fetch_app
from maestro_fetch.cli.source import app as source_app
from maestro_fetch.cli.cache_cmd import app as cache_app
from maestro_fetch.cli.config_cmd import app as config_app
from maestro_fetch.cli.discover_cmd import app as discover_app
from maestro_fetch.cli.do_cmd import app as do_app
from maestro_fetch.cli.tab_cmd import app as tab_app

app = typer.Typer(
    name="maestro-fetch",
    help="Fetch everything, for agents. Universal data acquisition with smart routing.",
    add_completion=False,
    invoke_without_command=True,
)

# Register subcommands
app.add_typer(source_app, name="source", help="Manage source adapters.")
app.add_typer(cache_app, name="cache", help="Cache management.")
app.add_typer(config_app, name="config", help="Configuration management.")
app.add_typer(discover_app, name="discover", help="Discover site content via extension.")
app.add_typer(do_app, name="do", help="Natural language browser tasks.")
app.add_typer(tab_app, name="tab", help="Interact with existing Chrome tabs.")

# Register the default fetch command as "main" subcommand
app.registered_commands += fetch_app.registered_commands

# Known subcommand names
_SUBCOMMANDS = {"source", "cache", "config", "discover", "do", "tab", "main"}

# Site aliases discovered from source adapters (e.g. "twitter" → "source run twitter/...")
_SITE_NAMES: set[str] | None = None


def _discover_sites() -> set[str]:
    """Scan source adapters for site prefixes (twitter, xiaohongshu, weixin, ...)."""
    global _SITE_NAMES
    if _SITE_NAMES is not None:
        return _SITE_NAMES
    from maestro_fetch.cli.source import _all_adapters
    sites = set()
    for adapter in _all_adapters():
        name = adapter.meta.name
        if "/" in name:
            sites.add(name.split("/")[0])
    _SITE_NAMES = sites
    return sites


def run() -> None:
    """Entry point with site aliases: ``mfetch twitter reply`` → ``mfetch source run twitter/reply``."""
    args = sys.argv[1:]
    if args and args[0] not in _SUBCOMMANDS and not args[0].startswith("-"):
        # Check if first arg is a site name (twitter, xiaohongshu, etc.)
        sites = _discover_sites()
        if args[0] in sites and len(args) >= 2 and not args[1].startswith("-"):
            # mfetch twitter reply "text" "url" → mfetch source run twitter/reply "text" "url"
            site = args[0]
            command = args[1]
            rest = args[2:]
            sys.argv = [sys.argv[0], "source", "run", f"{site}/{command}"] + rest
        else:
            # Not a site — treat as URL
            sys.argv.insert(1, "main")
    app()
