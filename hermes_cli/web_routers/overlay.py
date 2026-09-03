"""Recipes, MCP Apps, and codebase graph on the dashboard (desktop origin)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from gateway.session_prompt import run_session_prompt, session_turn_kwargs

router = APIRouter()


class GraphIndexBody(BaseModel):
    workspace_path: str = ""
    force: bool = False


class GraphQueryBody(BaseModel):
    workspace_path: str = ""
    question: str = ""


class GraphContextBody(BaseModel):
    workspace_path: str = ""
    file_path: str = ""


@router.get("/api/recipes")
async def list_recipes() -> Dict[str, Any]:
    from gateway.recipes import RecipeLibrary, default_recipes_dir

    library = RecipeLibrary(default_recipes_dir())
    return {"ok": True, "recipes": library.list_recipes()}


@router.post("/api/recipes/{name}/run")
async def run_recipe(name: str, data: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    from gateway.recipes import RecipeLibrary, default_recipes_dir, execute_recipe

    payload = data if isinstance(data, dict) else {}
    kwargs = session_turn_kwargs(payload)
    workspace = str(payload.get("cwd") or payload.get("workspace") or kwargs["cwd"] or "")
    recipe = RecipeLibrary(default_recipes_dir()).load(name)
    if recipe is None:
        raise HTTPException(status_code=404, detail=f"Recipe '{name}' not found")

    async def _run_agent(prompt: str) -> str:
        return await run_session_prompt(
            prompt,
            timeout=300.0,
            session_id=kwargs["session_id"] or f"recipe_{name}",
            cwd=workspace or None,
            model=kwargs["model"],
            persist=bool(kwargs["session_id"]),
        )

    try:
        result = await execute_recipe(
            recipe,
            context={
                k: v
                for k, v in payload.items()
                if k not in {"workspace", "cwd", "sessionId", "session_id", "model"}
            },
            run_agent=_run_agent,
            workspace=workspace,
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/mcp/apps")
async def list_mcp_apps() -> Dict[str, Any]:
    from gateway.mcp_apps import MCPAppRegistry

    return {"ok": True, "apps": MCPAppRegistry.describe_apps()}


@router.post("/api/mcp/apps/{app_id}/run")
async def run_mcp_app(app_id: str, data: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    from gateway.mcp_apps import MCPAppRegistry

    payload = data if isinstance(data, dict) else {}
    built = MCPAppRegistry.build(app_id, **payload)
    if built is None:
        raise HTTPException(status_code=404, detail=f"App '{app_id}' not found")
    return {"ok": True, "result": built.to_message()}


@router.post("/api/graph/index")
async def graph_index(body: GraphIndexBody) -> Dict[str, Any]:
    from gateway.codebase_graph import get_graph_manager

    if not body.workspace_path:
        raise HTTPException(status_code=400, detail="workspace_path required")
    manager = get_graph_manager()
    try:
        graph = manager.index_workspace(body.workspace_path, force=body.force)
        return {
            "status": "indexed",
            "workspace": body.workspace_path,
            "nodes": graph.node_count,
            "edges": graph.edge_count,
            "files": graph.file_count,
            "languages": graph.language_stats,
            "backend": getattr(graph, "backend", "regex"),
            "warnings": list(getattr(graph, "warnings", []) or []),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/graph/query")
async def graph_query(body: GraphQueryBody) -> Dict[str, Any]:
    from gateway.codebase_graph import get_graph_manager

    if not body.workspace_path or not body.question:
        raise HTTPException(status_code=400, detail="workspace_path and question required")
    manager = get_graph_manager()
    return {"result": manager.query(body.workspace_path, body.question)}


@router.post("/api/graph/context")
async def graph_context(body: GraphContextBody) -> Dict[str, Any]:
    from gateway.codebase_graph import get_graph_manager

    manager = get_graph_manager()
    return {"context": manager.get_context_for_file(body.workspace_path, body.file_path)}


@router.get("/api/graph/search")
async def graph_search(
    workspace: str = "",
    pattern: str = "",
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    from gateway.codebase_graph import get_graph_manager

    manager = get_graph_manager()
    graph = manager.get_graph(workspace)
    if not graph:
        raise HTTPException(status_code=404, detail="Workspace not indexed")
    nodes = graph.search_nodes(pattern, kind=kind)
    return {"results": [n.to_dict() for n in nodes[:50]], "total": len(nodes)}


@router.get("/api/graph/neighbors")
async def graph_neighbors(workspace: str = "", node_id: str = "") -> Dict[str, Any]:
    from gateway.codebase_graph import get_graph_manager

    manager = get_graph_manager()
    graph = manager.get_graph(workspace)
    if not graph:
        raise HTTPException(status_code=404, detail="Workspace not indexed")
    neighbors = graph.get_neighbors(node_id)
    return {
        "neighbors": [{"node": n.to_dict(), "edge_kind": e.kind} for n, e in neighbors[:30]],
    }


@router.get("/api/graph/map")
async def graph_map(workspace: str = "", max_tokens: int = 2000) -> Dict[str, Any]:
    from gateway.codebase_graph import get_graph_manager

    manager = get_graph_manager()
    graph = manager.get_graph(workspace)
    if not graph:
        raise HTTPException(status_code=404, detail="Workspace not indexed")
    return {
        "map": graph.to_context_string(max_tokens=max_tokens),
        "warnings": list(getattr(graph, "warnings", []) or []),
    }
