"""
Smart Context Window — AST-based file inclusion.

Instead of stuffing the entire codebase into the LLM context,
intelligently selects only the relevant files based on:
1. Codebase knowledge graph (imports, calls, inheritance)
2. File proximity (same directory, related names)
3. Recent edits (files changed in last N commits)
4. Token budget (never exceed the model's context window)

Usage:
    from gateway.smart_context import SmartContextBuilder

    builder = SmartContextBuilder(workspace_path="/path/to/project")
    context = builder.build_context(
        target_file="src/auth.py",
        prompt="Fix the JWT validation bug",
        max_tokens=4000,
    )
    # Returns: relevant file contents + graph context, within token budget
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("hermes.smart_context")


@dataclass
class ContextFile:
    """A file included in the smart context."""
    path: str              # Absolute path
    rel_path: str          # Relative to workspace
    content: str           # File content (possibly truncated)
    relevance: float       # 0.0-1.0 relevance score
    reason: str            # Why this file was included
    tokens_estimate: int   # Rough token count (len/4)


class SmartContextBuilder:
    """Build an optimal context window for LLM from the codebase graph."""

    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)

    def build_context(
        self,
        target_file: str = "",
        prompt: str = "",
        max_tokens: int = 4000,
        include_graph: bool = True,
        include_recent: bool = True,
    ) -> str:
        """Build a smart context string within the token budget.

        Priority order:
        1. Target file itself (highest priority)
        2. Graph neighbors (files that import/call the target)
        3. Same-directory siblings
        4. Recently edited files
        5. Codebase graph map (compact overview)
        """
        budget = max_tokens
        sections: List[str] = []
        included_files: Set[str] = set()

        # 1. Target file.
        if target_file:
            abs_path = os.path.join(self.workspace_path, target_file) if not os.path.isabs(target_file) else target_file
            if os.path.isfile(abs_path):
                content = self._read_file(abs_path, max_chars=budget * 4)
                tokens = len(content) // 4
                if tokens <= budget:
                    rel = os.path.relpath(abs_path, self.workspace_path)
                    sections.append(f"### Target File: {rel}\n```\n{content}\n```")
                    budget -= tokens
                    included_files.add(abs_path)

        # 2. Graph neighbors.
        if include_graph and budget > 500:
            graph_context = self._get_graph_neighbors(target_file, budget // 2)
            if graph_context:
                tokens = len(graph_context) // 4
                sections.append(f"### Related Code (from knowledge graph)\n{graph_context}")
                budget -= tokens

        # 3. Same-directory siblings.
        if target_file and budget > 300:
            dir_path = os.path.dirname(
                os.path.join(self.workspace_path, target_file)
                if not os.path.isabs(target_file)
                else target_file
            )
            siblings = self._get_sibling_files(dir_path, included_files, budget)
            if siblings:
                for sf in siblings:
                    if budget <= 100:
                        break
                    tokens = len(sf.content) // 4
                    if tokens <= budget:
                        sections.append(f"### {sf.rel_path} ({sf.reason})\n```\n{sf.content}\n```")
                        budget -= tokens
                        included_files.add(sf.path)

        # 4. Recent edits.
        if include_recent and budget > 300:
            recent = self._get_recent_edits(included_files, budget)
            if recent:
                recent_summary = "### Recently Modified Files\n"
                for rf in recent[:5]:
                    recent_summary += f"- {rf.rel_path} ({rf.reason})\n"
                tokens = len(recent_summary) // 4
                if tokens <= budget:
                    sections.append(recent_summary)
                    budget -= tokens

        # 5. Compact graph map.
        if include_graph and budget > 200:
            repo_map = self._get_repo_map(budget)
            if repo_map:
                sections.append(f"### Repository Structure\n{repo_map}")

        return "\n\n".join(sections)

    def _read_file(self, path: str, max_chars: int = 16000) -> str:
        """Read a file, truncating if too large."""
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n... (truncated, {len(content)} chars total)"
            return content
        except Exception:
            return ""

    def _get_graph_neighbors(self, target_file: str, max_tokens: int) -> str:
        """Get related files from the codebase knowledge graph."""
        try:
            from gateway.codebase_graph import get_graph_manager
            manager = get_graph_manager()
            graph = manager.get_graph(self.workspace_path)
            if not graph:
                return ""

            abs_path = (
                os.path.join(self.workspace_path, target_file)
                if not os.path.isabs(target_file)
                else target_file
            )
            context = manager.get_context_for_file(self.workspace_path, abs_path)
            if len(context) // 4 > max_tokens:
                context = context[:max_tokens * 4]
            return context
        except Exception:
            return ""

    def _get_sibling_files(
        self,
        dir_path: str,
        exclude: Set[str],
        max_tokens: int,
    ) -> List[ContextFile]:
        """Get files in the same directory."""
        result = []
        if not os.path.isdir(dir_path):
            return result

        code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c", ".h"}
        try:
            for entry in sorted(os.listdir(dir_path)):
                path = os.path.join(dir_path, entry)
                if path in exclude or not os.path.isfile(path):
                    continue
                ext = os.path.splitext(entry)[1].lower()
                if ext not in code_exts:
                    continue

                content = self._read_file(path, max_chars=2000)
                tokens = len(content) // 4
                if tokens > max_tokens:
                    continue

                result.append(ContextFile(
                    path=path,
                    rel_path=os.path.relpath(path, self.workspace_path),
                    content=content,
                    relevance=0.5,
                    reason="same directory",
                    tokens_estimate=tokens,
                ))
                max_tokens -= tokens

                if len(result) >= 3:
                    break
        except Exception:
            pass
        return result

    def _get_recent_edits(self, exclude: Set[str], max_tokens: int) -> List[ContextFile]:
        """Get recently modified files from git."""
        result = []
        try:
            proc = subprocess.run(
                ["git", "log", "--oneline", "--name-only", "-10", "--pretty=format:"],
                capture_output=True, text=True, timeout=5,
                cwd=self.workspace_path,
            )
            if proc.returncode != 0:
                return result

            seen: Set[str] = set()
            for line in proc.stdout.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                path = os.path.join(self.workspace_path, line)
                if path in exclude or path in seen or not os.path.isfile(path):
                    continue
                seen.add(path)

                result.append(ContextFile(
                    path=path,
                    rel_path=line,
                    content="",  # Don't include full content — just reference.
                    relevance=0.3,
                    reason="recently modified",
                    tokens_estimate=0,
                ))

                if len(result) >= 5:
                    break
        except Exception:
            pass
        return result

    def _get_repo_map(self, max_tokens: int) -> str:
        """Get compact repo map from the knowledge graph."""
        try:
            from gateway.codebase_graph import get_graph_manager
            manager = get_graph_manager()
            graph = manager.get_graph(self.workspace_path)
            if graph:
                return graph.to_context_string(max_tokens=max_tokens)
        except Exception:
            pass
        return ""
