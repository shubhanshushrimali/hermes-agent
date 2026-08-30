"""
Git Auto-Commit Hook — creates a git commit after each agent file write.

Every agent action that modifies files gets its own commit, enabling:
- Undo via `git revert`
- Full change history in the diff review UI
- Agent vs human commits are tagged differently

Usage:
    from gateway.git_hooks import auto_commit_agent_changes

    # After agent writes files:
    auto_commit_agent_changes(
        workspace="/path/to/project",
        files_changed=["src/auth.py", "tests/test_auth.py"],
        description="Fixed JWT expiry validation",
        agent_name="Fix Engineer",
    )
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import List, Optional

logger = logging.getLogger("hermes.git_hooks")

# Prefix for all agent commits — makes them easy to filter/revert.
AGENT_COMMIT_PREFIX = "[hermes-agent]"


def auto_commit_agent_changes(
    workspace: str,
    files_changed: List[str],
    description: str = "Agent changes",
    agent_name: str = "hermes-agent",
    auto_stage: bool = True,
) -> Optional[str]:
    """Create a git commit for agent changes.

    Args:
        workspace: Project root (must be a git repo).
        files_changed: List of file paths that were modified.
        description: What the agent did.
        agent_name: Which agent made the changes.
        auto_stage: Stage the files before committing.

    Returns:
        Commit hash if successful, None otherwise.
    """
    if not _is_git_repo(workspace):
        return None

    try:
        if auto_stage:
            # Stage only the files the agent changed.
            for f in files_changed:
                abs_path = os.path.join(workspace, f) if not os.path.isabs(f) else f
                if os.path.exists(abs_path):
                    subprocess.run(
                        ["git", "add", abs_path],
                        cwd=workspace, timeout=5,
                        capture_output=True,
                    )

        # Check if there's anything to commit.
        status = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=workspace, timeout=5,
            capture_output=True,
        )
        if status.returncode == 0:
            # Nothing staged.
            return None

        # Build commit message.
        commit_msg = f"{AGENT_COMMIT_PREFIX} {description}"
        if agent_name != "hermes-agent":
            commit_msg += f" (by {agent_name})"

        # Commit with agent author.
        result = subprocess.run(
            [
                "git", "commit",
                "-m", commit_msg,
                "--author", f"{agent_name} <hermes@agent.local>",
            ],
            cwd=workspace, timeout=10,
            capture_output=True, text=True,
        )

        if result.returncode == 0:
            # Get the commit hash.
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=workspace, timeout=5,
                capture_output=True, text=True,
            )
            commit_hash = hash_result.stdout.strip()
            logger.info(
                "Auto-committed agent changes: %s (%s)",
                commit_hash[:8], description,
            )
            return commit_hash
        else:
            logger.debug("Git commit failed: %s", result.stderr)
            return None

    except Exception as e:
        logger.debug("Auto-commit failed: %s", e)
        return None


def revert_agent_commit(workspace: str, commit_hash: str) -> bool:
    """Revert a specific agent commit.

    Args:
        workspace: Project root.
        commit_hash: The commit to revert.

    Returns:
        True if revert succeeded.
    """
    try:
        result = subprocess.run(
            ["git", "revert", "--no-edit", commit_hash],
            cwd=workspace, timeout=30,
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("Reverted agent commit: %s", commit_hash[:8])
            return True
        else:
            logger.warning("Revert failed: %s", result.stderr)
            return False
    except Exception as e:
        logger.debug("Revert failed: %s", e)
        return False


def get_agent_commits(workspace: str, limit: int = 20) -> list:
    """Get recent agent commits (filtered by prefix)."""
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"-{limit}",
                f"--grep={AGENT_COMMIT_PREFIX}",
                "--pretty=format:%H|%h|%s|%aI",
            ],
            cwd=workspace, timeout=10,
            capture_output=True, text=True,
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "message": parts[2],
                    "date": parts[3],
                })
        return commits
    except Exception:
        return []


def _is_git_repo(path: str) -> bool:
    """Check if a directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path, timeout=3,
            capture_output=True,
        )
        return result.returncode == 0
    except Exception:
        return False
