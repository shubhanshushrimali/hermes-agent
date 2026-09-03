"""IDE Cmd+K + ghost-text routes on the dashboard (desktop conn.baseUrl)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gateway.ide_features import (
    _build_inline_edit_prompt,
    _validate_ghost_completion_request,
    _validate_inline_edit_request,
    run_ghost_completion_async,
)
from gateway.session_prompt import run_session_prompt, strip_code_fences

router = APIRouter()


class InlineEditBody(BaseModel):
    filePath: str
    selectedCode: str
    instruction: str
    contextBefore: Optional[str] = None
    contextAfter: Optional[str] = None
    language: Optional[str] = None
    sessionId: Optional[str] = None
    session_id: Optional[str] = None
    cwd: Optional[str] = None
    model: Optional[str] = None


class GhostCompletionBody(BaseModel):
    prefix: str
    filePath: str
    suffix: str = ""
    language: Optional[str] = None
    sessionId: Optional[str] = None
    session_id: Optional[str] = None
    cwd: Optional[str] = None
    model: Optional[str] = None


def _session_fields(body: InlineEditBody | GhostCompletionBody) -> Dict[str, Any]:
    session_id = str(body.sessionId or body.session_id or "").strip()
    cwd = str(body.cwd or "").strip() or None
    model = str(body.model or "").strip() or None
    return {"session_id": session_id, "cwd": cwd, "model": model}


async def _ide_turn(
    prompt: str,
    *,
    timeout: float,
    prefix: str,
    session_id: str,
    cwd: Optional[str],
    model: Optional[str],
    persist: bool,
) -> str:
    return await run_session_prompt(
        prompt,
        timeout=timeout,
        session_id=session_id or f"{prefix}_{uuid.uuid4().hex[:8]}",
        adapter=None,
        cwd=cwd,
        model=model,
        persist=persist and bool(session_id),
    )


@router.post("/api/ide/inline-edit")
async def inline_edit(body: InlineEditBody) -> Dict[str, Any]:
    data = body.model_dump()
    error = _validate_inline_edit_request(data)
    if error:
        raise HTTPException(status_code=400, detail=error)
    fields = _session_fields(body)
    try:
        replacement = await _ide_turn(
            _build_inline_edit_prompt(data),
            timeout=30.0,
            prefix="ide_edit",
            persist=True,
            **fields,
        )
        return {"ok": True, "replacement": strip_code_fences(replacement)}
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Agent response timed out") from exc
    except RuntimeError as exc:
        if "busy" in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/ide/ghost-completion")
async def ghost_completion(body: GhostCompletionBody) -> Dict[str, Any]:
    data = body.model_dump()
    error = _validate_ghost_completion_request(data)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        completion = await run_ghost_completion_async(data, timeout=5.0)
        return {"ok": True, "completion": completion}
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Timeout") from exc
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/api/ide/verify-hint")
async def verify_hint(cwd: str = "") -> Dict[str, Any]:
    """Project test/lint commands for the IDE rail — does not run them."""
    if not (cwd or "").strip():
        return {"ok": True, "commands": [], "facts": None}
    try:
        from agent.coding_context import project_facts_for

        facts = project_facts_for(cwd.strip())
        commands = list((facts or {}).get("verifyCommands") or [])
        return {"ok": True, "commands": commands, "facts": facts}
    except Exception as exc:
        return {"ok": False, "commands": [], "error": str(exc)}
