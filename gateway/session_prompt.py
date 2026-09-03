"""One-shot prompt against the focused session runtime.

Cmd+K and recipe ``agent`` steps share the same turn path as dashboard chat:

* Live desktop/TUI session — reuse the in-memory agent (cwd, history, model)
* Else SessionDB history + ``_make_agent`` / ``APIServerAdapter._run_agent``

Ghost text does **not** use this module — it is a cheap ``call_llm``
completion with no tools and never persists. See ``gateway.ide_features``.

There is no global ``gateway_runner.agent``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional


def _final_text(result: Any) -> str:
    if isinstance(result, dict):
        text = result.get("final_response") or result.get("error") or ""
        return str(text).strip()
    return str(result or "").strip()


def run_ephemeral_turn(
    prompt: str,
    *,
    session_id: str = "graph-engine-ephemeral",
    cwd: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """One agent turn that does not persist to a live desktop session.

    Used by the graph engine execute node (daemon / eval). Desktop chat
    must keep using conversation_loop — never process_prompt().
    """
    return _dashboard_run(
        prompt,
        session_id=session_id,
        cwd=cwd,
        model=model,
        persist=False,
    )


def session_turn_kwargs(data: Dict[str, Any]) -> Dict[str, Any]:
    """Pull focused-session fields from an IDE/recipe JSON body."""
    session_id = str(data.get("sessionId") or data.get("session_id") or "").strip()
    cwd = str(data.get("cwd") or data.get("workspace") or "").strip()
    model = str(data.get("model") or "").strip()
    return {
        "session_id": session_id,
        "cwd": cwd or None,
        "model": model or None,
    }


def strip_code_fences(text: str) -> str:
    """Drop a wrapping markdown fence so Cmd+K can paste the body."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _bind_cwd(session_id: str, cwd: Optional[str]) -> None:
    if not session_id or not (cwd or "").strip():
        return
    try:
        from tools.terminal_tool import register_task_env_overrides

        register_task_env_overrides(session_id, {"cwd": cwd.strip()})
    except Exception:
        pass


def find_live_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Locate the in-memory desktop/TUI session by UI id or stored key."""
    if not session_id:
        return None
    try:
        from tui_gateway.server import _sessions, _sessions_lock
    except Exception:
        return None
    with _sessions_lock:
        direct = _sessions.get(session_id)
        if isinstance(direct, dict):
            return direct
        for sess in _sessions.values():
            if not isinstance(sess, dict):
                continue
            if sess.get("session_key") == session_id:
                return sess
    return None


def _load_db_history(session_id: str) -> List[Dict[str, Any]]:
    try:
        from tui_gateway.server import _get_db

        db = _get_db()
        if db is None:
            return []
        return db.get_messages_as_conversation(session_id, repair_alternation=True)
    except Exception:
        return []


def _model_override(model: Optional[str], live: Optional[Dict[str, Any]]) -> Any:
    if model:
        return {"model": model}
    if live and isinstance(live.get("model_override"), dict):
        return live.get("model_override")
    return None


def _dashboard_run(
    prompt: str,
    *,
    session_id: str,
    cwd: Optional[str],
    model: Optional[str],
    persist: bool,
) -> str:
    live = find_live_session(session_id) if session_id else None
    if live is not None and live.get("running") and persist:
        raise RuntimeError("Session is busy with another turn")

    if not cwd and live:
        cwd = str(live.get("cwd") or "").strip() or None
    if not model and live:
        override = live.get("model_override")
        if isinstance(override, dict):
            model = str(override.get("model") or "").strip() or None
        elif isinstance(override, str):
            model = override.strip() or None

    bind_id = session_id or "ide_ephemeral"
    if cwd:
        _bind_cwd(bind_id, cwd)
        if live is not None and persist:
            live["cwd"] = cwd.strip()
            try:
                from tui_gateway.server import _register_session_cwd

                _register_session_cwd(live)
            except Exception:
                pass

    from tui_gateway.server import _make_agent

    agent = live.get("agent") if live else None
    if agent is not None and persist:
        history = list(live.get("history") or [])
        run = getattr(agent, "run_conversation", None)
        if not callable(run):
            raise RuntimeError("agent has no run_conversation")
        task_id = str(live.get("session_key") or session_id)
        return _final_text(run(prompt, conversation_history=history, task_id=task_id))

    history = _load_db_history(session_id) if persist and session_id else []
    sid = bind_id if persist else f"ide_ghost_{session_id or 'anon'}"
    agent = _make_agent(
        sid,
        sid,
        session_id=session_id if persist and session_id else sid,
        model_override=_model_override(model, live),
    )
    run = getattr(agent, "run_conversation", None)
    if not callable(run):
        raise RuntimeError("agent has no run_conversation")
    return _final_text(
        run(prompt, conversation_history=history, task_id=session_id or sid)
    )


async def run_session_prompt(
    prompt: str,
    *,
    timeout: float,
    session_id: str,
    adapter: Any = None,
    cwd: Optional[str] = None,
    model: Optional[str] = None,
    persist: bool = True,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Run one agent turn on the focused session and return assistant text.

    ``adapter`` is the aiohttp API-server adapter when called from gateway
    routes. Dashboard routes omit it and join the desktop/TUI session.
    """
    if adapter is not None:
        history = conversation_history
        if history is None and session_id:
            history = await adapter._conversation_history_for_session(session_id)
        if history is None:
            history = []
        stored_model = None
        requested_model = model
        if session_id:
            try:
                session, err = await adapter._get_existing_session_or_404(session_id)
                if err is None and session:
                    stored_model = adapter._stored_session_model(session)
            except Exception:
                stored_model = None
        if cwd:
            _bind_cwd(session_id, cwd)
        result, _usage = await asyncio.wait_for(
            adapter._run_agent(
                user_message=prompt,
                conversation_history=history,
                session_id=session_id or None,
                requested_model=requested_model,
                session_model=stored_model,
            ),
            timeout=timeout,
        )
        return _final_text(result)

    return await asyncio.wait_for(
        asyncio.to_thread(
            _dashboard_run,
            prompt,
            session_id=session_id,
            cwd=cwd,
            model=model,
            persist=persist,
        ),
        timeout=timeout,
    )
