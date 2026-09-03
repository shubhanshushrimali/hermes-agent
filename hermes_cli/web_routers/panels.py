"""Crew / daemon / cost panel routes on the dashboard (same backends as gateway)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CrewRunBody(BaseModel):
    crew: str = ""
    task: str = ""
    context: str = ""
    workspace: str = ""


class CostBudgetBody(BaseModel):
    max_daily_usd: float = 10.0


@router.get("/api/crew/status")
async def crew_status() -> Dict[str, Any]:
    try:
        from gateway.crew_engine import get_crew_engine
        return get_crew_engine().get_crew_status()
    except ImportError:
        return {"crewai_available": False, "available_crews": {}, "active_agents": []}


@router.post("/api/crew/run")
async def crew_run(body: CrewRunBody) -> Dict[str, Any]:
    try:
        from gateway.crew_engine import get_crew_engine
        return get_crew_engine().run_crew(
            crew_name=body.crew,
            task_description=body.task,
            context=body.context,
            workspace_path=body.workspace,
        )
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="CrewAI not installed") from exc


@router.get("/api/daemon/health")
async def daemon_health() -> Dict[str, Any]:
    try:
        from gateway.daemon_runner import DaemonRunner
        return DaemonRunner().get_health()
    except ImportError:
        return {"status": "not_installed"}


@router.get("/api/daemon/jobs")
async def daemon_jobs() -> Dict[str, Any]:
    try:
        from gateway.daemon_runner import JobQueue
        jobs = JobQueue().list_jobs()
        return {
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "status": j.status,
                    "prompt": (j.prompt or "")[:100],
                    "schedule": j.schedule,
                    "priority": j.priority,
                    "created_at": j.created_at,
                }
                for j in jobs
            ]
        }
    except ImportError:
        return {"jobs": []}


@router.get("/api/cost/dashboard")
async def cost_dashboard() -> Dict[str, Any]:
    try:
        from gateway.graph_engine import get_budget
        budget = get_budget()
        return {
            "total_today_usd": budget.daily_spend,
            "budget_remaining_usd": budget.remaining_budget,
            "max_daily_usd": budget.max_daily_usd,
            "by_model": budget.by_model,
            "by_intent": budget.by_intent,
            "last_7_days": budget.last_7_days,
        }
    except Exception:
        return {
            "total_today_usd": 0,
            "budget_remaining_usd": 10.0,
            "by_model": {},
            "by_intent": {},
            "last_7_days": [],
        }


@router.post("/api/cost/budget")
async def cost_budget(body: CostBudgetBody) -> Dict[str, Any]:
    try:
        from gateway.graph_engine import get_budget
        budget = get_budget()
        budget.max_daily_usd = body.max_daily_usd
        return {"ok": True, "max_daily_usd": budget.max_daily_usd}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
