"""
Streak Tracker — daily usage streak persistence.

Tracks consecutive days of agent usage, stores in SQLite.
Awards milestones at 3, 7, 14, 30, 60, 100, 365 days.

Usage:
    from gateway.streaks import StreakTracker
    tracker = StreakTracker()
    tracker.record_activity()          # Call on each agent interaction
    info = tracker.get_streak_info()   # Get current streak data
    print(info['current_streak'])      # e.g. 7
    print(info['milestones'])          # e.g. ['🔥 3-day streak', '⚡ 7-day streak']
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes.streaks")


# ============================================================================
# Milestone Definitions
# ============================================================================

MILESTONES = [
    (3,   "🔥", "3-day streak",   "First flame — consistency begins"),
    (7,   "⚡", "7-day streak",   "One full week — you're locked in"),
    (14,  "💎", "14-day streak",  "Two weeks strong — diamond hands"),
    (30,  "👑", "30-day streak",  "A full month — crown achievement"),
    (60,  "🏆", "60-day streak",  "Two months — legendary dedication"),
    (100, "⭐", "100-day streak", "Triple digits — unstoppable"),
    (200, "🌟", "200-day streak", "Half-year strong — mythic status"),
    (365, "🗡️", "365-day streak", "Zanpakutō mastered — one full year"),
]


# ============================================================================
# Streak Tracker
# ============================================================================

class StreakTracker:
    """SQLite-backed daily streak tracker."""

    def __init__(self, db_dir: str = None):
        self._db_dir = db_dir or os.path.join(
            os.path.expanduser("~"), ".hermes"
        )
        os.makedirs(self._db_dir, exist_ok=True)
        self._db_path = os.path.join(self._db_dir, "streaks.db")
        self._conn = sqlite3.connect(self._db_path)
        self._init_db()

    def _init_db(self):
        """Create tables on first run."""
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=3000")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_activity (
                date TEXT PRIMARY KEY,
                interactions INTEGER DEFAULT 1,
                first_at REAL NOT NULL,
                last_at REAL NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                models_used TEXT DEFAULT '[]'
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                name TEXT PRIMARY KEY,
                reached_at REAL NOT NULL,
                streak_length INTEGER NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS streak_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def record_activity(
        self,
        tokens: int = 0,
        model: str = "",
    ) -> Dict[str, Any]:
        """Record an interaction for today.

        Returns streak info including any new milestones achieved.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        now = time.time()

        # Upsert today's activity.
        existing = self._conn.execute(
            "SELECT interactions, models_used FROM daily_activity WHERE date = ?",
            (today,),
        ).fetchone()

        if existing:
            count = existing[0] + 1
            import json
            models = json.loads(existing[1] or "[]")
            if model and model not in models:
                models.append(model)
            self._conn.execute(
                "UPDATE daily_activity SET interactions = ?, last_at = ?, tokens_used = tokens_used + ?, models_used = ? WHERE date = ?",
                (count, now, tokens, json.dumps(models), today),
            )
        else:
            import json
            models = [model] if model else []
            self._conn.execute(
                "INSERT INTO daily_activity (date, interactions, first_at, last_at, tokens_used, models_used) VALUES (?, 1, ?, ?, ?, ?)",
                (today, now, now, tokens, json.dumps(models)),
            )

        self._conn.commit()

        # Calculate streak and check milestones.
        info = self.get_streak_info()

        # Check for new milestones.
        new_milestones = []
        for days, emoji, name, desc in MILESTONES:
            if info["current_streak"] >= days:
                existing_ms = self._conn.execute(
                    "SELECT 1 FROM milestones WHERE name = ?", (name,)
                ).fetchone()
                if not existing_ms:
                    self._conn.execute(
                        "INSERT INTO milestones (name, reached_at, streak_length) VALUES (?, ?, ?)",
                        (name, now, info["current_streak"]),
                    )
                    new_milestones.append(f"{emoji} {name}: {desc}")

        if new_milestones:
            self._conn.commit()
            info["new_milestones"] = new_milestones
            for ms in new_milestones:
                logger.info("🏅 Milestone reached: %s", ms)

        return info

    def get_streak_info(self) -> Dict[str, Any]:
        """Calculate current streak and stats."""
        # Get all activity dates, sorted descending.
        rows = self._conn.execute(
            "SELECT date FROM daily_activity ORDER BY date DESC"
        ).fetchall()

        if not rows:
            return {
                "current_streak": 0,
                "longest_streak": 0,
                "total_days": 0,
                "total_interactions": 0,
                "milestones": [],
                "new_milestones": [],
            }

        dates = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]
        today = datetime.now().date()

        # Current streak: count consecutive days from today.
        current_streak = 0
        check_date = today
        for d in dates:
            if d == check_date:
                current_streak += 1
                check_date -= timedelta(days=1)
            elif d < check_date:
                break

        # If we didn't start from today, check if yesterday counts.
        if current_streak == 0 and dates and dates[0] == today - timedelta(days=1):
            check_date = today - timedelta(days=1)
            for d in dates:
                if d == check_date:
                    current_streak += 1
                    check_date -= timedelta(days=1)
                elif d < check_date:
                    break

        # Longest streak ever.
        longest = 0
        streak = 0
        prev = None
        for d in sorted(dates):
            if prev is None or d == prev + timedelta(days=1):
                streak += 1
            else:
                streak = 1
            longest = max(longest, streak)
            prev = d

        # Total stats.
        total_days = len(dates)
        total_interactions = self._conn.execute(
            "SELECT COALESCE(SUM(interactions), 0) FROM daily_activity"
        ).fetchone()[0]
        total_tokens = self._conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM daily_activity"
        ).fetchone()[0]

        # Milestones achieved.
        milestones = [
            {"name": r[0], "reached_at": r[1], "streak_length": r[2]}
            for r in self._conn.execute(
                "SELECT name, reached_at, streak_length FROM milestones ORDER BY streak_length"
            ).fetchall()
        ]

        # Streak display.
        if current_streak >= 365:
            streak_display = f"🗡️ {current_streak} days (Zanpakutō Mastered)"
        elif current_streak >= 100:
            streak_display = f"⭐ {current_streak} days (Legendary)"
        elif current_streak >= 30:
            streak_display = f"👑 {current_streak} days (Crown)"
        elif current_streak >= 7:
            streak_display = f"⚡ {current_streak} days"
        elif current_streak >= 3:
            streak_display = f"🔥 {current_streak} days"
        elif current_streak > 0:
            streak_display = f"✨ {current_streak} day{'s' if current_streak > 1 else ''}"
        else:
            streak_display = "Start your streak today!"

        return {
            "current_streak": current_streak,
            "longest_streak": longest,
            "total_days": total_days,
            "total_interactions": total_interactions,
            "total_tokens": total_tokens,
            "streak_display": streak_display,
            "milestones": milestones,
            "new_milestones": [],
        }

    def get_activity_heatmap(self, days: int = 90) -> List[Dict[str, Any]]:
        """Get daily activity for the last N days (for GitHub-style heatmap)."""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT date, interactions, tokens_used FROM daily_activity WHERE date >= ? ORDER BY date",
            (cutoff,),
        ).fetchall()

        heatmap = []
        for date, interactions, tokens in rows:
            # Intensity: 0-4 based on interactions.
            if interactions >= 20:
                intensity = 4
            elif interactions >= 10:
                intensity = 3
            elif interactions >= 5:
                intensity = 2
            elif interactions >= 1:
                intensity = 1
            else:
                intensity = 0

            heatmap.append({
                "date": date,
                "interactions": interactions,
                "tokens": tokens,
                "intensity": intensity,
            })

        return heatmap

    def reset(self) -> None:
        """Reset all streak data. Use with caution."""
        self._conn.execute("DELETE FROM daily_activity")
        self._conn.execute("DELETE FROM milestones")
        self._conn.execute("DELETE FROM streak_meta")
        self._conn.commit()
        logger.info("Streak data reset")


# ============================================================================
# API Routes (for panel_routes)
# ============================================================================

def get_streak_api_data() -> Dict[str, Any]:
    """Get streak data formatted for API response."""
    try:
        tracker = StreakTracker()
        info = tracker.get_streak_info()
        heatmap = tracker.get_activity_heatmap(90)
        return {
            "streak": info,
            "heatmap": heatmap,
            "status": "ok",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Streak Tracker")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("info", help="Show current streak")
    sub.add_parser("record", help="Record activity")
    sub.add_parser("heatmap", help="Show activity heatmap")
    sub.add_parser("reset", help="Reset all data")

    args = parser.parse_args()
    tracker = StreakTracker()

    if args.cmd == "record":
        result = tracker.record_activity()
        print(f"Streak: {result['streak_display']}")
        for ms in result.get("new_milestones", []):
            print(f"  NEW: {ms}")

    elif args.cmd == "heatmap":
        heatmap = tracker.get_activity_heatmap()
        if not heatmap:
            print("No activity recorded yet.")
        else:
            for entry in heatmap[-30:]:  # Last 30 days
                bar = "█" * entry["intensity"] + "░" * (4 - entry["intensity"])
                print(f"  {entry['date']}  {bar}  {entry['interactions']} interactions")

    elif args.cmd == "reset":
        confirm = input("Reset all streak data? (yes/no): ")
        if confirm.lower() == "yes":
            tracker.reset()
            print("Reset complete.")
    else:
        info = tracker.get_streak_info()
        print(f"\n  {info['streak_display']}")
        print(f"  Longest: {info['longest_streak']} days")
        print(f"  Total:   {info['total_days']} active days, {info['total_interactions']} interactions")
        if info["milestones"]:
            print(f"\n  Milestones:")
            for ms in info["milestones"]:
                print(f"    ✓ {ms['name']}")
        print()
