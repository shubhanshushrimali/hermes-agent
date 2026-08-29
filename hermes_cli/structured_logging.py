"""Structured error logging — Hermes Agent Aizen Version.

Provides JSON-structured logging with:
- Correlation IDs (trace across request/response boundaries)
- Error classification (transient, user, system, fatal)
- Context fields (session_id, user_id, model, tool, etc.)
- Log rotation and file output
- Performance timing decorators

Usage:
    from hermes_cli.structured_logging import get_logger, LogContext

    log = get_logger("gateway.session")
    with LogContext(session_id="abc123", model="gpt-4"):
        log.info("Session started", tokens=1000)
        log.error("API call failed", error_class="transient", retry_in=5)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import threading
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional


# ---------------------------------------------------------------------------
# Thread-local context storage
# ---------------------------------------------------------------------------

_context = threading.local()


def _get_context() -> Dict[str, Any]:
    """Get the current thread-local logging context."""
    if not hasattr(_context, "fields"):
        _context.fields = {}
    return _context.fields


@contextmanager
def LogContext(**fields):
    """Context manager that adds fields to all log messages within the block.

    Usage:
        with LogContext(session_id="abc", model="gpt-4"):
            log.info("Processing")  # → includes session_id, model
    """
    ctx = _get_context()
    old_values = {}
    for k, v in fields.items():
        old_values[k] = ctx.get(k)
        ctx[k] = v
    try:
        yield
    finally:
        for k, old_v in old_values.items():
            if old_v is None:
                ctx.pop(k, None)
            else:
                ctx[k] = old_v


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

class ErrorClass:
    """Classifiers for error severity and type."""
    TRANSIENT = "transient"     # Retryable (network timeout, rate limit)
    USER = "user"               # User input error (bad config, invalid PIN)
    SYSTEM = "system"           # Internal error (bug, assertion failure)
    FATAL = "fatal"             # Unrecoverable (corrupt DB, missing binary)
    EXTERNAL = "external"       # Third-party service failure


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class StructuredFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Add thread-local context
        ctx = _get_context()
        if ctx:
            entry["ctx"] = dict(ctx)

        # Add correlation ID if present
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            entry["correlation_id"] = correlation_id

        # Add extra fields passed to the log call
        extra_fields = getattr(record, "_extra_fields", {})
        if extra_fields:
            entry.update(extra_fields)

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add source location for errors
        if record.levelno >= logging.WARNING:
            entry["source"] = f"{record.pathname}:{record.lineno}"

        return json.dumps(entry, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Structured logger wrapper
# ---------------------------------------------------------------------------

class StructuredLogger:
    """Wraps a stdlib logger to accept keyword arguments as structured fields."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _log(self, level: int, msg: str, **fields) -> None:
        if not self._logger.isEnabledFor(level):
            return
        record = self._logger.makeRecord(
            self._logger.name, level, "(structured)", 0, msg, (), None
        )
        record._extra_fields = fields  # type: ignore[attr-defined]
        self._logger.handle(record)

    def debug(self, msg: str, **fields) -> None:
        self._log(logging.DEBUG, msg, **fields)

    def info(self, msg: str, **fields) -> None:
        self._log(logging.INFO, msg, **fields)

    def warning(self, msg: str, **fields) -> None:
        self._log(logging.WARNING, msg, **fields)

    def error(self, msg: str, **fields) -> None:
        self._log(logging.ERROR, msg, **fields)

    def critical(self, msg: str, **fields) -> None:
        self._log(logging.CRITICAL, msg, **fields)

    def exception(self, msg: str, **fields) -> None:
        fields["exc_info"] = True
        self._log(logging.ERROR, msg, **fields)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

_configured = False


def configure_logging(
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console: bool = True,
    json_file: bool = True,
) -> None:
    """Configure structured logging for the application.

    Call once at startup. Subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(level)

    formatter = StructuredFormatter()

    # Console handler (human-readable for dev, JSON for production)
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        if os.environ.get("HERMES_LOG_JSON"):
            console_handler.setFormatter(formatter)
        else:
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s")
            )
        root.addHandler(console_handler)

    # JSON file handler
    if json_file and log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_path = log_dir / "hermes.log.jsonl"
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger by name."""
    return StructuredLogger(logging.getLogger(name))


# ---------------------------------------------------------------------------
# Performance timing decorator
# ---------------------------------------------------------------------------

def timed(name: Optional[str] = None):
    """Decorator that logs execution time of a function."""
    def decorator(fn: Callable) -> Callable:
        label = name or f"{fn.__module__}.{fn.__qualname__}"
        log = get_logger(label)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                elapsed = time.perf_counter() - start
                log.debug("completed", duration_ms=round(elapsed * 1000, 2))
                return result
            except Exception:
                elapsed = time.perf_counter() - start
                log.error("failed", duration_ms=round(elapsed * 1000, 2))
                raise
        return wrapper
    return decorator


def new_correlation_id() -> str:
    """Generate a new correlation ID for tracing."""
    return uuid.uuid4().hex[:12]
