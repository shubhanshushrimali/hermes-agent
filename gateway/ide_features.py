"""
IDE Features Gateway Handler — inline edit + ghost text completion.

Adds two HTTP POST endpoints to the gateway API server:
  POST /api/ide/inline-edit
  POST /api/ide/ghost-completion

Both endpoints forward the request to the agent for processing and
stream back the result. Used by the desktop app's Cmd+K inline edit
and ghost text suggestion features.

Part of Phase 4: IDE-Grade Code Experience.
"""

import json
import logging
import asyncio
from typing import Any, Dict, Optional

logger = logging.getLogger("hermes.ide_features")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

def _validate_inline_edit_request(data: Dict[str, Any]) -> Optional[str]:
    """Validate an inline edit request. Returns error message or None."""
    if not isinstance(data.get("filePath"), str):
        return "Missing or invalid 'filePath'"
    if not isinstance(data.get("selectedCode"), str):
        return "Missing or invalid 'selectedCode'"
    if not isinstance(data.get("instruction"), str):
        return "Missing or invalid 'instruction'"
    return None


def _validate_ghost_completion_request(data: Dict[str, Any]) -> Optional[str]:
    """Validate a ghost completion request. Returns error message or None."""
    if not isinstance(data.get("prefix"), str):
        return "Missing or invalid 'prefix'"
    if not isinstance(data.get("filePath"), str):
        return "Missing or invalid 'filePath'"
    return None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_inline_edit_prompt(data: Dict[str, Any]) -> str:
    """Build a prompt for the agent from an inline edit request."""
    parts = []
    parts.append(f"File: {data['filePath']}")
    if data.get("language"):
        parts.append(f"Language: {data['language']}")
    parts.append("")
    parts.append("## Selected Code")
    parts.append("```")
    parts.append(data["selectedCode"])
    parts.append("```")

    if data.get("contextBefore"):
        parts.append("")
        parts.append("## Context Before")
        parts.append("```")
        parts.append(data["contextBefore"])
        parts.append("```")

    if data.get("contextAfter"):
        parts.append("")
        parts.append("## Context After")
        parts.append("```")
        parts.append(data["contextAfter"])
        parts.append("```")

    parts.append("")
    parts.append("## Instruction")
    parts.append(data["instruction"])
    parts.append("")
    parts.append(
        "Respond with ONLY the replacement code. "
        "No explanations, no markdown fences, no surrounding context."
    )
    return "\n".join(parts)


def _build_ghost_completion_prompt(data: Dict[str, Any]) -> str:
    """Build a prompt for the agent from a ghost completion request."""
    parts = []
    parts.append(f"File: {data['filePath']}")
    if data.get("language"):
        parts.append(f"Language: {data['language']}")
    parts.append("")
    parts.append("Complete the code that follows. Provide ONLY the completion text")
    parts.append("(the characters that come next). No explanations, no code fences.")
    parts.append("Maximum 3 lines.")
    parts.append("")
    parts.append("## Code so far")
    parts.append("```")
    parts.append(data["prefix"][-500:])
    parts.append("```")

    if data.get("suffix"):
        parts.append("")
        parts.append("## Code after cursor")
        parts.append("```")
        parts.append(data["suffix"][:200])
        parts.append("```")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Route handler factory
# ---------------------------------------------------------------------------

def register_ide_routes(app: Any, get_agent_fn: Any) -> None:
    """
    Register IDE feature routes on an aiohttp app.

    Parameters
    ----------
    app : aiohttp.web.Application
        The running aiohttp application.
    get_agent_fn : callable
        A function that returns the current agent instance
        (or None if no agent is loaded).
    """
    try:
        from aiohttp import web
    except ImportError:
        logger.warning("aiohttp not available — IDE routes not registered")
        return

    async def handle_inline_edit(request: web.Request) -> web.Response:
        """Handle POST /api/ide/inline-edit."""
        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"ok": False, "error": "Invalid JSON body"},
                status=400,
            )

        error = _validate_inline_edit_request(data)
        if error:
            return web.json_response(
                {"ok": False, "error": error},
                status=400,
            )

        agent = get_agent_fn()
        if agent is None:
            return web.json_response(
                {"ok": False, "error": "No agent loaded"},
                status=503,
            )

        prompt = _build_inline_edit_prompt(data)
        logger.info(
            "Inline edit request: %s (%d chars selected)",
            data["filePath"],
            len(data["selectedCode"]),
        )

        try:
            # Use the agent's chat method to get a response.
            # This is a simplified integration — production would
            # use the agent's streaming interface.
            replacement = await _ask_agent(agent, prompt, timeout=30.0)
            return web.json_response({"ok": True, "replacement": replacement})
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Agent response timed out"},
                status=504,
            )
        except Exception as e:
            logger.exception("Inline edit failed")
            return web.json_response(
                {"ok": False, "error": str(e)},
                status=500,
            )

    async def handle_ghost_completion(request: web.Request) -> web.Response:
        """Handle POST /api/ide/ghost-completion."""
        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"ok": False, "error": "Invalid JSON body"},
                status=400,
            )

        error = _validate_ghost_completion_request(data)
        if error:
            return web.json_response(
                {"ok": False, "error": error},
                status=400,
            )

        agent = get_agent_fn()
        if agent is None:
            return web.json_response(
                {"ok": False, "error": "No agent loaded"},
                status=503,
            )

        prompt = _build_ghost_completion_prompt(data)

        try:
            completion = await _ask_agent(agent, prompt, timeout=5.0)
            # Limit ghost text to 3 lines max.
            lines = completion.split("\n")[:3]
            completion = "\n".join(lines)
            return web.json_response({"ok": True, "completion": completion})
        except asyncio.TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Timeout"},
                status=504,
            )
        except Exception as e:
            logger.exception("Ghost completion failed")
            return web.json_response(
                {"ok": False, "error": str(e)},
                status=500,
            )

    # Register routes
    app.router.add_post("/api/ide/inline-edit", handle_inline_edit)
    app.router.add_post("/api/ide/ghost-completion", handle_ghost_completion)
    logger.info("IDE feature routes registered: /api/ide/inline-edit, /api/ide/ghost-completion")


# ---------------------------------------------------------------------------
# Agent interaction helper
# ---------------------------------------------------------------------------

async def _ask_agent(agent: Any, prompt: str, timeout: float = 30.0) -> str:
    """
    Send a prompt to the agent and collect the response.

    This is a simplified interface — it calls the agent's generate method
    directly. In production, this would use the full streaming pipeline.
    """
    # Try the agent's direct chat method first.
    if hasattr(agent, "chat_raw"):
        result = await asyncio.wait_for(
            asyncio.coroutine(agent.chat_raw)(prompt)
            if not asyncio.iscoroutinefunction(agent.chat_raw)
            else agent.chat_raw(prompt),
            timeout=timeout,
        )
        return str(result).strip()

    # Fallback: use the model's generate interface.
    if hasattr(agent, "model") and hasattr(agent.model, "generate"):
        result = await asyncio.wait_for(
            agent.model.generate(prompt),
            timeout=timeout,
        )
        if isinstance(result, dict):
            return str(result.get("text", result.get("content", ""))).strip()
        return str(result).strip()

    # Last resort: simple pass-through (for testing).
    return f"[IDE feature] Agent does not support direct generation.\nPrompt: {prompt[:200]}..."
