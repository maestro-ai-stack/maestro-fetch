"""Tests for CacheManager (core/cache.py).

Covers: init, put/get, expiration, clear, list, content-addressing.
All tests use tmp_path for filesystem isolation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from maestro_fetch.core.cache import CacheManager


@pytest.fixture()
def cache_env(tmp_path: Path) -> tuple[CacheManager, Path]:
    """Return a CacheManager pointed at tmp_path and a scratch dir for files."""
    db_path = tmp_path / "cache.db"
    cache_dir = tmp_path / "cache"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    mgr = CacheManager(db_path=db_path, cache_dir=cache_dir)
    return mgr, scratch


def _write_file(directory: Path, name: str, content: bytes) -> Path:
    p = directory / name
    p.write_bytes(content)
    return p


# -- schema ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_creates_tables(cache_env: tuple[CacheManager, Path]) -> None:
    """init() should create the SQLite DB with the cache table and indices."""
    mgr, _ = cache_env
    await mgr.init()
    try:
        assert mgr.db_path.exists()
        # Query sqlite_master for expected objects
        assert mgr._db is not None
        cursor = await mgr._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cache'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "cache"

        # Check indices
        cursor = await mgr._db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_cache_%'"
        )
        indices = {r[0] for r in await cursor.fetchall()}
        assert "idx_cache_hash" in indices
        assert "idx_cache_fetched" in indices
    finally:
        await mgr.close()


# -- put and get -----------------------------------------------------------


@pytest.mark.asyncio
async def test_put_and_get(cache_env: tuple[CacheManager, Path]) -> None:
    """put() stores an entry; get() retrieves it by URL."""
    mgr, scratch = cache_env
    await mgr.init()
    try:
        raw = _write_file(scratch, "data.csv", b"a,b\n1,2\n")
        entry = await mgr.put(
            url="https://example.com/data.csv",
            raw_path=raw,
            source_type="doc",
            mime_type="text/csv",
        )
        assert entry.url == "https://example.com/data.csv"
        assert entry.source_type == "doc"
        assert entry.hash  # non-empty sha256

        got = await mgr.get("https://example.com/data.csv")
        assert got is not None
        assert got.hash == entry.hash
        assert got.mime_type == "text/csv"
    finally:
        await mgr.close()


# -- expiration ------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_expired(cache_env: tuple[CacheManager, Path]) -> None:
    """get() returns None for entries whose TTL has elapsed."""
    mgr, scratch = cache_env
    await mgr.init()
    try:
        raw = _write_file(scratch, "old.txt", b"stale")
        # Store with TTL=1 second
        await mgr.put(
            url="https://example.com/old.txt",
            raw_path=raw,
            source_type="web",
            ttl=1,
        )
        # Manually backdate fetched_at so the entry is expired
        assert mgr._db is not None
        past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        await mgr._db.execute(
            "UPDATE cache SET fetched_at = ? WHERE url = ?",
            (past, "https://example.com/old.txt"),
        )
        await mgr._db.commit()

        result = await mgr.get("https://example.com/old.txt")
        assert result is None
    finally:
        await mgr.close()


# -- clear -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_all(cache_env: tuple[CacheManager, Path]) -> None:
    """clear() with no arguments removes all entries."""
    mgr, scratch = cache_env
    await mgr.init()
    try:
        for i in range(3):
            raw = _write_file(scratch, f"f{i}.txt", f"data{i}".encode())
            await mgr.put(url=f"https://example.com/f{i}", raw_path=raw, source_type="web")
        count = await mgr.clear()
        assert count == 3
        entries = await mgr.list_entries()
        assert len(entries) == 0
    finally:
        await mgr.close()


@pytest.mark.asyncio
async def test_clear_older_than(cache_env: tuple[CacheManager, Path]) -> None:
    """clear(older_than='1s') removes only old entries."""
    mgr, scratch = cache_env
    await mgr.init()
    try:
        # Insert an old entry
        raw_old = _write_file(scratch, "old.txt", b"old")
        await mgr.put(url="https://example.com/old", raw_path=raw_old, source_type="web")
        assert mgr._db is not None
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await mgr._db.execute(
            "UPDATE cache SET fetched_at = ? WHERE url = ?",
            (past, "https://example.com/old"),
        )
        await mgr._db.commit()

        # Insert a fresh entry
        raw_new = _write_file(scratch, "new.txt", b"new")
        await mgr.put(url="https://example.com/new", raw_path=raw_new, source_type="web")

        removed = await mgr.clear(older_than="1d")
        assert removed == 1

        entries = await mgr.list_entries()
        assert len(entries) == 1
        assert entries[0].url == "https://example.com/new"
    finally:
        await mgr.close()


# -- list ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_entries(cache_env: tuple[CacheManager, Path]) -> None:
    """list_entries() returns all entries including expired."""
    mgr, scratch = cache_env
    await mgr.init()
    try:
        for i in range(2):
            raw = _write_file(scratch, f"item{i}.txt", f"content{i}".encode())
            await mgr.put(url=f"https://example.com/item{i}", raw_path=raw, source_type="web")
        entries = await mgr.list_entries()
        assert len(entries) == 2
    finally:
        await mgr.close()


# -- content addressing ----------------------------------------------------


@pytest.mark.asyncio
async def test_content_addressed(cache_env: tuple[CacheManager, Path]) -> None:
    """Two files with identical content produce the same hash."""
    mgr, scratch = cache_env
    await mgr.init()
    try:
        data = b"identical content bytes"
        raw1 = _write_file(scratch, "file_a.txt", data)
        raw2 = _write_file(scratch, "file_b.txt", data)
        e1 = await mgr.put(url="https://example.com/a", raw_path=raw1, source_type="web")
        e2 = await mgr.put(url="https://example.com/b", raw_path=raw2, source_type="web")
        assert e1.hash == e2.hash
    finally:
        await mgr.close()
