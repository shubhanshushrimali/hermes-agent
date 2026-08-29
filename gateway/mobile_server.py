"""Mobile API Server — HTTP endpoints for the mobile PWA.

Bridges the mobile PWA to the Hermes gateway using a lightweight
HTTP server (no external dependencies — uses stdlib http.server).

Endpoints:
    POST /api/mobile/auth      — PIN authentication
    GET  /api/mobile/status     — Agent status
    POST /api/mobile/chat       — Send message to agent
    GET  /api/mobile/sessions   — List active sessions
    POST /api/mobile/revoke     — Revoke a session
    GET  /api/mobile/qr         — Generate QR pairing data

Runs alongside the gateway on a configurable port (default 8765).

Usage:
    from gateway.mobile_server import MobileAPIServer
    server = MobileAPIServer(mobile_auth, gateway_bridge, port=8765)
    server.start()  # Starts in a background thread
"""

from __future__ import annotations

import json
import logging
import os
import threading
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class MobileRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for mobile API endpoints."""

    # Suppress default access log (we log ourselves)
    def log_message(self, format, *args):
        logger.debug("Mobile API: %s", format % args)

    @property
    def auth(self):
        return self.server.mobile_auth  # type: ignore

    @property
    def bridge(self):
        return self.server.gateway_bridge  # type: ignore

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400) -> None:
        """Send an error JSON response."""
        self._send_json({"error": message}, status)

    def _read_body(self) -> dict:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    def _get_session(self):
        """Extract and verify the session from the Authorization header."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        return self.auth.verify_token(token)

    def _get_client_ip(self) -> str:
        """Get the client IP address."""
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    # ---- CORS preflight ----

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # ---- Routes ----

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/mobile/auth":
            self._handle_auth()
        elif path == "/api/mobile/chat":
            self._handle_chat()
        elif path == "/api/mobile/revoke":
            self._handle_revoke()
        else:
            self._send_error("Not found", 404)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/mobile/status":
            self._handle_status()
        elif path == "/api/mobile/sessions":
            self._handle_sessions()
        elif path == "/api/mobile/qr":
            self._handle_qr()
        elif path == "/api/mobile/health":
            self._send_json({"status": "ok", "version": "aizen-1.0"})
        else:
            self._send_error("Not found", 404)

    # ---- Handlers ----

    def _handle_auth(self):
        """POST /api/mobile/auth — PIN authentication."""
        body = self._read_body()
        pin = body.get("pin", "")
        if not pin:
            self._send_error("PIN required", 400)
            return

        client_ip = self._get_client_ip()
        token = self.auth.verify_pin(pin, client_ip)
        if token:
            logger.info("Mobile auth: success from %s", client_ip)
            self._send_json({"token": token, "expires_in": 3600})
        else:
            logger.info("Mobile auth: failed from %s", client_ip)
            self._send_error("Invalid PIN", 401)

    def _handle_status(self):
        """GET /api/mobile/status — Agent status."""
        session = self._get_session()
        if not session:
            self._send_error("Unauthorized", 401)
            return

        # Get status from the bridge (or defaults)
        status = {}
        if self.bridge:
            status = self.bridge.get("status", {})

        self._send_json({
            "model": status.get("model", "Unknown"),
            "sessions": status.get("active_sessions", 0),
            "tokens": status.get("tokens_used", "—"),
            "uptime": status.get("uptime", "—"),
            "scope": session.scope,
            "connected": True,
        })

    def _handle_chat(self):
        """POST /api/mobile/chat — Send message to agent."""
        session = self._get_session()
        if not session:
            self._send_error("Unauthorized", 401)
            return

        if not self.auth.has_permission(session, "operator"):
            self._send_error("Insufficient permissions (need operator+)", 403)
            return

        body = self._read_body()
        message = body.get("message", "").strip()
        if not message:
            self._send_error("Message required", 400)
            return

        # Queue message via the bridge
        response = "Message received. Agent processing..."
        if self.bridge and callable(self.bridge.get("send_message")):
            try:
                response = self.bridge["send_message"](message, session.scope)
            except Exception as e:
                logger.error("Mobile chat bridge error: %s", e)
                response = f"Bridge error: {e}"

        self._send_json({"response": response})

    def _handle_sessions(self):
        """GET /api/mobile/sessions — List active sessions."""
        session = self._get_session()
        if not session:
            self._send_error("Unauthorized", 401)
            return

        if not self.auth.has_permission(session, "admin"):
            self._send_error("Insufficient permissions (need admin)", 403)
            return

        self._send_json({
            "sessions": self.auth.list_sessions(),
            "pins": self.auth.list_pins(),
        })

    def _handle_revoke(self):
        """POST /api/mobile/revoke — Revoke a session or PIN."""
        session = self._get_session()
        if not session:
            self._send_error("Unauthorized", 401)
            return

        if not self.auth.has_permission(session, "admin"):
            self._send_error("Insufficient permissions", 403)
            return

        body = self._read_body()
        target_session_id = body.get("session_id")
        target_pin_id = body.get("pin_id")

        if target_session_id:
            ok = self.auth.revoke_session(target_session_id)
            self._send_json({"revoked": ok, "type": "session"})
        elif target_pin_id:
            ok = self.auth.revoke_pin(target_pin_id)
            self._send_json({"revoked": ok, "type": "pin"})
        else:
            self._send_error("session_id or pin_id required", 400)

    def _handle_qr(self):
        """GET /api/mobile/qr — Generate QR pairing data."""
        session = self._get_session()
        if not session:
            self._send_error("Unauthorized", 401)
            return

        if not self.auth.has_permission(session, "admin"):
            self._send_error("Insufficient permissions", 403)
            return

        host = self.headers.get("Host", "localhost:8765")
        gateway_url = f"http://{host}"
        qr_data = self.auth.generate_qr_data(gateway_url)
        self._send_json(qr_data)


class MobileAPIServer:
    """Manages the mobile API HTTP server lifecycle."""

    def __init__(
        self,
        mobile_auth,
        gateway_bridge: Optional[Dict[str, Any]] = None,
        port: int = 8765,
        host: str = "0.0.0.0",
    ):
        self.mobile_auth = mobile_auth
        self.gateway_bridge = gateway_bridge or {}
        self.port = port
        self.host = host
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the mobile API server in a background thread."""
        self._server = HTTPServer((self.host, self.port), MobileRequestHandler)
        self._server.mobile_auth = self.mobile_auth  # type: ignore
        self._server.gateway_bridge = self.gateway_bridge  # type: ignore

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="mobile-api-server",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Mobile API server started on %s:%d", self.host, self.port
        )

    def stop(self) -> None:
        """Stop the mobile API server."""
        if self._server:
            self._server.shutdown()
            logger.info("Mobile API server stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
