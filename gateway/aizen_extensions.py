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

    # Codebase graph routes
    _register_graph_routes(app)

    # Panel routes (git, crew, daemon, cost dashboard)
    try:
        from gateway.panel_routes import register_panel_routes
        register_panel_routes(app)
    except ImportError as e:
        logger.debug("Panel routes not registered: %s", e)

    logger.info("All Aizen extension routes registered")


# ============================================================================
# Codebase Knowledge Graph Routes
# ============================================================================

def _register_graph_routes(app: Any) -> None:
    """Register codebase knowledge graph API routes."""
    try:
        from aiohttp import web
        from gateway.codebase_graph import get_graph_manager
    except ImportError as e:
        logger.debug("Graph routes not registered: %s", e)
        return

    async def handle_index_workspace(request):
        """POST /api/graph/index — Index a workspace into a knowledge graph."""
        data = await request.json()
        workspace_path = data.get("workspace_path", "")
        force = data.get("force", False)

        if not workspace_path:
            return web.json_response({"error": "workspace_path required"}, status=400)

        manager = get_graph_manager()
        try:
            graph = manager.index_workspace(workspace_path, force=force)
            return web.json_response({
                "status": "indexed",
                "workspace": workspace_path,
                "nodes": graph.node_count,
                "edges": graph.edge_count,
                "files": graph.file_count,
                "languages": graph.language_stats,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_query_graph(request):
        """POST /api/graph/query — Query the knowledge graph."""
        data = await request.json()
        workspace_path = data.get("workspace_path", "")
        question = data.get("question", "")

        if not workspace_path or not question:
            return web.json_response(
                {"error": "workspace_path and question required"}, status=400
            )

        manager = get_graph_manager()
        result = manager.query(workspace_path, question)
        return web.json_response({"result": result})

    async def handle_graph_context(request):
        """POST /api/graph/context — Get graph context for a file."""
        data = await request.json()
        workspace_path = data.get("workspace_path", "")
        file_path = data.get("file_path", "")

        manager = get_graph_manager()
        context = manager.get_context_for_file(workspace_path, file_path)
        return web.json_response({"context": context})

    async def handle_graph_search(request):
        """GET /api/graph/search?workspace=...&pattern=...&kind=..."""
        workspace_path = request.query.get("workspace", "")
        pattern = request.query.get("pattern", "")
        kind = request.query.get("kind")

        manager = get_graph_manager()
        graph = manager.get_graph(workspace_path)
        if not graph:
            return web.json_response({"error": "Workspace not indexed"}, status=404)

        nodes = graph.search_nodes(pattern, kind=kind)
        return web.json_response({
            "results": [n.to_dict() for n in nodes[:50]],
            "total": len(nodes),
        })

    async def handle_graph_neighbors(request):
        """GET /api/graph/neighbors?workspace=...&node_id=..."""
        workspace_path = request.query.get("workspace", "")
        node_id = request.query.get("node_id", "")

        manager = get_graph_manager()
        graph = manager.get_graph(workspace_path)
        if not graph:
            return web.json_response({"error": "Workspace not indexed"}, status=404)

        neighbors = graph.get_neighbors(node_id)
        return web.json_response({
            "neighbors": [
                {"node": n.to_dict(), "edge_kind": e.kind}
                for n, e in neighbors[:30]
            ],
        })

    async def handle_graph_map(request):
        """GET /api/graph/map?workspace=... — Get compact repo map for LLM."""
        workspace_path = request.query.get("workspace", "")
        max_tokens = int(request.query.get("max_tokens", "2000"))

        manager = get_graph_manager()
        graph = manager.get_graph(workspace_path)
        if not graph:
            return web.json_response({"error": "Workspace not indexed"}, status=404)

        repo_map = graph.to_context_string(max_tokens=max_tokens)
        return web.json_response({"map": repo_map})

    app.router.add_post("/api/graph/index", handle_index_workspace)
    app.router.add_post("/api/graph/query", handle_query_graph)
    app.router.add_post("/api/graph/context", handle_graph_context)
    app.router.add_get("/api/graph/search", handle_graph_search)
    app.router.add_get("/api/graph/neighbors", handle_graph_neighbors)
    app.router.add_get("/api/graph/map", handle_graph_map)
    logger.info("Codebase graph routes registered")


# ============================================================================
# Route table export (for api_server.py _http_route_table)
# ============================================================================

def get_extension_routes(adapter: Any) -> list:
    """Return (method, path, handler) tuples for the API server route table.

    Called by api_server.py._http_route_table() to merge extension
    routes without requiring direct aiohttp app access.
    """
    # For now, extension routes are registered via register_aizen_extensions.
    # This function is a hook for future route-table-style registration.
    return []
