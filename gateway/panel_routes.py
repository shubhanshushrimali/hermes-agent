"""
Git + Daemon + Crew + Cost API Routes.

Backend handlers for the desktop UI panels.
Registered via aizen_extensions.py.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger("hermes.panel_routes")


def register_panel_routes(app: Any) -> None:
    """Register all panel API routes."""
    try:
        from aiohttp import web
    except ImportError:
        return

    # ================================================================
    # Git Routes
    # ================================================================

    async def handle_git_status(request):
        workspace = request.query.get("workspace", "")
        if not workspace or not os.path.isdir(workspace):
            return web.json_response({"error": "Invalid workspace"}, status=400)

        try:
            # Branch info.
            branch = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=workspace, timeout=5,
            ).stdout.strip()

            # Ahead/behind.
            ab = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"{branch}...origin/{branch}"],
                capture_output=True, text=True, cwd=workspace, timeout=5,
            ).stdout.strip().split()
            ahead = int(ab[0]) if len(ab) >= 2 else 0
            behind = int(ab[1]) if len(ab) >= 2 else 0

            # Status.
            status_out = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=workspace, timeout=5,
            ).stdout.strip()

            staged, unstaged, untracked = [], [], []
            for line in status_out.split("\n"):
                if not line:
                    continue
                idx, wt = line[0], line[1]
                path = line[3:]
                status_map = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed"}
                if idx != " " and idx != "?":
                    staged.append({"path": path, "status": status_map.get(idx, "modified")})
                elif wt != " " and wt != "?":
                    unstaged.append({"path": path, "status": status_map.get(wt, "modified")})
                elif idx == "?":
                    untracked.append({"path": path, "status": "added"})

            # Last commit.
            last = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%H|%h|%s|%an|%aI"],
                capture_output=True, text=True, cwd=workspace, timeout=5,
            ).stdout.strip().split("|")

            last_commit = None
            if len(last) >= 5:
                last_commit = {
                    "hash": last[0], "shortHash": last[1], "message": last[2],
                    "author": last[3], "date": last[4],
                    "isAgentCommit": "hermes" in last[3].lower() or "aizen" in last[2].lower(),
                }

            return web.json_response({
                "branch": branch, "ahead": ahead, "behind": behind,
                "staged": staged, "unstaged": unstaged, "untracked": untracked,
                "lastCommit": last_commit,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_git_log(request):
        workspace = request.query.get("workspace", "")
        limit = int(request.query.get("limit", "20"))
        try:
            out = subprocess.run(
                ["git", "log", f"-{limit}", "--pretty=format:%H|%h|%s|%an|%aI"],
                capture_output=True, text=True, cwd=workspace, timeout=10,
            ).stdout.strip()

            commits = []
            for line in out.split("\n"):
                if not line:
                    continue
                parts = line.split("|", 4)
                if len(parts) >= 5:
                    commits.append({
                        "hash": parts[0], "shortHash": parts[1], "message": parts[2],
                        "author": parts[3], "date": parts[4],
                        "isAgentCommit": "hermes" in parts[3].lower(),
                    })
            return web.json_response({"commits": commits})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_git_stage(request):
        data = await request.json()
        workspace = data.get("workspace", "")
        files = data.get("files", [])
        subprocess.run(["git", "add"] + files, cwd=workspace, timeout=10)
        return web.json_response({"ok": True})

    async def handle_git_unstage(request):
        data = await request.json()
        workspace = data.get("workspace", "")
        files = data.get("files", [])
        subprocess.run(["git", "restore", "--staged"] + files, cwd=workspace, timeout=10)
        return web.json_response({"ok": True})

    async def handle_git_commit(request):
        data = await request.json()
        workspace = data.get("workspace", "")
        message = data.get("message", "")
        subprocess.run(["git", "commit", "-m", message], cwd=workspace, timeout=30)
        return web.json_response({"ok": True})

    async def handle_git_push(request):
        data = await request.json()
        workspace = data.get("workspace", "")
        subprocess.run(["git", "push"], cwd=workspace, timeout=30)
        return web.json_response({"ok": True})

    async def handle_git_pull(request):
        data = await request.json()
        workspace = data.get("workspace", "")
        subprocess.run(["git", "pull"], cwd=workspace, timeout=30)
        return web.json_response({"ok": True})

    async def handle_git_revert(request):
        data = await request.json()
        workspace = data.get("workspace", "")
        commit_hash = data.get("commit_hash", "")
        subprocess.run(["git", "revert", "--no-edit", commit_hash], cwd=workspace, timeout=30)
        return web.json_response({"ok": True})

    async def handle_git_diff(request):
        workspace = request.query.get("workspace", "")
        file_path = request.query.get("file", "")
        out = subprocess.run(
            ["git", "diff", file_path] if file_path else ["git", "diff"],
            capture_output=True, text=True, cwd=workspace, timeout=10,
        ).stdout
        return web.json_response({"diff": out})

    app.router.add_get("/api/git/status", handle_git_status)
    app.router.add_get("/api/git/log", handle_git_log)
    app.router.add_post("/api/git/stage", handle_git_stage)
    app.router.add_post("/api/git/unstage", handle_git_unstage)
    app.router.add_post("/api/git/commit", handle_git_commit)
    app.router.add_post("/api/git/push", handle_git_push)
    app.router.add_post("/api/git/pull", handle_git_pull)
    app.router.add_post("/api/git/revert", handle_git_revert)
    app.router.add_get("/api/git/diff", handle_git_diff)

    # ================================================================
    # Crew Routes
    # ================================================================

    async def handle_crew_status(request):
        try:
            from gateway.crew_engine import get_crew_engine
            engine = get_crew_engine()
            return web.json_response(engine.get_crew_status())
        except ImportError:
            return web.json_response({"crewai_available": False})

    async def handle_crew_run(request):
        data = await request.json()
        try:
            from gateway.crew_engine import get_crew_engine
            engine = get_crew_engine()
            result = engine.run_crew(
                crew_name=data.get("crew", ""),
                task_description=data.get("task", ""),
                context=data.get("context", ""),
                workspace_path=data.get("workspace", ""),
            )
            return web.json_response(result)
        except ImportError:
            return web.json_response({"error": "CrewAI not installed"}, status=500)

    async def handle_crew_agents(request):
        try:
            from gateway.crew_engine import get_crew_engine
            engine = get_crew_engine()
            return web.json_response({"agents": engine.list_agents()})
        except ImportError:
            return web.json_response({"agents": []})

    app.router.add_get("/api/crew/status", handle_crew_status)
    app.router.add_post("/api/crew/run", handle_crew_run)
    app.router.add_get("/api/crew/agents", handle_crew_agents)

    # ================================================================
    # Daemon Routes
    # ================================================================

    async def handle_daemon_health(request):
        try:
            from gateway.daemon_runner import DaemonRunner
            daemon = DaemonRunner()
            return web.json_response(daemon.get_health())
        except ImportError:
            return web.json_response({"status": "not_installed"})

    async def handle_daemon_jobs(request):
        try:
            from gateway.daemon_runner import JobQueue
            queue = JobQueue()
            jobs = queue.list_jobs()
            return web.json_response({
                "jobs": [
                    {
                        "id": j.id, "name": j.name, "status": j.status,
                        "prompt": j.prompt[:100], "schedule": j.schedule,
                        "priority": j.priority, "created_at": j.created_at,
                    }
                    for j in jobs
                ]
            })
        except ImportError:
            return web.json_response({"jobs": []})

    async def handle_daemon_add_job(request):
        data = await request.json()
        try:
            from gateway.daemon_runner import JobQueue, Job
            queue = JobQueue()
            job = Job(
                id="", name=data.get("name", ""), prompt=data.get("prompt", ""),
                schedule=data.get("schedule", ""), priority=data.get("priority", 5),
            )
            job_id = queue.enqueue(job)
            return web.json_response({"id": job_id})
        except ImportError:
            return web.json_response({"error": "Daemon not available"}, status=500)

    async def handle_daemon_template(request):
        data = await request.json()
        try:
            from gateway.daemon_runner import JobQueue, Job, DAEMON_TEMPLATES
            template_name = data.get("template", "")
            template = DAEMON_TEMPLATES.get(template_name)
            if not template:
                return web.json_response({"error": f"Unknown template: {template_name}"}, status=400)

            queue = JobQueue()
            job = Job(
                id="", name=template["name"], prompt=template["prompt"],
                schedule=template["schedule"], priority=template["priority"],
                workspace_path=data.get("workspace", ""),
            )
            job_id = queue.enqueue(job)
            return web.json_response({"id": job_id, "template": template_name})
        except ImportError:
            return web.json_response({"error": "Daemon not available"}, status=500)

    async def handle_daemon_pause_job(request):
        job_id = request.match_info["job_id"]
        try:
            from gateway.daemon_runner import JobQueue
            JobQueue().pause_job(job_id)
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_daemon_resume_job(request):
        job_id = request.match_info["job_id"]
        try:
            from gateway.daemon_runner import JobQueue
            JobQueue().resume_job(job_id)
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_daemon_delete_job(request):
        job_id = request.match_info["job_id"]
        try:
            from gateway.daemon_runner import JobQueue
            JobQueue().delete_job(job_id)
            return web.json_response({"ok": True})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get("/api/daemon/health", handle_daemon_health)
    app.router.add_get("/api/daemon/jobs", handle_daemon_jobs)
    app.router.add_post("/api/daemon/jobs", handle_daemon_add_job)
    app.router.add_post("/api/daemon/jobs/template", handle_daemon_template)
    app.router.add_post("/api/daemon/jobs/{job_id}/pause", handle_daemon_pause_job)
    app.router.add_post("/api/daemon/jobs/{job_id}/resume", handle_daemon_resume_job)
    app.router.add_delete("/api/daemon/jobs/{job_id}", handle_daemon_delete_job)

    # ================================================================
    # Cost Dashboard Routes
    # ================================================================

    async def handle_cost_dashboard(request):
        try:
            from gateway.graph_engine import get_budget
            budget = get_budget()
            return web.json_response({
                "total_today_usd": budget.daily_spend,
                "budget_remaining_usd": budget.remaining_budget,
                "max_daily_usd": budget.max_daily_usd,
                "by_model": budget.by_model,
                "by_intent": budget.by_intent,
                "last_7_days": budget.last_7_days,
            })
        except Exception:
            return web.json_response({
                "total_today_usd": 0, "budget_remaining_usd": 10.0,
                "by_model": {}, "by_intent": {}, "last_7_days": [],
            })

    async def handle_cost_budget(request):
        data = await request.json()
        try:
            from gateway.graph_engine import get_budget
            budget = get_budget()
            budget.max_daily_usd = data.get("max_daily_usd", 10.0)
            return web.json_response({"ok": True, "max_daily_usd": budget.max_daily_usd})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    app.router.add_get("/api/cost/dashboard", handle_cost_dashboard)
    app.router.add_post("/api/cost/budget", handle_cost_budget)

    # ================================================================
    # WebSocket Auto-Broadcast on Mutations
    # ================================================================

    try:
        from gateway.ws_hub import OVERLAY_WS_STATS_PATH, wrap_panel_route_with_broadcast, get_hub

        # After git mutations (stage, commit, push, pull, revert),
        # auto-broadcast the new git status to all WebSocket clients.
        async def _broadcast_git_after(request):
            """After a git mutation, broadcast the updated status."""
            workspace = ""
            if request.method == "POST":
                try:
                    data = await request.json()
                    workspace = data.get("workspace", "")
                except Exception:
                    pass
            if workspace:
                try:
                    # Re-fetch git status and broadcast.
                    import subprocess, os
                    branch = subprocess.run(
                        ["git", "branch", "--show-current"],
                        capture_output=True, text=True, cwd=workspace, timeout=5,
                    ).stdout.strip()
                    status_out = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True, text=True, cwd=workspace, timeout=5,
                    ).stdout.strip()
                    from gateway.ws_hub import broadcast
                    import asyncio
                    await broadcast("git", {
                        "branch": branch,
                        "files_changed": len([l for l in status_out.split("\n") if l.strip()]),
                    })
                except Exception:
                    pass

        # WebSocket stats endpoint.
        async def handle_ws_stats(request):
            hub = get_hub()
            return web.json_response(hub.get_stats())

        app.router.add_get(OVERLAY_WS_STATS_PATH, handle_ws_stats)
    except ImportError:
        pass

    async def handle_streaks(_request):
        try:
            from gateway.streaks import get_streak_api_data
            return web.json_response(get_streak_api_data())
        except Exception as e:
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    async def handle_streaks_record(_request):
        try:
            from gateway.streaks import StreakTracker
            info = StreakTracker().record_activity()
            return web.json_response({"ok": True, "streak": info})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    app.router.add_get("/api/panels/streaks", handle_streaks)
    app.router.add_post("/api/panels/streaks/record", handle_streaks_record)

    logger.info("Panel routes registered: git, crew, daemon, cost, ws, streaks")
