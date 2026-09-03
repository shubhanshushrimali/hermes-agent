"""
IDE Features Gateway Handler — inline edit + ghost text completion.

Adds HTTP endpoints to the gateway API server:
  POST /api/ide/inline-edit
  POST /api/ide/ghost-completion

Cmd+K runs a session turn through ``run_session_prompt`` (same runtime as
dashboard chat). Ghost text is a cheap ``call_llm`` completion: no tools,
never persisted, cached by file+prefix.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from gateway.session_prompt import (
    find_live_session,
    run_session_prompt,
    session_turn_kwargs,
    strip_code_fences,
)

logger = logging.getLogger("hermes.ide_features")

_GHOST_CACHE: OrderedDict[str, Tuple[float, str]] = OrderedDict()
_GHOST_CACHE_LOCK = threading.Lock()
_GHOST_CACHE_TTL_S = 60.0
_GHOST_CACHE_MAX = 64
_GHOST_INSTRUCTIONS = (
    "You complete source code at the cursor. Return ONLY the characters that "
    "should be inserted next. No markdown fences, no quotes, no explanation. "
    "Maximum 3 lines. Prefer a short, high-confidence completion."
)


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
        "Respond with ONLY the replacement for the selected code. "
        "Keep the change as small as possible — do not rewrite the whole "
        "file or surrounding context. No explanations, no markdown fences."
    )
    return "\n".join(parts)


def _build_ghost_completion_prompt(data: Dict[str, Any]) -> str:
    """Build the user payload for a ghost completion request."""
    parts = []
    parts.append(f"File: {data['filePath']}")
    if data.get("language"):
        parts.append(f"Language: {data['language']}")
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


def _ghost_cache_key(data: Dict[str, Any]) -> str:
    prefix = str(data.get("prefix") or "")[-200:]
    suffix = str(data.get("suffix") or "")[:100]
    return f"{data.get('filePath')}::{prefix}::{suffix}"


def _ghost_cache_get(key: str) -> Optional[str]:
    with _GHOST_CACHE_LOCK:
        hit = _GHOST_CACHE.get(key)
        if hit is None:
            return None
        ts, text = hit
        if time.monotonic() - ts > _GHOST_CACHE_TTL_S:
            _GHOST_CACHE.pop(key, None)
            return None
        _GHOST_CACHE.move_to_end(key)
        return text


def _ghost_cache_put(key: str, text: str) -> None:
    with _GHOST_CACHE_LOCK:
        _GHOST_CACHE[key] = (time.monotonic(), text)
        _GHOST_CACHE.move_to_end(key)
        while len(_GHOST_CACHE) > _GHOST_CACHE_MAX:
            _GHOST_CACHE.popitem(last=False)


def clear_ghost_cache_for_tests() -> None:
    with _GHOST_CACHE_LOCK:
        _GHOST_CACHE.clear()


def _ghost_main_runtime(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kwargs = session_turn_kwargs(data)
    runtime: Dict[str, Any] = {}
    live = find_live_session(kwargs["session_id"]) if kwargs["session_id"] else None
    if live is not None:
        agent = live.get("agent")
        if agent is not None:
            for field in ("provider", "model", "base_url", "api_key", "api_mode"):
                value = getattr(agent, field, None)
                if isinstance(value, str) and value.strip():
                    runtime[field] = value.strip()
        override = live.get("model_override")
        if isinstance(override, dict):
            model = str(override.get("model") or "").strip()
            if model:
                runtime.setdefault("model", model)
        elif isinstance(override, str) and override.strip():
            runtime.setdefault("model", override.strip())
    if kwargs["model"]:
        runtime["model"] = kwargs["model"]
    return runtime or None


def run_ghost_completion(data: Dict[str, Any]) -> str:
    """Cheap completion: one ``call_llm``, no tools, never persisted."""
    key = _ghost_cache_key(data)
    cached = _ghost_cache_get(key)
    if cached is not None:
        return cached

    from agent.oneshot import run_oneshot

    text = run_oneshot(
        instructions=_GHOST_INSTRUCTIONS,
        user_input=_build_ghost_completion_prompt(data),
        task="title_generation",
        max_tokens=80,
        temperature=0.0,
        timeout=5.0,
        main_runtime=_ghost_main_runtime(data),
    )
    lines = strip_code_fences(text or "").split("\n")[:3]
    completion = "\n".join(line for line in lines if line is not None).rstrip()
    if completion:
        _ghost_cache_put(key, completion)
    return completion


async def run_ghost_completion_async(data: Dict[str, Any], *, timeout: float = 5.0) -> str:
    return await asyncio.wait_for(
        asyncio.to_thread(run_ghost_completion, data),
        timeout=timeout,
    )


def register_ide_routes(app: Any, get_agent_fn: Any = None) -> None:
    """Register IDE feature routes on an aiohttp app.

    ``get_agent_fn`` is ignored. Turns go through ``app['api_server_adapter']``.
    """
    try:
        from aiohttp import web
    except ImportError:
        logger.warning("aiohttp not available — IDE routes not registered")
        return

    async def handle_inline_edit(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"ok": False, "error": "Invalid JSON body"},
                status=400,
            )

        error = _validate_inline_edit_request(data)
        if error:
            return web.json_response({"ok": False, "error": error}, status=400)

        adapter = request.app.get("api_server_adapter")
        prompt = _build_inline_edit_prompt(data)
        logger.info(
            "Inline edit request: %s (%d chars selected)",
            data["filePath"],
            len(data["selectedCode"]),
        )
        kwargs = session_turn_kwargs(data)
        session_id = kwargs["session_id"] or f"ide_edit_{uuid.uuid4().hex[:8]}"
        try:
            replacement = await run_session_prompt(
                prompt,
                timeout=30.0,
                session_id=session_id,
                adapter=adapter,
                cwd=kwargs["cwd"],
                model=kwargs["model"],
                persist=bool(kwargs["session_id"]),
            )
            return web.json_response({
                "ok": True,
                "replacement": strip_code_fences(replacement),
            })
        except TimeoutError:
            return web.json_response(
                {"ok": False, "error": "Agent response timed out"},
                status=504,
            )
        except RuntimeError as e:
            if "busy" in str(e).lower():
                return web.json_response({"ok": False, "error": str(e)}, status=409)
            logger.exception("Inline edit failed")
            return web.json_response({"ok": False, "error": str(e)}, status=500)
        except Exception as e:
            logger.exception("Inline edit failed")
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def handle_ghost_completion(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"ok": False, "error": "Invalid JSON body"},
                status=400,
            )

        error = _validate_ghost_completion_request(data)
        if error:
            return web.json_response({"ok": False, "error": error}, status=400)

        try:
            completion = await run_ghost_completion_async(data, timeout=5.0)
            return web.json_response({"ok": True, "completion": completion})
        except TimeoutError:
            return web.json_response({"ok": False, "error": "Timeout"}, status=504)
        except Exception as e:
            logger.info("Ghost completion failed: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=200)

    app.router.add_post("/api/ide/inline-edit", handle_inline_edit)
    app.router.add_post("/api/ide/ghost-completion", handle_ghost_completion)
    logger.info("IDE feature routes registered: /api/ide/inline-edit, /api/ide/ghost-completion")