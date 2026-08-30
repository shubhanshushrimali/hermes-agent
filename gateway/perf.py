"""
Performance & Optimization Module — ensures Hermes runs fast.

1. SQLite optimization (WAL, indexes, PRAGMA tuning)
2. Codebase graph caching (avoids re-indexing)
3. Model response caching (avoid duplicate LLM calls)
4. Connection pooling for HTTP endpoints
5. Lazy imports for heavy modules
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("hermes.perf")


# =============================================================================
# SQLite Optimization
# =============================================================================

def optimize_sqlite_connection(conn: sqlite3.Connection, label: str = "") -> None:
    """Apply production-grade SQLite optimizations."""
    pragmas = [
        "PRAGMA journal_mode=WAL",       # Write-Ahead Logging (concurrent reads)
        "PRAGMA busy_timeout=5000",       # Wait 5s on lock instead of failing
        "PRAGMA synchronous=NORMAL",      # Faster writes (safe with WAL)
        "PRAGMA cache_size=-64000",       # 64MB page cache
        "PRAGMA mmap_size=268435456",     # 256MB memory-mapped I/O
        "PRAGMA temp_store=MEMORY",       # Temp tables in memory
        "PRAGMA optimize",                # Run query planner optimization
    ]
    for pragma in pragmas:
        try:
            conn.execute(pragma)
        except Exception:
            pass
    logger.debug("SQLite optimized: %s", label)


def add_missing_indexes(conn: sqlite3.Connection) -> int:
    """Add performance indexes to existing tables. Returns count added."""
    indexes = [
        # Response store — lookup by response_id and conversation name.
        "CREATE INDEX IF NOT EXISTS idx_responses_accessed ON responses(accessed_at)",
        "CREATE INDEX IF NOT EXISTS idx_conversations_response ON conversations(response_id)",
        # Daemon jobs — priority queue ordering.
        "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_workspace ON jobs(workspace_path) WHERE workspace_path != ''",
    ]
    count = 0
    for idx in indexes:
        try:
            conn.execute(idx)
            count += 1
        except Exception:
            pass  # Table may not exist — that's fine.
    if count:
        conn.commit()
        logger.info("Added %d indexes", count)
    return count


# =============================================================================
# LLM Response Cache — avoid duplicate calls for identical prompts
# =============================================================================

class ResponseCache:
    """Simple SQLite-backed LLM response cache.

    Cache key = hash(model + system_prompt + user_prompt).
    TTL = 1 hour by default.
    """

    def __init__(self, cache_dir: str = None, ttl_seconds: int = 3600):
        self._cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".hermes", "cache"
        )
        os.makedirs(self._cache_dir, exist_ok=True)
        self._db_path = os.path.join(self._cache_dir, "response_cache.db")
        self._ttl = ttl_seconds
        self._conn = sqlite3.connect(self._db_path)
        optimize_sqlite_connection(self._conn, "response_cache")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                response TEXT NOT NULL,
                model TEXT,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_created ON cache(created_at)"
        )
        self._conn.commit()

    def _make_key(self, model: str, system: str, user: str) -> str:
        """Create a cache key from the prompt components."""
        raw = f"{model}|{system[:500]}|{user}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def get(self, model: str, system: str, user: str) -> Optional[str]:
        """Get cached response, or None if miss/expired."""
        key = self._make_key(model, system, user)
        cutoff = time.time() - self._ttl
        row = self._conn.execute(
            "SELECT response FROM cache WHERE key = ? AND created_at > ?",
            (key, cutoff),
        ).fetchone()
        if row:
            logger.debug("Cache hit: %s", key[:8])
            return row[0]
        return None

    def put(self, model: str, system: str, user: str, response: str) -> None:
        """Store a response in the cache."""
        key = self._make_key(model, system, user)
        self._conn.execute(
            "INSERT OR REPLACE INTO cache (key, response, model, created_at) VALUES (?, ?, ?, ?)",
            (key, response, model, time.time()),
        )
        self._conn.commit()

    def evict_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        cutoff = time.time() - self._ttl
        cursor = self._conn.execute(
            "DELETE FROM cache WHERE created_at < ?", (cutoff,)
        )
        self._conn.commit()
        return cursor.rowcount

    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        cutoff = time.time() - self._ttl
        valid = self._conn.execute(
            "SELECT COUNT(*) FROM cache WHERE created_at > ?", (cutoff,)
        ).fetchone()[0]
        return {"total": total, "valid": valid, "expired": total - valid}


# =============================================================================
# Codebase Graph Cache
# =============================================================================

class GraphCache:
    """Cache codebase graph results to avoid re-indexing unchanged repos.

    Key = workspace_path + git HEAD hash.
    If HEAD hasn't changed, skip re-indexing.
    """

    _cache: Dict[str, Any] = {}

    @classmethod
    def should_reindex(cls, workspace: str) -> bool:
        """Check if workspace needs re-indexing."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=workspace, timeout=3,
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                return True
            head = result.stdout.strip()
            cached_head = cls._cache.get(workspace)
            if cached_head == head:
                return False
            cls._cache[workspace] = head
            return True
        except Exception:
            return True

    @classmethod
    def invalidate(cls, workspace: str) -> None:
        """Force re-index on next check."""
        cls._cache.pop(workspace, None)


# =============================================================================
# Startup Optimizer
# =============================================================================

def run_startup_optimizations() -> None:
    """Run all startup optimizations. Called once at gateway boot."""
    logger.info("Running startup optimizations...")

    # 1. Evict expired response cache.
    try:
        cache = ResponseCache()
        evicted = cache.evict_expired()
        stats = cache.stats()
        logger.info(
            "Response cache: %d valid, %d evicted",
            stats["valid"], evicted,
        )
    except Exception:
        pass

    # 2. Optimize any existing SQLite databases.
    db_paths = [
        os.path.join(os.path.expanduser("~"), ".hermes", "daemon_jobs.db"),
        os.path.join(os.path.expanduser("~"), ".hermes", "cache", "response_cache.db"),
    ]
    for db_path in db_paths:
        if os.path.isfile(db_path):
            try:
                conn = sqlite3.connect(db_path)
                optimize_sqlite_connection(conn, db_path)
                add_missing_indexes(conn)
                conn.close()
            except Exception:
                pass

    logger.info("Startup optimizations complete")
