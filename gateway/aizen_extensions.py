"""
Aizen Extensions Wiring — registers mobile auth, MCP apps, recipes,
and IDE features onto the gateway API server.

Import this module from the gateway bootstrap to add:
  - POST /api/mobile/auth/pin         (set/verify PIN)
  - POST /api/mobile/auth/verify      (verify token)
  - POST /api/mobile/auth/qr          (generate QR pairing data)
  - POST /api/ide/inline-edit         (Cmd+K code edit)
  - POST /api/ide/ghost-completion    (ghost text)
  - GET  /api/mcp/apps                (list available MCP apps)
  - POST /api/mcp/apps/{app_id}/run   (execute an MCP app)
  - GET  /api/recipes                 (list available recipes)
  - POST /api/recipes/{name}/run      (execute a recipe)

Part of Phase 2, 4, 7: wiring orphaned gateway modules.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger("hermes.aizen_extensions")


# ============================================================================
# Mobile Auth Routes
# ============================================================================

def _register_mobile_auth_routes(app: Any) -> None:
    """Register mobile PIN authentication routes."""
    try:
        from aiohttp import web
        from gateway.mobile_auth import MobileAuth
    except ImportError as e:
        logger.debug("Mobile auth routes not registered: %s", e)
        return

    # Singleton — one auth instance per gateway.
    _auth: Optional[MobileAuth] = None

    def _get_auth() -> MobileAuth:
        nonlocal _auth
        if _auth is None:
            try:
                from hermes_cli.config import get_hermes_home
                _auth = MobileAuth(hermes_home=get_hermes_home())
            except Exception:
                from pathlib import Path
                _auth = MobileAuth(hermes_home=Path.home() / ".hermes")
        return _auth

    async def handle_set_pin(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            pin = data.get("pin", "")
            scope = data.get("scope", "operator")
            auth = _get_auth()
            auth.set_pin(pin, scope=scope)
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    async def handle_verify_pin(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            pin = data.get("pin", "")
            client_ip = request.remote or "unknown"
            auth = _get_auth()
            token = auth.verify_pin(pin, client_ip=client_ip)
            if token:
                return web.json_response({"ok": True, "token": token})
            return web.json_response(
                {"ok": False, "error": "Invalid PIN"}, status=401
            )
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=429)

    async def handle_verify_token(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            token = data.get("token", "")
            auth = _get_auth()
            claims = auth.verify_token(token)
            if claims:
                return web.json_response({"ok": True, "claims": claims})
            return web.json_response(
                {"ok": False, "error": "Invalid token"}, status=401
            )
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=401)

    async def handle_qr_pairing(request: web.Request) -> web.Response:
        try:
            auth = _get_auth()
            qr_data = auth.generate_pairing_qr()
            return web.json_response({"ok": True, "qr": qr_data})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_post("/api/mobile/auth/pin", handle_set_pin)
    app.router.add_post("/api/mobile/auth/verify", handle_verify_pin)
    app.router.add_post("/api/mobile/auth/token", handle_verify_token)
    app.router.add_post("/api/mobile/auth/qr", handle_qr_pairing)
    logger.info("Mobile auth routes registered")


# ============================================================================
# MCP Apps Routes
# ============================================================================

def _register_mcp_apps_routes(app: Any) -> None:
    """Register MCP Apps routes."""
    try:
        from aiohttp import web
        from gateway.mcp_apps import MCPApp, MCPAppRegistry
    except ImportError as e:
        logger.debug("MCP Apps routes not registered: %s", e)
        return

    _registry = MCPAppRegistry()

    async def handle_list_apps(request: web.Request) -> web.Response:
        apps = _registry.list_apps()
        return web.json_response({
            "ok": True,
            "apps": [a.to_message() for a in apps],
        })

    async def handle_run_app(request: web.Request) -> web.Response:
        app_id = request.match_info["app_id"]
        try:
            data = await request.json()
        except Exception:
            data = {}
        try:
            result = _registry.run_app(app_id, data)
            return web.json_response({"ok": True, "result": result})
        except KeyError:
            return web.json_response(
                {"ok": False, "error": f"App '{app_id}' not found"}, status=404
            )
        except Exception as e:
            return web.json_response(
                {"ok": False, "error": str(e)}, status=500
            )

    app.router.add_get("/api/mcp/apps", handle_list_apps)
    app.router.add_post("/api/mcp/apps/{app_id}/run", handle_run_app)
    logger.info("MCP Apps routes registered")


# ============================================================================
# Recipes Routes
# ============================================================================

def _register_recipes_routes(app: Any, get_agent_fn: Any = None) -> None:
    """Register Recipes routes."""
    try:
        from aiohttp import web
        from gateway.recipes import RecipeRunner
    except ImportError as e:
        logger.debug("Recipes routes not registered: %s", e)
        return

    _runner = RecipeRunner()

    async def handle_list_recipes(request: web.Request) -> web.Response:
        recipes = _runner.list_recipes()
        return web.json_response({
            "ok": True,
            "recipes": [
                {"name": r.name, "description": r.description}
                for r in recipes
            ],
        })

    async def handle_run_recipe(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        try:
            data = await request.json()
        except Exception:
            data = {}
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _runner.run(name, context=data, agent=get_agent_fn() if get_agent_fn else None)
            )
            return web.json_response({"ok": True, "result": result})
        except FileNotFoundError:
            return web.json_response(
                {"ok": False, "error": f"Recipe '{name}' not found"}, status=404
            )
        except Exception as e:
            return web.json_response(
                {"ok": False, "error": str(e)}, status=500
            )

    app.router.add_get("/api/recipes", handle_list_recipes)
    app.router.add_post("/api/recipes/{name}/run", handle_run_recipe)
    logger.info("Recipes routes registered")


# ============================================================================
# Public wiring entry point
# ============================================================================

def register_aizen_extensions(app: Any, get_agent_fn: Any = None) -> None:
    """
    Register all Aizen extension routes on an aiohttp application.

    Call this after the core API server routes are registered.

    Parameters
    ----------
    app : aiohttp.web.Application
        The running aiohttp application.
    get_agent_fn : callable, optional
        Returns the current agent instance (for IDE features and recipes).
    """
    _register_mobile_auth_routes(app)
    _register_mcp_apps_routes(app)
    _register_recipes_routes(app, get_agent_fn)

    # IDE features (inline edit, ghost completion)
    try:
        from gateway.ide_features import register_ide_routes
        register_ide_routes(app, get_agent_fn)
    except ImportError as e:
        logger.debug("IDE feature routes not registered: %s", e)

    logger.info("All Aizen extension routes registered")
