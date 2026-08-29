"""Mobile server integration — wires the mobile HTTP API into the gateway lifecycle.

This module provides a single entry point ``start_mobile_api()`` that:
1. Loads or creates the MobileAuth instance
2. Creates the gateway bridge (status, send_message callbacks)
3. Starts the MobileAPIServer on the configured port

Import and call from the gateway startup sequence:
    from gateway.mobile_integration import start_mobile_api
    mobile_server = start_mobile_api(hermes_home, gateway_state)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

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
    """Start the mobile API server alongside the gateway.

    Args:
        hermes_home: Path to the Hermes home directory (~/.hermes)
        gateway_state: Dict with gateway runtime state for the bridge
        port: Port to bind the mobile API server (default: 8765)
        host: Host to bind (default: 0.0.0.0 for LAN access)

    Returns:
        The MobileAPIServer instance (call .stop() to shut down)
    """
    from gateway.mobile_auth import MobileAuth
    from gateway.mobile_server import MobileAPIServer

    # Initialize the auth system
    auth = MobileAuth(hermes_home=hermes_home)

    # Build the gateway bridge — callbacks that the mobile server uses
    # to interact with the gateway's state
    bridge = _build_bridge(gateway_state or {})

    # Start the HTTP server
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


def _build_bridge(gateway_state: Dict[str, Any]) -> Dict[str, Any]:
    """Build the bridge dict that connects mobile API handlers to the gateway.

    The bridge provides:
    - status: Dict with model, active_sessions, tokens_used, uptime
    - send_message: Callable to queue a message to the active agent session
    """
    import time

    start_time = time.time()

    def get_status() -> Dict[str, Any]:
        """Get current gateway status for mobile display."""
        uptime_s = int(time.time() - start_time)
        hours, remainder = divmod(uptime_s, 3600)
        minutes, _ = divmod(remainder, 60)

        return {
            "model": gateway_state.get("model", "Not configured"),
            "active_sessions": gateway_state.get("active_sessions", 0),
            "tokens_used": gateway_state.get("tokens_used", "—"),
            "uptime": f"{hours}h {minutes}m",
        }

    def send_message(message: str, scope: str) -> str:
        """Queue a message to the active agent session.

        Returns a response string. In a full integration, this would
        push to the gateway's message queue and return the agent's reply.
        """
        # Check if there's a message handler registered
        handler = gateway_state.get("message_handler")
        if handler and callable(handler):
            try:
                return handler(message, scope)
            except Exception as e:
                logger.error("Mobile message handler error: %s", e)
                return f"Error: {e}"

        # Default: acknowledge receipt
        logger.info("Mobile message received (scope=%s): %s", scope, message[:100])
        return (
            f"Message queued for processing. "
            f"Scope: {scope}. "
            f"Length: {len(message)} chars."
        )

    return {
        "status": property(lambda _: get_status()),
        "get_status": get_status,
        "send_message": send_message,
    }


def stop_mobile_api(server: Any) -> None:
    """Gracefully stop the mobile API server."""
    if server is not None and hasattr(server, "stop"):
        server.stop()
        logger.info("Mobile API server stopped")
