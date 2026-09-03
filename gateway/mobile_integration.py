"""Mobile server integration — wires the mobile HTTP API into the gateway lifecycle.

This module provides a single entry point ``start_mobile_api()`` that:
1. Loads or creates the MobileAuth instance
2. Creates the gateway bridge (status, send_message, approve, steer)
3. Starts the MobileAPIServer on the configured port

Import and call from the dashboard/gateway startup sequence:
    from gateway.mobile_integration import start_mobile_api
    mobile_server = start_mobile_api(hermes_home)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default port for the mobile API server
MOBILE_API_PORT = int(os.environ.get("HERMES_MOBILE_PORT", "8765"))


def start_mobile_api(
    hermes_home: Path,
    gateway_state: Optional[Dict[str, Any]] = None,
    *,
    port: int = MOBILE_API_PORT,
    host: str = "0.0.0.0",
) -> Any:
    """Start the mobile API server alongside the dashboard.

    Args:
        hermes_home: Path to the Hermes home directory (~/.hermes)
        gateway_state: Dict with gateway runtime state for the bridge
        port: Port to bind the mobile API server (default: 8765)
        host: Host to bind (default: 0.0.0.0 for LAN access)
    """
    from gateway.mobile_auth import MobileAuth
    from gateway.mobile_server import MobileAPIServer

    auth = MobileAuth(hermes_home=hermes_home)
    bridge = _build_bridge(gateway_state or {})
    server = MobileAPIServer(
        mobile_auth=auth,
        gateway_bridge=bridge,
        port=port,
        host=host,
    )

    try:
        server.start()
        logger.info(
            "Mobile API started — PIN auth on %s:%d (LAN: http://<your-ip>:%d)",
            host, port, port,
        )
    except OSError as e:
        if e.errno == 10048 or e.errno == 98:  # EADDRINUSE on Windows / Linux
            logger.warning(
                "Mobile API port %d already in use — skipping mobile server. "
                "Set HERMES_MOBILE_PORT to use a different port.",
                port,
            )
            return None
        raise

    return server


def _session_target() -> Optional[Dict[str, Any]]:
    from gateway.focused_session import pick_live_session

    return pick_live_session()


def _run_on_loop(coro: Any, timeout: float) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _build_bridge(gateway_state: Dict[str, Any]) -> Dict[str, Any]:
    """Bridge mobile handlers to the focused desktop session."""
    import time

    start_time = time.time()

    def get_status() -> Dict[str, Any]:
        uptime_s = int(time.time() - start_time)
        hours, remainder = divmod(uptime_s, 3600)
        minutes, _ = divmod(remainder, 60)
        target = _session_target()
        return {
            "model": (target or {}).get("model") or gateway_state.get("model", "Not configured"),
            "active_sessions": gateway_state.get("active_sessions", 0),
            "tokens_used": gateway_state.get("tokens_used", "—"),
            "uptime": f"{hours}h {minutes}m",
            "focused_session_id": (target or {}).get("session_id"),
        }

    def send_message(message: str, scope: str) -> str:
        handler = gateway_state.get("message_handler")
        if handler and callable(handler):
            try:
                return handler(message, scope)
            except Exception as e:
                logger.error("Mobile message handler error: %s", e)
                return f"Error: {e}"

        target = _session_target()
        if not target:
            return (
                "No focused desktop session. Open a chat in Hermes desktop first."
            )

        from gateway.session_prompt import find_live_session, run_session_prompt

        live = find_live_session(target["session_id"])
        if live is not None and live.get("running"):
            agent = live.get("agent")
            redirect = getattr(agent, "redirect", None) if agent is not None else None
            if callable(redirect):
                try:
                    accepted = redirect(message)
                except Exception as e:
                    return f"Steer failed: {e}"
                return "Steered the live turn." if accepted else "Steer rejected."
            return "Session is busy with another turn. Wait or send /stop from desktop."

        try:
            return str(
                _run_on_loop(
                    run_session_prompt(
                        message,
                        timeout=120.0,
                        session_id=target["session_id"],
                        cwd=target.get("cwd"),
                        model=target.get("model"),
                        persist=True,
                    ),
                    120.0,
                )
            )
        except RuntimeError as e:
            if "busy" in str(e).lower():
                return "Session is busy with another turn."
            return f"Error: {e}"
        except Exception as e:
            logger.error("Mobile chat failed: %s", e)
            return f"Error: {e}"

    def list_pending() -> Dict[str, Any]:
        target = _session_target()
        if not target:
            return {"session_id": None, "approvals": []}
        try:
            from tools.approval import list_gateway_approvals

            key = str(target.get("session_key") or target["session_id"])
            return {
                "session_id": target["session_id"],
                "approvals": list_gateway_approvals(key),
            }
        except Exception as e:
            logger.error("Mobile pending approvals failed: %s", e)
            return {"session_id": target["session_id"], "approvals": [], "error": str(e)}

    def resolve_approval(choice: str, request_id: Optional[str] = None) -> Dict[str, Any]:
        target = _session_target()
        if not target:
            return {"ok": False, "error": "No focused session"}
        mapped = (choice or "").strip().lower()
        if mapped in {"approve", "allow", "yes", "once"}:
            mapped = "once"
        elif mapped in {"deny", "reject", "no"}:
            mapped = "deny"
        else:
            return {"ok": False, "error": "choice must be approve or deny"}
        try:
            from tools.approval import resolve_gateway_approval

            key = str(target.get("session_key") or target["session_id"])
            resolved = resolve_gateway_approval(
                key,
                mapped,
                request_id=request_id,
            )
            return {"ok": True, "resolved": resolved, "choice": mapped}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def steer(text: str) -> str:
        return send_message(text, "operator")

    return {
        "get_status": get_status,
        "send_message": send_message,
        "list_pending": list_pending,
        "resolve_approval": resolve_approval,
        "steer": steer,
    }


def stop_mobile_api(server: Any) -> None:
    """Gracefully stop the mobile API server."""
    if server is not None and hasattr(server, "stop"):
        server.stop()
        logger.info("Mobile API server stopped")
