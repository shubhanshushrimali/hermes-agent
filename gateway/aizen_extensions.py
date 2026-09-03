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
    """Register MCP Apps routes against MCPAppRegistry.build / describe_apps."""
    try:
        from aiohttp import web
        from gateway.mcp_apps import MCPAppRegistry
    except ImportError as e:
        logger.debug("MCP Apps routes not registered: %s", e)
        return

    async def handle_list_apps(request: web.Request) -> web.Response:
        return web.json_response({
            "ok": True,
            "apps": MCPAppRegistry.describe_apps(),
        })

    async def handle_run_app(request: web.Request) -> web.Response:
        app_id = request.match_info["app_id"]
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        built = MCPAppRegistry.build(app_id, **data)
        if built is None:
            return web.json_response(
                {"ok": False, "error": f"App '{app_id}' not found"}, status=404
            )
        return web.json_response({"ok": True, "result": built.to_message()})

    app.router.add_get("/api/mcp/apps", handle_list_apps)
    app.router.add_post("/api/mcp/apps/{app_id}/run", handle_run_app)
    logger.info("MCP Apps routes registered")


# ============================================================================
# Recipes Routes
# ============================================================================

def _register_recipes_routes(app: Any) -> None:
    """Register Recipes routes via RecipeLibrary (not RecipeRunner())."""
    try:
        from aiohttp import web
        from gateway.recipes import RecipeLibrary, default_recipes_dir, execute_recipe
        from gateway.session_prompt import run_session_prompt, session_turn_kwargs
    except ImportError as e:
        logger.debug("Recipes routes not registered: %s", e)
        return

    library = RecipeLibrary(default_recipes_dir())

    def _adapter():
        return app.get("api_server_adapter")

    async def handle_list_recipes(request: web.Request) -> web.Response:
        return web.json_response({
            "ok": True,
            "recipes": library.list_recipes(),
        })

    async def handle_run_recipe(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        recipe = library.load(name)
        if recipe is None:
            return web.json_response(
                {"ok": False, "error": f"Recipe '{name}' not found"}, status=404
            )
        workspace = str(data.get("workspace") or data.get("cwd") or "")
        kwargs = session_turn_kwargs(data)
        adapter = _adapter()

        async def _run_agent(prompt: str) -> str:
            return await run_session_prompt(
                prompt,
                timeout=300.0,
                session_id=kwargs["session_id"] or f"recipe_{name}",
                adapter=adapter,
                cwd=workspace or kwargs["cwd"],
                model=kwargs["model"],
                persist=bool(kwargs["session_id"]),
            )

        try:
            result = await execute_recipe(
                recipe,
                context={
                    k: v
                    for k, v in data.items()
                    if k not in {"workspace", "cwd", "sessionId", "session_id", "model"}
                },
                run_agent=_run_agent,
                workspace=workspace,
            )
            return web.json_response({"ok": True, "result": result})
        except FileNotFoundError:
            return web.json_response(
                {"ok": False, "error": f"Recipe '{name}' not found"}, status=404
            )
        except Exception as e:
            logger.exception("Recipe %s failed", name)
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get("/api/recipes", handle_list_recipes)
    app.router.add_post("/api/recipes/{name}/run", handle_run_recipe)
    logger.info("Recipes routes registered")


# ============================================================================
# Public wiring entry point
# ============================================================================

def _safe_register(name: str, fn) -> None:
    """One extension must not abort the rest of the overlay."""
    try:
        fn()
    except Exception:
        logger.exception("Extension %s failed to register; continuing", name)


def register_aizen_extensions(app: Any, get_agent_fn: Any = None) -> None:
    """
    Register all Aizen extension routes on an aiohttp application.

    Call this after the core API server routes are registered.
    ``get_agent_fn`` is ignored — IDE and recipes use the session runtime
    via ``app['api_server_adapter']`` / ``run_session_prompt``.
    """
    _safe_register("mobile_auth", lambda: _register_mobile_auth_routes(app))
    _safe_register("mcp_apps", lambda: _register_mcp_apps_routes(app))
    _safe_register("recipes", lambda: _register_recipes_routes(app))

    def _register_ide() -> None:
        from gateway.ide_features import register_ide_routes
        register_ide_routes(app)

    _safe_register("ide", _register_ide)
    _safe_register("graph", lambda: _register_graph_routes(app))

    def _register_panels() -> None:
        from gateway.panel_routes import register_panel_routes
        register_panel_routes(app)

    _safe_register("panels", _register_panels)

    # Log integration status at startup.
    try:
        from gateway.env_config import log_startup_status
        log_startup_status()
    except Exception:
        pass

    # Run startup performance optimizations (SQLite tuning, cache eviction).
    try:
        from gateway.perf import run_startup_optimizations
        run_startup_optimizations()
    except Exception:
        pass

    # Print the Zanpakutō banner.
    try:
        from gateway.banner import print_banner
        print_banner(compact=True)
    except Exception:
        pass

    # Record daily streak activity.
    try:
        from gateway.streaks import StreakTracker
        tracker = StreakTracker()
        info = tracker.record_activity()
        logger.info("Streak: %s", info.get("streak_display", ""))
    except Exception:
        pass

    # Discover and load plugins.
    try:
        from gateway.plugin_system import get_plugin_registry
        registry = get_plugin_registry()
        plugins = registry.get_plugins()
        if plugins:
            logger.info("Loaded %d plugins with %d tools",
                        len(plugins),
                        len(registry.get_tools()))
    except Exception:
        pass

    # WebSocket hub — real-time panel updates.
    try:
        from gateway.ws_hub import get_hub, PeriodicBroadcaster
        hub = get_hub()
        hub.register_routes(app)

        # Start periodic broadcaster after the event loop is running.
        async def _start_broadcaster(app_):
            broadcaster = PeriodicBroadcaster(hub, interval=10.0)
            app_["_ws_broadcaster"] = broadcaster
            await broadcaster.start()

        async def _stop_broadcaster(app_):
            broadcaster = app_.get("_ws_broadcaster")
            if broadcaster:
                await broadcaster.stop()

        app.on_startup.append(_start_broadcaster)
        app.on_cleanup.append(_stop_broadcaster)
    except Exception:
        pass

    # Initialize Langfuse tracing.
    try:
        from gateway.langfuse_integration import init_langfuse
        init_langfuse()
    except Exception:
        pass

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
                "backend": getattr(graph, "backend", "regex"),
                "warnings": list(getattr(graph, "warnings", []) or []),
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
