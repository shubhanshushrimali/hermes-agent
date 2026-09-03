"""MCP Apps — Interactive UI Components in Chat.

Allows tools to render interactive HTML/React micro-apps directly
in the chat stream. Apps are sandboxed iframes with a message-passing
bridge to the agent.

Part of Phase 7: Advanced Features.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MCPApp:
    """A renderable micro-app that appears inline in chat."""

    app_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    html: str = ""
    width: str = "100%"
    height: str = "400px"
    theme: str = "aizen"
    data: Dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> Dict[str, Any]:
        """Serialize for the chat stream."""
        return {
            "type": "mcp_app",
            "app_id": self.app_id,
            "name": self.name,
            "description": self.description,
            "html": self.html,
            "width": self.width,
            "height": self.height,
            "theme": self.theme,
            "data": self.data,
        }


class MCPAppRegistry:
    """Registry for built-in MCP Apps."""

    _apps: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register an MCP App builder."""
        def decorator(fn):
            cls._apps[name] = fn
            return fn
        return decorator

    @classmethod
    def build(cls, name: str, **kwargs) -> Optional[MCPApp]:
        """Build an MCP App by name."""
        builder = cls._apps.get(name)
        if builder:
            return builder(**kwargs)
        return None

    @classmethod
    def list_apps(cls) -> List[str]:
        return list(cls._apps.keys())

    @classmethod
    def describe_apps(cls) -> List[Dict[str, Any]]:
        """Catalog entries for GET /api/mcp/apps (id + built metadata)."""
        payloads: List[Dict[str, Any]] = []
        for name in cls.list_apps():
            built = cls.build(name)
            if built is None:
                payloads.append({"id": name, "name": name, "description": ""})
                continue
            msg = built.to_message()
            msg["id"] = name
            payloads.append(msg)
        return payloads


# ---- Built-in Apps ----

@MCPAppRegistry.register("json-viewer")
def build_json_viewer(data: Any = None, **kwargs) -> MCPApp:
    """Interactive JSON tree viewer."""
    return MCPApp(
        name="JSON Viewer",
        description="Interactive JSON tree",
        html=f"""
        <div id="root" style="font-family: 'JetBrains Mono', monospace; font-size: 13px;
             color: #E4E4E7; background: #12151A; padding: 16px; overflow: auto;">
          <pre>{json.dumps(data, indent=2, default=str) if data else '{}'}</pre>
        </div>
        """,
        height="300px",
        data={"raw": data},
    )


@MCPAppRegistry.register("metrics-dashboard")
def build_metrics_dashboard(metrics: Dict[str, Any] = None, **kwargs) -> MCPApp:
    """Real-time metrics dashboard."""
    metrics = metrics or {}
    cards_html = ""
    for key, value in metrics.items():
        cards_html += f"""
        <div style="background: #1A1D24; border: 1px solid #23262F; border-radius: 12px;
                    padding: 16px; text-align: center;">
          <div style="font-size: 11px; color: #A1A1AA; text-transform: uppercase;
                      letter-spacing: 0.05em;">{key}</div>
          <div style="font-size: 24px; font-weight: 600; margin-top: 4px;
                      color: #6366F1;">{value}</div>
        </div>
        """
    return MCPApp(
        name="Metrics Dashboard",
        description="Agent performance metrics",
        html=f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                    gap: 12px; padding: 16px; font-family: Inter, system-ui, sans-serif;
                    background: #0B0D10;">
          {cards_html}
        </div>
        """,
        height="200px",
        data=metrics,
    )


@MCPAppRegistry.register("diff-viewer")
def build_diff_viewer(diff: str = "", filename: str = "", **kwargs) -> MCPApp:
    """Code diff viewer with syntax highlighting."""
    lines = diff.split("\n")
    rendered = ""
    for line in lines:
        if line.startswith("+"):
            color = "#22C55E"
            bg = "rgba(34, 197, 94, 0.1)"
        elif line.startswith("-"):
            color = "#EF4444"
            bg = "rgba(239, 68, 68, 0.1)"
        else:
            color = "#A1A1AA"
            bg = "transparent"
        escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rendered += f'<div style="color: {color}; background: {bg}; padding: 2px 12px;">{escaped}</div>'

    return MCPApp(
        name="Diff Viewer",
        description=f"Changes in {filename}" if filename else "Code diff",
        html=f"""
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 12px;
                    line-height: 1.6; background: #12151A; overflow: auto;
                    border-radius: 8px;">
          {rendered}
        </div>
        """,
        height="350px",
        data={"diff": diff, "filename": filename},
    )
