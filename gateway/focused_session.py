"""The desktop chat the phone (and other sidecars) should join.

Every ``prompt.submit`` pins the live session here so LAN mobile chat is the
same transcript, cwd, and model — not a throwaway conversation.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

_lock = threading.Lock()
_focused: Dict[str, Any] = {}


def set_focused_session(
    *,
    session_id: str,
    session_key: str = "",
    cwd: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    if not session_id:
        return
    with _lock:
        _focused["session_id"] = str(session_id)
        _focused["session_key"] = str(session_key or session_id)
        _focused["cwd"] = (cwd or "").strip() or None
        _focused["model"] = (model or "").strip() or None


def get_focused_session() -> Optional[Dict[str, Any]]:
    with _lock:
        if not _focused.get("session_id"):
            return None
        return dict(_focused)


def pick_live_session() -> Optional[Dict[str, Any]]:
    """Focused pin, else the most recently active in-memory desktop session."""
    pinned = get_focused_session()
    if pinned:
        return pinned
    try:
        from tui_gateway.server import _sessions, _sessions_lock
    except Exception:
        return None
    best: Optional[Dict[str, Any]] = None
    best_t = -1.0
    with _sessions_lock:
        for sid, sess in _sessions.items():
            if not isinstance(sess, dict) or sess.get("_closing"):
                continue
            try:
                last = float(sess.get("last_active") or 0)
            except (TypeError, ValueError):
                last = 0.0
            if last < best_t:
                continue
            best_t = last
            model = None
            override = sess.get("model_override")
            if isinstance(override, dict):
                model = str(override.get("model") or "").strip() or None
            elif isinstance(override, str):
                model = override.strip() or None
            best = {
                "session_id": str(sid),
                "session_key": str(sess.get("session_key") or sid),
                "cwd": str(sess.get("cwd") or "").strip() or None,
                "model": model,
            }
    return best


def reset_focused_session_for_tests() -> None:
    with _lock:
        _focused.clear()
