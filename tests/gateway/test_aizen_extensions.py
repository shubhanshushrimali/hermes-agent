"""Overlay wiring: recipes, MCP apps, IDE session turns, registration isolation."""

from __future__ import annotations

import inspect

import pytest
from aiohttp import web

from gateway.aizen_extensions import (
    _register_recipes_routes,
    register_aizen_extensions,
)
from gateway.ide_features import register_ide_routes
from gateway.mcp_apps import MCPAppRegistry
from gateway.recipes import (
    Recipe,
    RecipeLibrary,
    RecipeRunner,
    RecipeStep,
    default_recipes_dir,
    execute_recipe,
)
from gateway.session_prompt import session_turn_kwargs, strip_code_fences


def _route_paths(app: web.Application) -> set[str]:
    paths: set[str] = set()
    for resource in app.router.resources():
        info = resource.get_info()
        if "path" in info:
            paths.add(info["path"])
        elif "formatter" in info:
            paths.add(info["formatter"])
    return paths


class TestRecipeLibrary:
    def test_bundled_yaml_recipes_are_listed(self):
        names = {item["name"] for item in RecipeLibrary(default_recipes_dir()).list_recipes()}
        assert "code-review" in names
        assert "deploy-check" in names

    def test_recipe_runner_requires_a_recipe(self):
        with pytest.raises(TypeError):
            RecipeRunner()  # type: ignore[call-arg]

    def test_recipes_route_does_not_construct_runner_at_register(self):
        source = inspect.getsource(_register_recipes_routes)
        assert "RecipeLibrary" in source
        assert "execute_recipe" in source
        assert "import RecipeRunner" not in source


class TestMcpApps:
    def test_list_apps_returns_names_not_payloads(self):
        names = MCPAppRegistry.list_apps()
        assert isinstance(names, list)
        assert all(isinstance(name, str) for name in names)
        assert "json-viewer" in names

    def test_describe_apps_uses_build_and_to_message(self):
        apps = MCPAppRegistry.describe_apps()
        assert isinstance(apps, list)
        viewer = next(item for item in apps if item.get("id") == "json-viewer")
        assert viewer["type"] == "mcp_app"
        assert viewer["name"]

    def test_build_unknown_returns_none(self):
        assert MCPAppRegistry.build("does-not-exist") is None

    def test_run_path_is_build_not_run_app(self):
        built = MCPAppRegistry.build("json-viewer", data={"a": 1})
        assert built is not None
        payload = built.to_message()
        assert payload["type"] == "mcp_app"
        assert not hasattr(MCPAppRegistry, "run_app")


class TestSessionPrompt:
    def test_strip_code_fences(self):
        assert strip_code_fences("```python\nx = 1\n```") == "x = 1"
        assert strip_code_fences("plain") == "plain"

    def test_session_turn_kwargs_reads_focused_session_fields(self):
        assert session_turn_kwargs(
            {"sessionId": "abc", "cwd": "C:/proj", "model": "gpt"}
        ) == {"session_id": "abc", "cwd": "C:/proj", "model": "gpt"}
        assert session_turn_kwargs({"session_id": "x", "workspace": "/w"})[
            "session_id"
        ] == "x"

    def test_ide_routes_use_session_runtime_not_asyncio_coroutine(self):
        source = inspect.getsource(register_ide_routes)
        assert "run_session_prompt" in source
        assert "run_ghost_completion_async" in source
        assert "asyncio.coroutine" not in source
        assert "gateway_runner.agent" not in source

    def test_overlay_ws_is_not_desktop_jsonrpc_path(self):
        from gateway.ws_hub import OVERLAY_WS_PATH

        assert OVERLAY_WS_PATH == "/api/overlay/ws"
        assert OVERLAY_WS_PATH != "/api/ws"

    def test_dashboard_overlay_mounts_recipes_mcp_graph(self):
        from hermes_cli.web_routers.overlay import router

        paths = {getattr(route, "path", "") for route in router.routes}
        assert "/api/recipes" in paths
        assert "/api/recipes/{name}/run" in paths
        assert "/api/mcp/apps" in paths
        assert "/api/graph/index" in paths

    def test_dashboard_ide_mounts_verify_hint(self):
        from hermes_cli.web_routers.ide import router

        paths = {getattr(route, "path", "") for route in router.routes}
        assert "/api/ide/ghost-completion" in paths
        assert "/api/ide/verify-hint" in paths


class TestLiveSessionBusy:
    def test_busy_live_session_raises(self, monkeypatch):
        from gateway import session_prompt as sp

        monkeypatch.setattr(
            sp,
            "find_live_session",
            lambda _sid: {"running": True, "agent": object(), "cwd": "/x"},
        )
        with pytest.raises(RuntimeError, match="busy"):
            sp._dashboard_run(
                "hi",
                session_id="sess-1",
                cwd=None,
                model=None,
                persist=True,
            )


@pytest.mark.asyncio
async def test_execute_recipe_mcp_step_builds_app():
    recipe = Recipe(
        name="viewer",
        steps=[RecipeStep(action="mcp_app", app="json-viewer", data={"data": {"x": 1}})],
    )
    out = await execute_recipe(recipe)
    assert out["steps"][0]["status"] == "ok"
    assert out["steps"][0]["app_payload"]["type"] == "mcp_app"


class TestExtensionIsolation:
    def test_recipe_failure_still_registers_ide_and_graph(self, monkeypatch):
        def boom(_app):
            raise RuntimeError("recipes exploded")

        monkeypatch.setattr(
            "gateway.aizen_extensions._register_recipes_routes", boom
        )
        app = web.Application()
        register_aizen_extensions(app)
        paths = _route_paths(app)
        assert "/api/ide/inline-edit" in paths
        assert "/api/ide/ghost-completion" in paths
        assert "/api/graph/index" in paths
        assert "/api/mcp/apps" in paths
        recipe_paths = [p for p in paths if p.startswith("/api/recipes")]
        assert recipe_paths == []
