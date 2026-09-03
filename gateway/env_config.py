"""
Hermes Environment Config Helper — ensures all integration keys are set.

Checks for required environment variables and provides clear guidance
when things are missing. Called at gateway startup.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Tuple

logger = logging.getLogger("hermes.env_config")


def check_integration_env() -> Dict[str, bool]:
    """Check all integration environment variables and return status.

    Called at startup to log what's available.
    """
    checks = {
        # Langfuse (observability)
        "LANGFUSE_SECRET_KEY": bool(os.environ.get("LANGFUSE_SECRET_KEY")),
        "LANGFUSE_PUBLIC_KEY": bool(os.environ.get("LANGFUSE_PUBLIC_KEY")),
        "LANGFUSE_HOST": bool(os.environ.get("LANGFUSE_HOST", "")),
        # LiteLLM (model routing)
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY")),
        # Workspace
        "HERMES_WORKSPACE": bool(os.environ.get("HERMES_WORKSPACE")),
    }
    return checks


def log_startup_status() -> None:
    """Log integration status at startup."""
    status = check_integration_env()

    # Group by service.
    langfuse_ok = status.get("LANGFUSE_SECRET_KEY") and status.get("LANGFUSE_PUBLIC_KEY")
    has_llm_key = (
        status.get("ANTHROPIC_API_KEY")
        or status.get("OPENAI_API_KEY")
        or status.get("GOOGLE_API_KEY")
    )

    logger.info("=== Hermes Aizen Integration Status ===")

    if langfuse_ok:
        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        logger.info("  Langfuse:  ON  (%s)", host)
    else:
        logger.info("  Langfuse:  OFF (set LANGFUSE_SECRET_KEY + LANGFUSE_PUBLIC_KEY)")
        logger.info("             Or: docker compose -f docker/langfuse.yml up -d")

    if has_llm_key:
        providers = []
        if status.get("ANTHROPIC_API_KEY"):
            providers.append("Anthropic")
        if status.get("OPENAI_API_KEY"):
            providers.append("OpenAI")
        if status.get("GOOGLE_API_KEY"):
            providers.append("Google")
        logger.info("  LLM Keys:  %s", ", ".join(providers))
    else:
        logger.info("  LLM Keys:  None (will use local Ollama if available)")

    # Check LangGraph.
    try:
        from langgraph.graph import StateGraph
        logger.info("  LangGraph: ON")
    except ImportError:
        logger.info("  LangGraph: OFF (pip install langgraph)")

    # Check CrewAI.
    try:
        from crewai import Agent
        logger.info("  CrewAI:    ON")
    except ImportError:
        logger.info("  CrewAI:    OFF (pip install crewai)")

    # Check Graphify.
    try:
        import graphify
        logger.info("  Graphify:  ON")
    except ImportError:
        logger.info("  Graphify:  OFF (pip install graphify)")

    logger.info("========================================")


def setup_langfuse_local() -> None:
    """Configure Langfuse for local Docker instance if no keys set.

    If the user runs `docker compose -f docker/langfuse.yml up`,
    the default keys are pre-seeded in the compose file.
    Auto-detects if Langfuse is running on localhost:3000.
    """
    if os.environ.get("LANGFUSE_SECRET_KEY"):
        return  # User has custom keys — don't override.

    # Use the seeded keys from docker/langfuse.yml.
    os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-hermes-local")
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-hermes-local")
    os.environ.setdefault("LANGFUSE_HOST", "http://localhost:3000")

    # Check if Langfuse is actually reachable.
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:3000/api/public/health",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                logger.info("  Langfuse:  AUTO-CONFIGURED (Docker localhost:3000)")
                return
    except Exception:
        pass

    logger.debug("Langfuse keys set but service not reachable yet")


def auto_configure_integrations() -> None:
    """Auto-configure all integrations at startup.

    Call this from aizen_extensions to set up everything.
    """
    setup_langfuse_local()

