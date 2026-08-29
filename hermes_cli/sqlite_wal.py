"""SQLite WAL mode and connection hardening — Hermes Agent Aizen Version.

Provides a ``connect_wal()`` wrapper around ``sqlite3.connect`` that:

1. **Enables WAL mode** — Write-Ahead Logging allows concurrent reads
   during writes, eliminating "database is locked" errors
2. **Sets busy timeout** — Waits up to 10s for locks instead of
   immediately failing
3. **Enables foreign keys** — Enforces referential integrity
4. **Sets synchronous=NORMAL** — Good balance of safety vs speed in WAL
5. **Configures mmap_size** — Memory-maps the database for faster reads
6. **Adds integrity check** — Optional PRAGMA integrity_check on open

This module should be imported wherever sqlite3.connect is used.

Usage:
    from hermes_cli.sqlite_wal import connect_wal

    conn = connect_wal("~/.hermes/kanban.db")
    # WAL mode, busy_timeout, foreign_keys all configured
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Sensible defaults
DEFAULT_BUSY_TIMEOUT_MS = 10_000  # 10 seconds
DEFAULT_MMAP_SIZE = 64 * 1024 * 1024  # 64 MB
DEFAULT_CACHE_SIZE = -8000  # ~8MB (negative = KB)


def connect_wal(
    path: Union[str, Path],
    *,
    busy_timeout: int = DEFAULT_BUSY_TIMEOUT_MS,
    mmap_size: int = DEFAULT_MMAP_SIZE,
    foreign_keys: bool = True,
    read_only: bool = False,
    timeout: float = 10.0,
    check_integrity: bool = False,
) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and hardened settings.

    Args:
        path: Path to the database file (or ":memory:")
        busy_timeout: Milliseconds to wait for locks
        mmap_size: Bytes to memory-map (0 to disable)
        foreign_keys: Enable PRAGMA foreign_keys
        read_only: Open in read-only mode (URI mode)
        timeout: Connection timeout in seconds
        check_integrity: Run PRAGMA integrity_check on open
    """
    str_path = str(path)

    if read_only and str_path != ":memory:":
        # Use URI mode for read-only access
        resolved = Path(str_path).resolve()
        uri = f"file:{resolved.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    else:
        conn = sqlite3.connect(str_path, timeout=timeout)

    try:
        # WAL mode — most important setting
        # Returns the journal mode that was actually set
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if result and result[0].upper() != "WAL":
            logger.warning(
                "Could not enable WAL mode for %s (got %s)",
                path, result[0],
            )

        # Busy timeout — prevents immediate "database is locked" errors
        conn.execute(f"PRAGMA busy_timeout={busy_timeout}")

        # Synchronous NORMAL — safe with WAL, much faster than FULL
        conn.execute("PRAGMA synchronous=NORMAL")

        # Foreign keys — enforce referential integrity
        if foreign_keys:
            conn.execute("PRAGMA foreign_keys=ON")

        # Cache size — larger cache reduces disk reads
        conn.execute(f"PRAGMA cache_size={DEFAULT_CACHE_SIZE}")

        # Memory-map — faster reads for large databases
        if mmap_size > 0:
            conn.execute(f"PRAGMA mmap_size={mmap_size}")

        # Temp store in memory — faster temp tables
        conn.execute("PRAGMA temp_store=MEMORY")

        # Optional integrity check
        if check_integrity:
            integrity = conn.execute("PRAGMA integrity_check(1)").fetchone()
            if integrity and integrity[0] != "ok":
                logger.error(
                    "SQLite integrity check failed for %s: %s",
                    path, integrity[0],
                )

    except sqlite3.Error as e:
        logger.error("Failed to configure SQLite for %s: %s", path, e)
        # Don't close — caller may still want a partially-configured connection

    return conn


def enable_wal_existing(path: Union[str, Path]) -> bool:
    """Enable WAL mode on an existing database file.

    Returns True if WAL was enabled, False on failure.
    Useful for one-time migration of existing databases.
    """
    try:
        conn = sqlite3.connect(str(path))
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        conn.close()
        return result is not None and result[0].upper() == "WAL"
    except Exception as e:
        logger.error("Failed to enable WAL on %s: %s", path, e)
        return False


def migrate_all_databases(hermes_home: Union[str, Path]) -> int:
    """Enable WAL mode on all .db files in the Hermes home directory.

    Returns the count of databases migrated.
    """
    home = Path(hermes_home)
    migrated = 0
    for db_path in home.rglob("*.db"):
        if db_path.stat().st_size == 0:
            continue
        if enable_wal_existing(db_path):
            logger.info("Enabled WAL mode: %s", db_path)
            migrated += 1
    return migrated


def get_db_stats(path: Union[str, Path]) -> dict:
    """Get diagnostic stats for a SQLite database."""
    try:
        conn = sqlite3.connect(str(path), timeout=5)
        stats = {}
        for pragma in ("journal_mode", "wal_checkpoint", "page_count", "page_size", "freelist_count"):
            try:
                result = conn.execute(f"PRAGMA {pragma}").fetchone()
                stats[pragma] = result[0] if result else None
            except Exception:
                stats[pragma] = None
        conn.close()

        # Calculate size info
        if stats.get("page_count") and stats.get("page_size"):
            stats["size_mb"] = round(
                stats["page_count"] * stats["page_size"] / (1024 * 1024), 2
            )
        stats["file_size_mb"] = round(
            Path(path).stat().st_size / (1024 * 1024), 2
        )
        return stats
    except Exception as e:
        return {"error": str(e)}
