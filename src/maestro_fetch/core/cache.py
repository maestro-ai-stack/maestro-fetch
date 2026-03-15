"""SQLite cache index for maestro-fetch.

Tracks URL -> file mappings with TTL-based expiration.
Storage: ~/.maestro-fetch/cache.db
Files: ~/.maestro-fetch/cache/{sha256_hash}.{ext}
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS cache (
    url         TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    raw_path    TEXT NOT NULL,
    source_type TEXT NOT NULL,
    size_bytes  INTEGER,
    mime_type   TEXT,
    fetched_at  TEXT NOT NULL,
    ttl_seconds INTEGER DEFAULT 86400,
    etag        TEXT,
    metadata    TEXT
);
CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(hash);
CREATE INDEX IF NOT EXISTS idx_cache_fetched ON cache(fetched_at);
"""


@dataclass
class CacheEntry:
    """A single cached resource."""

    url: str
    hash: str
    raw_path: str
    source_type: str
    size_bytes: int | None = None
    mime_type: str | None = None
    fetched_at: str = ""
    ttl_seconds: int = 86400
    etag: str | None = None
    metadata: dict | None = field(default=None)

    @property
    def is_expired(self) -> bool:
        """Return True when the entry has outlived its TTL."""
        fetched = datetime.fromisoformat(self.fetched_at).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - fetched > timedelta(seconds=self.ttl_seconds)


def _parse_duration(value: str) -> timedelta:
    """Parse human duration strings such as '7d', '1h', '30m', '2d12h'.

    Supported units: d (days), h (hours), m (minutes), s (seconds).
    """
    pattern = re.compile(r"(\d+)\s*([dhms])", re.IGNORECASE)
    matches = pattern.findall(value)
    if not matches:
        msg = f"Cannot parse duration: {value!r}"
        raise ValueError(msg)
    total = timedelta()
    unit_map = {"d": "days", "h": "hours", "m": "minutes", "s": "seconds"}
    for amount, unit in matches:
        total += timedelta(**{unit_map[unit.lower()]: int(amount)})
    return total


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_to_entry(row: aiosqlite.Row) -> CacheEntry:
    """Convert a database row to a CacheEntry."""
    meta_raw = row[9]  # metadata column
    meta = json.loads(meta_raw) if meta_raw else None
    return CacheEntry(
        url=row[0],
        hash=row[1],
        raw_path=row[2],
        source_type=row[3],
        size_bytes=row[4],
        mime_type=row[5],
        fetched_at=row[6],
        ttl_seconds=row[7] if row[7] is not None else 86400,
        etag=row[8],
        metadata=meta,
    )


class CacheManager:
    """Content-addressed file cache backed by SQLite."""

    def __init__(self, db_path: Path, cache_dir: Path) -> None:
        self.db_path = db_path
        self.cache_dir = cache_dir
        self._db: aiosqlite.Connection | None = None

    # -- lifecycle -----------------------------------------------------------

    async def init(self) -> None:
        """Open the database and create tables if they do not exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    # -- queries -------------------------------------------------------------

    async def get(self, url: str) -> CacheEntry | None:
        """Return a cached entry if it exists and has not expired."""
        assert self._db is not None, "Call init() first"
        cursor = await self._db.execute("SELECT * FROM cache WHERE url = ?", (url,))
        row = await cursor.fetchone()
        if row is None:
            return None
        entry = _row_to_entry(row)
        if entry.is_expired:
            return None
        return entry

    async def put(
        self,
        url: str,
        raw_path: Path,
        source_type: str,
        ttl: int = 86400,
        etag: str | None = None,
        mime_type: str | None = None,
        metadata: dict | None = None,
    ) -> CacheEntry:
        """Store a file in the content-addressed cache and record it in the index."""
        assert self._db is not None, "Call init() first"

        file_hash = _sha256_file(raw_path)
        ext = raw_path.suffix or ""
        dest = self.cache_dir / f"{file_hash}{ext}"

        # Copy (not move) the raw file into cache storage
        if not dest.exists():
            shutil.copy2(raw_path, dest)

        size_bytes = dest.stat().st_size
        fetched_at = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata) if metadata else None

        await self._db.execute(
            """
            INSERT OR REPLACE INTO cache
                (url, hash, raw_path, source_type, size_bytes, mime_type,
                 fetched_at, ttl_seconds, etag, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (url, file_hash, str(dest), source_type, size_bytes, mime_type, fetched_at, ttl, etag, meta_json),
        )
        await self._db.commit()

        return CacheEntry(
            url=url,
            hash=file_hash,
            raw_path=str(dest),
            source_type=source_type,
            size_bytes=size_bytes,
            mime_type=mime_type,
            fetched_at=fetched_at,
            ttl_seconds=ttl,
            etag=etag,
            metadata=metadata,
        )

    async def list_entries(self) -> list[CacheEntry]:
        """Return all cache entries (including expired)."""
        assert self._db is not None, "Call init() first"
        cursor = await self._db.execute("SELECT * FROM cache ORDER BY fetched_at DESC")
        rows = await cursor.fetchall()
        return [_row_to_entry(r) for r in rows]

    async def clear(self, older_than: str | None = None) -> int:
        """Delete cache entries (and their files).

        Args:
            older_than: Human duration string like '7d' or '1h'.
                        If None, removes *all* entries.

        Returns:
            Number of entries removed.
        """
        assert self._db is not None, "Call init() first"

        if older_than is not None:
            delta = _parse_duration(older_than)
            cutoff = (datetime.now(timezone.utc) - delta).isoformat()
            cursor = await self._db.execute("SELECT raw_path FROM cache WHERE fetched_at < ?", (cutoff,))
            rows = await cursor.fetchall()
            for (raw_path,) in rows:
                p = Path(raw_path)
                if p.exists():
                    p.unlink()
            await self._db.execute("DELETE FROM cache WHERE fetched_at < ?", (cutoff,))
        else:
            cursor = await self._db.execute("SELECT raw_path FROM cache")
            rows = await cursor.fetchall()
            for (raw_path,) in rows:
                p = Path(raw_path)
                if p.exists():
                    p.unlink()
            await self._db.execute("DELETE FROM cache")

        await self._db.commit()
        return len(rows)
