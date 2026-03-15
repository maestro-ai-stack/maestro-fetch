"""Cache management — `mfetch cache list|clear`."""
from __future__ import annotations

import asyncio

import typer

from maestro_fetch.core.cache import CacheManager
from maestro_fetch.core.config import CACHE_DB_PATH, CACHE_DIR

app = typer.Typer(help="Cache management.")


def _manager() -> CacheManager:
    return CacheManager(db_path=CACHE_DB_PATH, cache_dir=CACHE_DIR)


@app.command("list")
def list_cache() -> None:
    """List cached entries."""

    async def _run() -> None:
        mgr = _manager()
        await mgr.init()
        try:
            entries = await mgr.list_entries()
            if not entries:
                typer.echo("Cache is empty.")
                return

            # Header
            typer.echo(f"{'URL':<60} {'TYPE':<10} {'SIZE':>10} {'FETCHED AT':<26} {'EXPIRED'}")
            typer.echo("-" * 120)

            for e in entries:
                size = f"{e.size_bytes:,}" if e.size_bytes is not None else "—"
                expired = "yes" if e.is_expired else "no"
                url_display = e.url[:57] + "..." if len(e.url) > 60 else e.url
                typer.echo(f"{url_display:<60} {e.source_type:<10} {size:>10} {e.fetched_at[:25]:<26} {expired}")

            typer.echo(f"\nTotal: {len(entries)} entries")
        finally:
            await mgr.close()

    asyncio.run(_run())


@app.command()
def clear(
    older_than: str = typer.Option(None, "--older-than", help="Remove entries older than (e.g. 7d, 1h)"),
) -> None:
    """Clear cached entries."""

    async def _run() -> None:
        mgr = _manager()
        await mgr.init()
        try:
            count = await mgr.clear(older_than=older_than)
            if older_than:
                typer.echo(f"Removed {count} entries older than {older_than}.")
            else:
                typer.echo(f"Removed {count} entries (cache cleared).")
        finally:
            await mgr.close()

    asyncio.run(_run())
