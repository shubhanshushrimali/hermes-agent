"""
Hermes Structured Logging — structlog-based JSON logging.

Replaces ad-hoc logging.getLogger() with structured, queryable JSON logs.
Integrates with Langfuse for trace correlation.

Usage:
    from gateway.hermes_slog import get_logger

    log = get_logger("gateway.run")
    log.info("turn_started", session="abc", model="claude-sonnet")
    log.error("tool_failed", tool="web_search", error="timeout")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

# Try structlog first, fall back to stdlib logging.
try:
    import structlog

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


def configure_structlog(
    json_output: bool = False,
    log_level: str = "INFO",
) -> None:
    """Configure structlog for the entire Hermes process.

    Call once at startup (e.g., in gateway/run.py or hermes_cli/main.py).

    Args:
        json_output: True for JSON (production/daemon), False for colored console.
        log_level: Standard log level string.
    """
    if not STRUCTLOG_AVAILABLE:
        # Fall back to stdlib basic config.
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            stream=sys.stderr,
        )
        return

    # Shared processors for all output formats.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        # Production: JSON lines to stderr.
        renderer = structlog.processors.JSONRenderer()
    else:
        # Development: colored console output.
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib root logger to use structlog formatter.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))


def get_logger(name: str, **initial_context: Any):
    """Get a structured logger instance.

    Works whether structlog is installed or not.

    Args:
        name: Logger name (e.g., "gateway.graph_engine").
        **initial_context: Key-value pairs bound to every log from this logger.

    Returns:
        A structlog BoundLogger or stdlib Logger.
    """
    if STRUCTLOG_AVAILABLE:
        log = structlog.get_logger(name)
        if initial_context:
            log = log.bind(**initial_context)
        return log
    else:
        return logging.getLogger(name)


def bind_trace_context(trace_id: str = "", session_key: str = "") -> None:
    """Bind trace context to all subsequent log entries in this async context.

    Call at the start of a turn to correlate logs with Langfuse traces.
    """
    if STRUCTLOG_AVAILABLE:
        ctx = {}
        if trace_id:
            ctx["trace_id"] = trace_id
        if session_key:
            ctx["session"] = session_key
        if ctx:
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(**ctx)
