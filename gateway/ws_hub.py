"""
WebSocket Hub — real-time panel updates.

Broadcasts panel state changes (git, daemon, crew, cost, streak)
to all connected desktop/PWA clients over WebSocket instead of polling.

Usage (server side):
    from gateway.ws_hub import get_hub, broadcast
    hub = get_hub()
    hub.register_routes(app)              # aiohttp app
    await broadcast("git", {"branch": "main", "ahead": 2})

Usage (client side):
    const ws = new WebSocket('ws://localhost:5005/api/overlay/ws');
    ws.onmessage = (e) => {
        const { channel, data, ts } = JSON.parse(e.data);
        // channel: 'git' | 'daemon' | 'crew' | 'cost' | 'streak' | 'system'
    };

Desktop chat uses the dashboard JSON-RPC socket at ``/api/ws``. This hub
is overlay panel pub/sub only — a different path so the two never collide.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import weakref
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("hermes.ws_hub")

# Overlay panel pub/sub. Desktop JSON-RPC lives on dashboard ``/api/ws``.
OVERLAY_WS_PATH = "/api/overlay/ws"
OVERLAY_WS_STATS_PATH = "/api/overlay/ws/stats"


# ============================================================================
# WebSocket Hub
# ============================================================================

class WebSocketHub:
    """Central pub/sub hub for real-time panel updates.

    Thread-safe: broadcast() can be called from any thread — it schedules
    the actual send on the event loop.
    """

    def __init__(self):
        self._clients: Set[Any] = set()  # weakref set would be ideal but aiohttp ws doesn't support it
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_state: Dict[str, Dict[str, Any]] = {}
        self._message_count = 0

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def register_routes(self, app: Any) -> None:
        """Register the WebSocket endpoint on an aiohttp app."""
        try:
            from aiohttp import web
        except ImportError:
            logger.warning("aiohttp not available — WebSocket hub disabled")
            return

        async def ws_handler(request: web.Request) -> web.WebSocketResponse:
            ws = web.WebSocketResponse(
                heartbeat=30.0,  # Ping every 30s to keep connection alive
                max_msg_size=4 * 1024 * 1024,  # 4MB max
            )
            await ws.prepare(request)

            self._clients.add(ws)
            self._loop = asyncio.get_event_loop()
            client_id = f"ws-{id(ws)}"
            logger.info("WebSocket client connected: %s (total: %d)", client_id, len(self._clients))

            # Send current state snapshot on connect.
            try:
                if self._last_state:
                    await ws.send_json({
                        "channel": "snapshot",
                        "data": self._last_state,
                        "ts": time.time(),
                    })
            except Exception:
                pass

            try:
                async for msg in ws:
                    if msg.type == 1:  # TEXT
                        # Clients can send subscription preferences.
                        try:
                            payload = json.loads(msg.data)
                            cmd = payload.get("cmd")
                            if cmd == "ping":
                                await ws.send_json({"channel": "pong", "ts": time.time()})
                            elif cmd == "subscribe":
                                # Future: per-channel subscriptions.
                                pass
                        except json.JSONDecodeError:
                            pass
                    elif msg.type == 258:  # ERROR
                        logger.warning("WebSocket error from %s: %s", client_id, msg.data)
                        break
            except asyncio.CancelledError:
                pass
            finally:
                self._clients.discard(ws)
                logger.info("WebSocket client disconnected: %s (remaining: %d)", client_id, len(self._clients))

            return ws

        app.router.add_get(OVERLAY_WS_PATH, ws_handler)
        logger.info("WebSocket hub registered at %s", OVERLAY_WS_PATH)

    async def _broadcast_async(self, channel: str, data: Dict[str, Any]) -> int:
        """Broadcast to all connected clients (async)."""
        if not self._clients:
            return 0

        # Cache latest state per channel.
        self._last_state[channel] = data

        message = json.dumps({
            "channel": channel,
            "data": data,
            "ts": time.time(),
        })

        sent = 0
        dead = []
        for ws in list(self._clients):
            try:
                if not ws.closed:
                    await ws.send_str(message)
                    sent += 1
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)

        # Clean up dead connections.
        for ws in dead:
            self._clients.discard(ws)

        self._message_count += 1
        return sent

    def broadcast_sync(self, channel: str, data: Dict[str, Any]) -> None:
        """Broadcast from a sync context (e.g., subprocess callback).

        Thread-safe: schedules the broadcast on the event loop.
        """
        if not self._loop or not self._clients:
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_async(channel, data),
                self._loop,
            )
        except RuntimeError:
            pass  # Event loop closed.

    def get_stats(self) -> Dict[str, Any]:
        """Get hub statistics."""
        return {
            "connected_clients": self.client_count,
            "total_messages": self._message_count,
            "cached_channels": list(self._last_state.keys()),
        }


# ============================================================================
# Singleton
# ============================================================================

_hub: Optional[WebSocketHub] = None


def get_hub() -> WebSocketHub:
    """Get or create the global WebSocket hub."""
    global _hub
    if _hub is None:
        _hub = WebSocketHub()
    return _hub


async def broadcast(channel: str, data: Dict[str, Any]) -> int:
    """Broadcast data to all WebSocket clients on a channel.

    Channels: 'git', 'daemon', 'crew', 'cost', 'streak', 'system'
    """
    hub = get_hub()
    return await hub._broadcast_async(channel, data)


def broadcast_sync(channel: str, data: Dict[str, Any]) -> None:
    """Broadcast from sync code (thread-safe)."""
    hub = get_hub()
    hub.broadcast_sync(channel, data)


# ============================================================================
# Auto-Broadcast Middleware
# ============================================================================

def wrap_panel_route_with_broadcast(handler, channel: str):
    """Wrap an aiohttp handler to auto-broadcast its response via WebSocket.

    After the normal JSON response is sent, the same data is pushed
    to all WebSocket clients on the specified channel.
    """
    async def wrapper(request):
        response = await handler(request)

        # If the handler returned a JSON response, broadcast it.
        if hasattr(response, 'text') and response.content_type == 'application/json':
            try:
                data = json.loads(response.text)
                if 'error' not in data:
                    await broadcast(channel, data)
            except Exception:
                pass

        return response

    return wrapper


# ============================================================================
# Periodic Broadcaster
# ============================================================================

class PeriodicBroadcaster:
    """Periodically fetch and broadcast panel data.

    Replaces client-side polling with server-push.
    Default: every 10 seconds for git/daemon/cost.
    """

    def __init__(self, hub: WebSocketHub, interval: float = 10.0):
        self._hub = hub
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the periodic broadcast loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Periodic broadcaster started (interval=%.1fs)", self._interval)

    async def stop(self):
        """Stop the periodic broadcast."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        """Main broadcast loop."""
        while self._running:
            try:
                if self._hub.client_count > 0:
                    await self._broadcast_all()
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Periodic broadcast error: %s", e)
                await asyncio.sleep(self._interval)

    async def _broadcast_all(self):
        """Fetch and broadcast all panel data."""
        import os

        # Daemon health.
        try:
            from gateway.daemon_runner import DaemonRunner
            daemon = DaemonRunner()
            health = daemon.get_health()
            await broadcast("daemon", health)
        except Exception:
            pass

        # Cost.
        try:
            from gateway.graph_engine import get_budget
            budget = get_budget()
            await broadcast("cost", {
                "total_today_usd": budget.daily_spend,
                "budget_remaining_usd": budget.remaining_budget,
            })
        except Exception:
            pass

        # Streak.
        try:
            from gateway.streaks import get_streak_api_data
            data = get_streak_api_data()
            await broadcast("streak", data)
        except Exception:
            pass

        # System stats.
        try:
            import psutil
            await broadcast("system", {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "clients": self._hub.client_count,
            })
        except Exception:
            await broadcast("system", {"clients": self._hub.client_count})
