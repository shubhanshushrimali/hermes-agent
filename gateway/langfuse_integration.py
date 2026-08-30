"""
Langfuse Integration for Hermes Agent — Observability & Tracing.

Self-hosted Langfuse runs on the user's laptop via Docker Compose.
All LLM calls, tool uses, graph node transitions, and crew handoffs
are traced automatically.

Setup:
    1. docker compose -f docker/langfuse.yml up -d
    2. Visit http://localhost:3000 to create project + API keys
    3. Set env vars: LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY
    4. Set LANGFUSE_HOST=http://localhost:3000

Usage:
    from gateway.langfuse_integration import init_langfuse, trace_turn

    init_langfuse()  # Call once at startup

    # Auto-traces any function:
    @observe(name="my_function")
    def my_function():
        ...

    # Manual span for gateway turns:
    with trace_turn(session_key, user_prompt) as span:
        result = run_agent(...)
        span.end(output=result)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger("hermes.langfuse")

# Try importing Langfuse.
try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

    # No-op fallback.
    def observe(*args, **kwargs):
        def wrapper(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return wrapper


# Singleton client.
_client: Optional[Any] = None


def init_langfuse(
    host: str = None,
    public_key: str = None,
    secret_key: str = None,
) -> bool:
    """Initialize Langfuse client for tracing.

    Reads from environment variables if args not provided:
        LANGFUSE_HOST (default: http://localhost:3000)
        LANGFUSE_PUBLIC_KEY
        LANGFUSE_SECRET_KEY

    Returns True if successfully initialized, False if not available.
    """
    global _client

    if not LANGFUSE_AVAILABLE:
        logger.info("Langfuse not installed — tracing disabled. pip install langfuse")
        return False

    host = host or os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
    public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        logger.info(
            "Langfuse keys not configured — tracing disabled. "
            "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY env vars. "
            "Or run 'docker compose -f docker/langfuse.yml up -d' and create keys at %s",
            host,
        )
        return False

    try:
        _client = Langfuse(
            host=host,
            public_key=public_key,
            secret_key=secret_key,
        )
        # Test connection.
        _client.auth_check()
        logger.info("Langfuse initialized — tracing to %s", host)
        return True
    except Exception as e:
        logger.warning("Langfuse init failed: %s — tracing disabled", e)
        _client = None
        return False


def get_client() -> Optional[Any]:
    """Get the Langfuse client instance."""
    return _client


@contextmanager
def trace_turn(
    session_key: str,
    user_prompt: str,
    model: str = "",
    intent: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator:
    """Context manager to trace an entire agent turn.

    Usage:
        with trace_turn("session-123", "Fix the bug") as trace:
            result = run_agent(...)
            trace.update(output=result)
    """
    if _client is None:
        yield _NoOpTrace()
        return

    trace = _client.trace(
        name="agent_turn",
        session_id=session_key,
        input=user_prompt,
        metadata={
            "model": model,
            "intent": intent,
            **(metadata or {}),
        },
    )

    try:
        yield trace
    except Exception as e:
        trace.update(
            status_message=f"Error: {e}",
            level="ERROR",
        )
        raise
    finally:
        _client.flush()


class _NoOpTrace:
    """No-op trace when Langfuse is not available."""
    def update(self, **kwargs): pass
    def end(self, **kwargs): pass
    def span(self, **kwargs): return self
    def generation(self, **kwargs): return self
    def score(self, **kwargs): pass


def trace_llm_call(
    model: str,
    messages: list,
    response: Any = None,
    tokens: int = 0,
    cost: float = 0.0,
    intent: str = "",
) -> None:
    """Record an individual LLM call to Langfuse.

    Call after every litellm.completion() for fine-grained tracing.
    """
    if _client is None:
        return

    try:
        if LANGFUSE_AVAILABLE:
            langfuse_context.update_current_observation(
                model=model,
                input=messages,
                output=response,
                usage={"total_tokens": tokens},
                metadata={"cost_usd": cost, "intent": intent},
            )
    except Exception:
        pass  # Never crash on observability.


def trace_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    result: Any = None,
    duration_ms: float = 0,
    error: str = "",
) -> None:
    """Record a tool invocation to Langfuse."""
    if _client is None:
        return

    try:
        if LANGFUSE_AVAILABLE:
            langfuse_context.update_current_observation(
                name=f"tool:{tool_name}",
                input=args,
                output=result,
                metadata={
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )
    except Exception:
        pass  # Never crash on observability.


def flush() -> None:
    """Flush any pending traces to Langfuse."""
    if _client:
        try:
            _client.flush()
        except Exception:
            pass


# Docker Compose template for self-hosted Langfuse.
DOCKER_COMPOSE_TEMPLATE = """\
# docker/langfuse.yml — Self-hosted Langfuse for Hermes Agent
# Usage: docker compose -f docker/langfuse.yml up -d
# Dashboard: http://localhost:3000

version: "3.8"

services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: "postgresql://langfuse:langfuse@postgres:5432/langfuse"
      NEXTAUTH_SECRET: "hermes-aizen-secret-change-me"
      SALT: "hermes-aizen-salt-change-me"
      NEXTAUTH_URL: "http://localhost:3000"
      TELEMETRY_ENABLED: "false"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    volumes:
      - langfuse_pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  langfuse_pg_data:
"""
