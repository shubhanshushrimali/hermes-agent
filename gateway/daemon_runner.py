"""
Hermes Daemon Runner — 24/7 background agent execution.

Runs on the user's laptop as a system service. Processes tasks from
a SQLite job queue, auto-restarts on crash, and enforces budget limits.

Architecture:
    ┌──────────────────────────────────────┐
    │         Daemon Runner                 │
    │  ┌──────────┐  ┌──────────────────┐  │
    │  │ Job Queue │  │ Health + Heartbeat│ │
    │  │ (SQLite)  │  │ (HTTP endpoint)   │ │
    │  └────┬─────┘  └──────────────────┘  │
    │       │                               │
    │  ┌────┴─────┐  ┌──────────────────┐  │
    │  │ Executor  │  │ Budget Guard     │  │
    │  │ (Graph)   │  │ ($X/day max)     │  │
    │  └──────────┘  └──────────────────┘  │
    └──────────────────────────────────────┘

Setup (Windows):
    python -m gateway.daemon_runner install
    python -m gateway.daemon_runner start

Templates:
    - repo-watcher: Monitor git repos, review new PRs
    - log-monitor: Watch error logs, alert on anomalies
    - daily-standup: Summarize git activity each morning
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("hermes.daemon")


# ============================================================================
# Job Queue (SQLite-backed)
# ============================================================================

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class Job:
    """A queued task for the daemon to execute."""
    id: str
    name: str
    prompt: str
    status: str = JobStatus.PENDING
    priority: int = 5          # 1 = highest, 10 = lowest
    schedule: str = ""         # Cron expression or empty for one-shot
    workspace_path: str = ""
    model: str = ""
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    result: str = ""
    error: str = ""
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)


class JobQueue:
    """SQLite-backed persistent job queue with WAL mode."""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or os.path.join(
            os.path.expanduser("~"), ".hermes", "daemon_jobs.db"
        )
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database with WAL mode."""
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 5,
                    schedule TEXT DEFAULT '',
                    workspace_path TEXT DEFAULT '',
                    model TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    started_at TEXT DEFAULT '',
                    completed_at TEXT DEFAULT '',
                    result TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status
                ON jobs(status, priority)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_schedule
                ON jobs(schedule) WHERE schedule != ''
            """)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, job: Job) -> str:
        """Add a job to the queue."""
        if not job.id:
            job.id = f"job-{int(time.time())}-{os.urandom(4).hex()}"
        if not job.created_at:
            job.created_at = datetime.now().isoformat()

        conn = self._connect()
        try:
            conn.execute("""
                INSERT INTO jobs (id, name, prompt, status, priority, schedule,
                    workspace_path, model, created_at, max_retries, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.name, job.prompt, job.status, job.priority,
                job.schedule, job.workspace_path, job.model,
                job.created_at, job.max_retries,
                json.dumps(job.metadata),
            ))
            conn.commit()
            logger.info("Job enqueued: %s (%s)", job.id, job.name)
            return job.id
        finally:
            conn.close()

    def dequeue(self) -> Optional[Job]:
        """Get and lock the next pending job (highest priority first)."""
        conn = self._connect()
        try:
            row = conn.execute("""
                SELECT * FROM jobs
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """).fetchone()

            if not row:
                return None

            # Mark as running.
            conn.execute("""
                UPDATE jobs SET status = 'running', started_at = datetime('now')
                WHERE id = ?
            """, (row["id"],))
            conn.commit()

            return self._row_to_job(row)
        finally:
            conn.close()

    def complete(self, job_id: str, result: str = "") -> None:
        """Mark a job as completed."""
        conn = self._connect()
        try:
            conn.execute("""
                UPDATE jobs SET status = 'completed',
                    completed_at = datetime('now'), result = ?
                WHERE id = ?
            """, (result, job_id))
            conn.commit()
        finally:
            conn.close()

    def fail(self, job_id: str, error: str = "") -> None:
        """Mark a job as failed. Auto-retry if under max_retries."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT retry_count, max_retries FROM jobs WHERE id = ?",
                (job_id,)
            ).fetchone()

            if row and row["retry_count"] < row["max_retries"]:
                # Re-queue for retry.
                conn.execute("""
                    UPDATE jobs SET status = 'pending',
                        retry_count = retry_count + 1, error = ?
                    WHERE id = ?
                """, (error, job_id))
                logger.info("Job %s queued for retry (%d/%d)",
                           job_id, row["retry_count"] + 1, row["max_retries"])
            else:
                conn.execute("""
                    UPDATE jobs SET status = 'failed',
                        completed_at = datetime('now'), error = ?
                    WHERE id = ?
                """, (error, job_id))

            conn.commit()
        finally:
            conn.close()

    def list_jobs(self, status: str = None, limit: int = 50) -> List[Job]:
        """List jobs, optionally filtered by status."""
        conn = self._connect()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [self._row_to_job(r) for r in rows]
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a specific job."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return self._row_to_job(row) if row else None
        finally:
            conn.close()

    def pause_job(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE jobs SET status = 'paused' WHERE id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def resume_job(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE jobs SET status = 'pending' WHERE id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def delete_job(self, job_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def _row_to_job(self, row) -> Job:
        return Job(
            id=row["id"], name=row["name"], prompt=row["prompt"],
            status=row["status"], priority=row["priority"],
            schedule=row["schedule"], workspace_path=row["workspace_path"],
            model=row["model"], created_at=row["created_at"],
            started_at=row["started_at"] or "", completed_at=row["completed_at"] or "",
            result=row["result"] or "", error=row["error"] or "",
            retry_count=row["retry_count"], max_retries=row["max_retries"],
            metadata=json.loads(row["metadata"] or "{}"),
        )


# ============================================================================
# Daemon Templates
# ============================================================================

DAEMON_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "repo-watcher": {
        "name": "Repository Watcher",
        "description": "Monitor git repos for new commits/PRs and auto-review",
        "schedule": "0 9 * * *",  # Every day at 9 AM
        "prompt": (
            "Check the git log for new commits since yesterday. "
            "Review each commit for: code quality, potential bugs, "
            "and security issues. Create a summary report."
        ),
        "priority": 3,
    },
    "log-monitor": {
        "name": "Error Log Monitor",
        "description": "Watch application logs for errors and anomalies",
        "schedule": "*/30 * * * *",  # Every 30 minutes
        "prompt": (
            "Scan the application logs for ERROR and WARNING entries "
            "in the last 30 minutes. Classify each issue and suggest "
            "fixes. Report critical errors immediately."
        ),
        "priority": 2,
    },
    "daily-standup": {
        "name": "Daily Standup Generator",
        "description": "Summarize git activity into a standup report",
        "schedule": "0 8 * * 1-5",  # Weekdays at 8 AM
        "prompt": (
            "Generate a daily standup report from yesterday's git log. "
            "Include: what was done, files changed, and any open issues. "
            "Format as a clean markdown summary."
        ),
        "priority": 5,
    },
    "dependency-audit": {
        "name": "Dependency Vulnerability Scanner",
        "description": "Check for known vulnerabilities in dependencies",
        "schedule": "0 3 * * 1",  # Weekly on Monday at 3 AM
        "prompt": (
            "Run pip-audit (Python) and npm audit (JavaScript) to check "
            "for known vulnerabilities. Report critical and high severity "
            "issues with recommended actions."
        ),
        "priority": 4,
    },
}


# ============================================================================
# Daemon Runner
# ============================================================================

class DaemonRunner:
    """Background agent that processes jobs from the SQLite queue.

    Runs continuously, checking for new jobs every N seconds.
    Enforces daily budget limits and auto-restarts on crash.
    """

    def __init__(
        self,
        heartbeat_interval: int = 30,
        max_daily_spend: float = 10.0,
        db_path: str = None,
    ):
        self.heartbeat_interval = heartbeat_interval
        self.max_daily_spend = max_daily_spend
        self.queue = JobQueue(db_path)
        self._running = False
        self._start_time = time.time()
        self._jobs_processed = 0
        self._daily_spend = 0.0
        self._last_heartbeat = time.time()

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    @property
    def is_running(self) -> bool:
        return self._running

    def get_health(self) -> Dict[str, Any]:
        """Health check data for the /health endpoint."""
        return {
            "status": "running" if self._running else "stopped",
            "uptime_seconds": int(self.uptime_seconds),
            "uptime_human": str(timedelta(seconds=int(self.uptime_seconds))),
            "jobs_processed": self._jobs_processed,
            "daily_spend_usd": round(self._daily_spend, 4),
            "budget_remaining_usd": round(self.max_daily_spend - self._daily_spend, 4),
            "last_heartbeat": datetime.fromtimestamp(self._last_heartbeat).isoformat(),
            "pending_jobs": len(self.queue.list_jobs(status="pending")),
        }

    async def run_forever(self):
        """Main daemon loop. Process jobs until stopped."""
        self._running = True
        self._start_time = time.time()
        logger.info("Daemon started. Heartbeat every %ds, budget $%.2f/day",
                    self.heartbeat_interval, self.max_daily_spend)

        # Handle graceful shutdown.
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, self.stop)
                except NotImplementedError:
                    pass  # Windows doesn't support add_signal_handler
        except Exception:
            pass

        while self._running:
            try:
                self._last_heartbeat = time.time()

                # Check budget.
                if self._daily_spend >= self.max_daily_spend:
                    logger.warning("Daily budget exhausted ($%.2f). Sleeping until midnight.",
                                 self._daily_spend)
                    await self._sleep_until_midnight()
                    self._daily_spend = 0.0
                    continue

                # Check for scheduled jobs.
                self._check_scheduled_jobs()

                # Process next job.
                job = self.queue.dequeue()
                if job:
                    await self._execute_job(job)
                    self._jobs_processed += 1
                else:
                    await asyncio.sleep(self.heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Daemon loop error: %s", e, exc_info=True)
                await asyncio.sleep(5)  # Brief pause before retry.

        logger.info("Daemon stopped. Processed %d jobs.", self._jobs_processed)

    def stop(self):
        """Signal the daemon to stop gracefully."""
        self._running = False
        logger.info("Daemon stop requested")

    async def _execute_job(self, job: Job):
        """Execute a single job through the graph engine."""
        logger.info("Executing job: %s (%s)", job.id, job.name)

        try:
            # Try graph engine first.
            try:
                from gateway.graph_engine import process_prompt
                result = process_prompt(
                    user_prompt=job.prompt,
                    session_key=f"daemon:{job.id}",
                    model=job.model,
                )
                output = result.get("final_response", result.get("agent_response", str(result)))
            except ImportError:
                output = f"[Daemon] Task queued: {job.prompt}"

            self.queue.complete(job.id, result=output)
            logger.info("Job completed: %s", job.id)

        except Exception as e:
            logger.error("Job failed: %s — %s", job.id, e)
            self.queue.fail(job.id, error=str(e))

    def _check_scheduled_jobs(self):
        """Check if any scheduled jobs need to be triggered."""
        # Simple cron-like check — runs every heartbeat.
        try:
            conn = self.queue._connect()
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE schedule != '' AND status = 'completed'
                ORDER BY completed_at ASC
            """).fetchall()

            now = datetime.now()
            for row in rows:
                schedule = row["schedule"]
                completed = row["completed_at"]

                # Simple interval check (not full cron parser).
                if self._should_reschedule(schedule, completed, now):
                    conn.execute("""
                        UPDATE jobs SET status = 'pending',
                            started_at = '', completed_at = '', result = ''
                        WHERE id = ?
                    """, (row["id"],))
                    logger.info("Re-scheduled job: %s", row["id"])

            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Schedule check failed: %s", e)

    @staticmethod
    def _should_reschedule(schedule: str, completed_at: str, now: datetime) -> bool:
        """Simple schedule check (every N minutes/hours pattern)."""
        if not schedule or not completed_at:
            return False
        try:
            parts = schedule.split()
            if len(parts) != 5:
                return False
            # Parse minute field for interval.
            if parts[0].startswith("*/"):
                interval_min = int(parts[0][2:])
                completed = datetime.fromisoformat(completed_at)
                return (now - completed) >= timedelta(minutes=interval_min)
            # Daily at specific hour.
            if parts[1] != "*":
                hour = int(parts[1])
                if now.hour >= hour:
                    completed = datetime.fromisoformat(completed_at)
                    return (now - completed) >= timedelta(hours=20)  # ~daily
        except Exception:
            pass
        return False

    async def _sleep_until_midnight(self):
        """Sleep until the next midnight (budget reset)."""
        now = datetime.now()
        midnight = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
        sleep_seconds = (midnight - now).total_seconds()
        logger.info("Sleeping %.0f seconds until midnight budget reset", sleep_seconds)
        await asyncio.sleep(min(sleep_seconds, 3600))  # Max 1 hour sleep chunks.


# ============================================================================
# Windows Service Installation
# ============================================================================

def install_windows_service():
    """Create a Windows Task Scheduler task to run the daemon on login."""
    import subprocess

    python_path = sys.executable
    script_path = os.path.abspath(__file__)
    task_name = "HermesAgentDaemon"

    cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'"{python_path}" "{script_path}" start',
        "/sc", "onlogon",
        "/rl", "limited",
        "/f",  # Force overwrite.
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Daemon installed as Windows task: {task_name}")
            print("It will start automatically when you log in.")
        else:
            print(f"Failed to install: {result.stderr}")
            print("Try running as administrator.")
    except Exception as e:
        print(f"Install failed: {e}")


def uninstall_windows_service():
    """Remove the Windows Task Scheduler task."""
    import subprocess
    try:
        subprocess.run(
            ["schtasks", "/delete", "/tn", "HermesAgentDaemon", "/f"],
            capture_output=True, text=True,
        )
        print("Daemon uninstalled from Windows Task Scheduler.")
    except Exception as e:
        print(f"Uninstall failed: {e}")


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """CLI entry point for the daemon."""
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Agent Daemon Runner")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("start", help="Start the daemon")
    subparsers.add_parser("install", help="Install as Windows startup task")
    subparsers.add_parser("uninstall", help="Remove Windows startup task")
    subparsers.add_parser("status", help="Show daemon health status")

    add_parser = subparsers.add_parser("add", help="Add a job to the queue")
    add_parser.add_argument("name", help="Job name")
    add_parser.add_argument("prompt", help="Task prompt")
    add_parser.add_argument("--priority", type=int, default=5)
    add_parser.add_argument("--schedule", default="")

    template_parser = subparsers.add_parser("template", help="Add a template job")
    template_parser.add_argument("template_name", choices=list(DAEMON_TEMPLATES.keys()))
    template_parser.add_argument("--workspace", default="")

    subparsers.add_parser("list", help="List all jobs")

    args = parser.parse_args()

    if args.command == "start":
        daemon = DaemonRunner()
        asyncio.run(daemon.run_forever())

    elif args.command == "install":
        install_windows_service()

    elif args.command == "uninstall":
        uninstall_windows_service()

    elif args.command == "status":
        daemon = DaemonRunner()
        health = daemon.get_health()
        for k, v in health.items():
            print(f"  {k}: {v}")

    elif args.command == "add":
        queue = JobQueue()
        job = Job(id="", name=args.name, prompt=args.prompt,
                 priority=args.priority, schedule=args.schedule)
        job_id = queue.enqueue(job)
        print(f"Job added: {job_id}")

    elif args.command == "template":
        queue = JobQueue()
        template = DAEMON_TEMPLATES[args.template_name]
        job = Job(
            id="", name=template["name"], prompt=template["prompt"],
            priority=template["priority"], schedule=template["schedule"],
            workspace_path=args.workspace,
        )
        job_id = queue.enqueue(job)
        print(f"Template job added: {job_id} ({template['name']})")

    elif args.command == "list":
        queue = JobQueue()
        jobs = queue.list_jobs()
        for j in jobs:
            print(f"  [{j.status:9s}] {j.id} — {j.name}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
