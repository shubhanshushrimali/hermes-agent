"""Pre-tool consequence gate for mutating file/shell tools.

Blocks write_file / patch / terminal until the assistant names blast radius
in the same turn. The block attaches a compact responsible-action excerpt
so the model can retry without a separate skill_view round-trip.

YOLO sessions skip the gate. Prompt-cache is untouched: this is a tool
result, not a system-prompt block.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

CONSEQUENCE_TOOLS = frozenset({"write_file", "patch", "terminal"})

_BLAST_RADIUS = re.compile(
    r"\b(blast radius|reversible|irreversible|affects|will (change|delete|overwrite|run)|scope)\b",
    re.IGNORECASE,
)

_RESPONSIBLE_ACTION_EXCERPT = (
    "Load skill_view(name='responsible-action') if you need the full skill. "
    "Before retrying: in one line name (1) what will change, (2) who/what it "
    "affects, (3) whether it is reversible. Then call the tool again."
)


def capture_assistant_for_consequence_gate(agent: Any, assistant_message: Any) -> None:
    """Stash this turn's assistant text so the gate can see it before tools run."""
    chunks: list[str] = []
    content = getattr(assistant_message, "content", None)
    if isinstance(content, str):
        chunks.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                chunks.append(part)
    reasoning = getattr(assistant_message, "reasoning_content", None) or getattr(
        assistant_message, "reasoning", None
    )
    if isinstance(reasoning, str):
        chunks.append(reasoning)
    text = "\n".join(c for c in chunks if c).strip()
    try:
        agent._consequence_gate_passed = False
        agent._consequence_assistant_text = text
    except Exception:
        pass


def _yolo(agent: Any) -> bool:
    if bool(getattr(agent, "yolo_mode", False)):
        return True
    cfg = getattr(agent, "_session_init_model_config", None)
    if isinstance(cfg, dict) and cfg.get("yolo_mode"):
        return True
    try:
        from tools.approval import is_session_yolo_enabled

        sid = str(getattr(agent, "session_id", "") or "")
        if sid and is_session_yolo_enabled(sid):
            return True
    except Exception:
        pass
    return False


def _responsible_excerpt() -> str:
    try:
        skill = Path(__file__).resolve().parent.parent / "skills" / "autonomous-ai-agents" / "responsible-action" / "SKILL.md"
        raw = skill.read_text(encoding="utf-8")
        body = raw.split("# Responsible action", 1)[-1].strip()
        lines = [ln for ln in body.splitlines() if ln.strip() and not ln.startswith("---")]
        excerpt = "\n".join(lines[:18]).strip()
        if excerpt:
            return excerpt[:1200]
    except Exception:
        pass
    return _RESPONSIBLE_ACTION_EXCERPT


def _has_blast_radius(text: str) -> bool:
    t = (text or "").strip()
    if len(t) >= 80:
        return True
    return bool(_BLAST_RADIUS.search(t))


def consequence_pre_tool_block(agent: Any, tool_name: str) -> Optional[str]:
    """Return a block message, or None to allow the call."""
    if tool_name not in CONSEQUENCE_TOOLS:
        return None
    if not bool(getattr(agent, "_consequence_guidance", True)):
        return None
    if _yolo(agent):
        return None
    if bool(getattr(agent, "_consequence_gate_passed", False)):
        return None
    text = str(getattr(agent, "_consequence_assistant_text", "") or "")
    if _has_blast_radius(text):
        try:
            agent._consequence_gate_passed = True
        except Exception:
            pass
        return None
    excerpt = _responsible_excerpt()
    return (
        f"Blocked {tool_name}: name the blast radius before this mutating tool. "
        f"{_RESPONSIBLE_ACTION_EXCERPT}\n\n{excerpt}"
    )
