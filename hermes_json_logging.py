"""Structured JSON logging formatter for Hermes Agent.

Outputs one JSON object per line for machine-parseable error analysis,
alerting, and log aggregation. Works alongside the existing text-based
``hermes_logging.py`` formatters — both can run simultaneously.

Each JSON line contains:
    ts         — ISO 8601 timestamp with timezone
    level      — log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    logger     — logger name (e.g. ``gateway.session``)
    session    — session ID from thread-local context (null if unset)
    msg        — formatted log message
    exc_type   — exception class name (only on errors)
    exc_msg    — exception message (only on errors)
    stack      — full traceback string (only on errors)
    pid        — process ID
    thread     — thread name

Usage:
    from hermes_json_logging import StructuredJsonFormatter

    handler = RotatingFileHandler("structured.log")
    handler.setFormatter(StructuredJsonFormatter())
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Import the session context from hermes_logging (thread-local session_id).
# Lazy import to avoid circular dependency at module load time.
_session_context = None


def _get_session_id() -> Optional[str]:
    """Retrieve the current thread's session ID, if set."""
    global _session_context
    if _session_context is None:
        try:
            from hermes_logging import _session_context as ctx
            _session_context = ctx
        except ImportError:
            return None
    return getattr(_session_context, "session_id", None)


# ---------------------------------------------------------------------------
# Secret redaction (reuses the agent's existing redaction patterns)
# ---------------------------------------------------------------------------

# Lazy-loaded redaction function.
_redact_fn = None


def _redact(text: str) -> str:
    """Redact secrets from text using the agent's existing redaction logic."""
    global _redact_fn
    if _redact_fn is None:
        try:
            from agent.redact import RedactingFormatter
            # Create a dummy formatter to access its redact method.
            _fmt = RedactingFormatter("%(message)s")
            _redact_fn = _fmt._redact  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            # Redaction not available — pass through unchanged.
            _redact_fn = lambda x: x  # noqa: E731
    return _redact_fn(text)


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------


class StructuredJsonFormatter(logging.Formatter):
    """Logging formatter that outputs one JSON object per line.

    Designed for the ``structured.log`` file handler. All string values
    are passed through the agent's secret redaction pipeline.

    The output is newline-delimited JSON (NDJSON/JSON Lines), compatible
    with ``jq``, Loki, Datadog, and other log aggregation tools.
    """

    def __init__(
        self,
        *,
        include_stack: bool = True,
        include_thread: bool = True,
        include_process: bool = True,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self._include_stack = include_stack
        self._include_thread = include_thread
        self._include_process = include_process
        self._extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        """Format a LogRecord as a single-line JSON string."""
        # Build the base record.
        entry: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "session": _get_session_id(),
            "msg": _redact(record.getMessage()),
        }

        # Exception info.
        if record.exc_info and record.exc_info[1] is not None:
            exc_type, exc_value, exc_tb = record.exc_info
            entry["exc_type"] = (
                exc_type.__name__ if exc_type else None
            )
            entry["exc_msg"] = _redact(str(exc_value)) if exc_value else None
            if self._include_stack and exc_tb is not None:
                entry["stack"] = _redact(
                    "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
                )

        # Process / thread context.
        if self._include_process:
            entry["pid"] = record.process
        if self._include_thread:
            entry["thread"] = record.threadName

        # Extra fields (e.g. hostname, service name).
        if self._extra_fields:
            entry.update(self._extra_fields)

        # Any extra attributes attached to the record.
        # Common pattern: logger.warning("msg", extra={"request_id": "abc"})
        for key in ("request_id", "platform", "chat_id", "user_id", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # Serialize — ensure_ascii=False to preserve Unicode,
        # default=str to handle non-serializable extras.
        try:
            return json.dumps(entry, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            # Absolute last resort — if JSON serialization itself fails.
            return json.dumps(
                {
                    "ts": entry.get("ts", ""),
                    "level": "ERROR",
                    "logger": "hermes_json_logging",
                    "msg": f"Failed to serialize log record: {record.getMessage()!r}",
                },
                ensure_ascii=False,
            )


# ---------------------------------------------------------------------------
# Convenience: attach structured logging to the root logger
# ---------------------------------------------------------------------------


def add_structured_handler(
    log_dir: str,
    *,
    level: int = logging.WARNING,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> logging.Handler:
    """Add a structured JSON log handler to the root logger.

    Creates ``structured.log`` in the given directory with rotation.

    Returns the handler so callers can remove it if needed.
    """
    from pathlib import Path

    log_path = Path(log_dir) / "structured.log"

    # Use the same rotating handler class as hermes_logging.py
    # (ConcurrentRotatingFileHandler on Windows, stdlib on POSIX).
    if sys.platform == "win32":
        try:
            from concurrent_log_handler import (
                ConcurrentRotatingFileHandler as RotHandler,
            )
        except ImportError:
            from logging.handlers import RotatingFileHandler as RotHandler
    else:
        from logging.handlers import RotatingFileHandler as RotHandler

    handler = RotHandler(
        str(log_path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(
        StructuredJsonFormatter(extra_fields=extra_fields)
    )

    logging.getLogger().addHandler(handler)
    return handler
