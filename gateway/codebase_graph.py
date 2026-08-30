"""
Codebase Knowledge Graph — Project-aware graph indexing for Hermes Agent.

Converts any project/workspace into a queryable knowledge graph so agents
can "see" the entire codebase structure: functions, classes, imports,
call chains, and dependencies.

Three-tier approach:
1. **Graphify** (if installed): Full multi-pass graph with MCP support
2. **Built-in Tree-sitter**: Lightweight AST-based graph (no LLM cost)
3. **Fallback Regex**: Simple file/import scanning (always works)

Usage:
    from gateway.codebase_graph import CodebaseGraphManager

    manager = CodebaseGraphManager()
    graph = await manager.index_workspace("/path/to/project")

    # Query the graph
    result = manager.query("What calls the auth middleware?")
    neighbors = manager.get_neighbors("AuthService")
    path = manager.shortest_path("UserController", "DatabaseClient")

Integration with graph_engine.py:
    The research node in the LangGraph state machine uses this to
    auto-include relevant code context before asking the LLM to code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("hermes.codebase_graph")


# ============================================================================
# Graph Node & Edge Types
# ============================================================================

@dataclass
class GraphNode:
    """A node in the codebase knowledge graph."""
    id: str                          # Unique identifier
    name: str                        # Human-readable name
    kind: str                        # file, class, function, method, module, variable
    file_path: str = ""              # Absolute path to source file
    line_start: int = 0              # Line number where definition starts
    line_end: int = 0                # Line number where definition ends
    language: str = ""               # Programming language
    signature: str = ""              # Function/method signature
    docstring: str = ""              # Extracted docstring
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "file_path": self.file_path, "line_start": self.line_start,
            "line_end": self.line_end, "language": self.language,
            "signature": self.signature,
        }


@dataclass
class GraphEdge:
    """An edge connecting two nodes in the graph."""
    source: str        # Source node ID
    target: str        # Target node ID
    kind: str          # calls, imports, inherits, uses, defines
    confidence: str    # EXTRACTED (from AST), INFERRED, AMBIGUOUS
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CodebaseGraph:
    """The full knowledge graph for a codebase."""
    workspace_path: str
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    indexed_at: float = 0.0
    file_count: int = 0
    language_stats: Dict[str, int] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def get_neighbors(self, node_id: str, direction: str = "both") -> List[Tuple[GraphNode, GraphEdge]]:
        """Get all nodes connected to the given node."""
        result = []
        for edge in self.edges:
            if direction in ("out", "both") and edge.source == node_id:
                if edge.target in self.nodes:
                    result.append((self.nodes[edge.target], edge))
            if direction in ("in", "both") and edge.target == node_id:
                if edge.source in self.nodes:
                    result.append((self.nodes[edge.source], edge))
        return result

    def search_nodes(self, pattern: str, kind: str = None) -> List[GraphNode]:
        """Search nodes by name pattern."""
        regex = re.compile(pattern, re.IGNORECASE)
        results = []
        for node in self.nodes.values():
            if regex.search(node.name):
                if kind is None or node.kind == kind:
                    results.append(node)
        return results

    def get_file_nodes(self, file_path: str) -> List[GraphNode]:
        """Get all nodes defined in a specific file."""
        return [n for n in self.nodes.values() if n.file_path == file_path]

    def to_context_string(self, max_tokens: int = 2000) -> str:
        """Generate a compact context string for LLM consumption.

        Similar to Aider's repo-map: shows file structure + key symbols.
        """
        lines = [f"# Codebase Graph: {os.path.basename(self.workspace_path)}"]
        lines.append(f"# {self.node_count} nodes, {self.edge_count} edges, "
                     f"{self.file_count} files")
        lines.append("")

        # Group by file.
        by_file: Dict[str, List[GraphNode]] = {}
        for node in self.nodes.values():
            if node.kind != "file":
                by_file.setdefault(node.file_path, []).append(node)

        for fp, nodes in sorted(by_file.items()):
            rel_path = os.path.relpath(fp, self.workspace_path) if fp else "unknown"
            lines.append(f"## {rel_path}")
            for n in sorted(nodes, key=lambda x: x.line_start):
                prefix = "  " if n.kind in ("method",) else ""
                sig = f"({n.signature})" if n.signature else ""
                lines.append(f"{prefix}- {n.kind}: {n.name}{sig} L{n.line_start}")
            lines.append("")

            # Rough token estimate (4 chars per token).
            if len("\n".join(lines)) // 4 > max_tokens:
                lines.append(f"... ({self.node_count - len(lines)} more nodes)")
                break

        return "\n".join(lines)

    def to_json(self) -> dict:
        """Serialize for storage."""
        return {
            "workspace_path": self.workspace_path,
            "indexed_at": self.indexed_at,
            "file_count": self.file_count,
            "language_stats": self.language_stats,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": [
                {"source": e.source, "target": e.target,
                 "kind": e.kind, "confidence": e.confidence}
                for e in self.edges
            ],
        }


# ============================================================================
# File Type Detection
# ============================================================================

_LANGUAGE_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
    ".cpp": "cpp", ".c": "c", ".h": "c", ".hpp": "cpp",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".rb": "ruby",
    ".php": "php", ".swift": "swift", ".kt": "kotlin",
    ".scala": "scala", ".r": "r", ".lua": "lua",
    ".sh": "bash", ".sql": "sql", ".md": "markdown",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".xml": "xml", ".html": "html",
    ".css": "css", ".scss": "scss",
}

_IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target", "vendor",
    ".tox", ".mypy_cache", ".pytest_cache", "coverage",
    ".eggs", "*.egg-info",
}


def _should_index(path: Path) -> bool:
    """Check if a file should be indexed."""
    # Skip hidden and ignored dirs.
    for part in path.parts:
        if part.startswith(".") and part != ".":
            return False
        if part in _IGNORE_DIRS:
            return False
    # Check extension.
    return path.suffix.lower() in _LANGUAGE_MAP


# ============================================================================
# Built-in Regex Parser (Fallback — always works, zero deps)
# ============================================================================

# Regex patterns for extracting definitions (language-aware).
_PATTERNS = {
    "python": {
        "class": re.compile(r"^class\s+(\w+)\s*[\(:]", re.MULTILINE),
        "function": re.compile(r"^def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE),
        "import": re.compile(r"^(?:from\s+(\S+)\s+)?import\s+(.+)", re.MULTILINE),
    },
    "javascript": {
        "class": re.compile(r"class\s+(\w+)", re.MULTILINE),
        "function": re.compile(
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)|"
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?",
            re.MULTILINE,
        ),
        "import": re.compile(
            r"import\s+(?:\{[^}]+\}|\w+)\s+from\s+['\"]([^'\"]+)['\"]|"
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            re.MULTILINE,
        ),
    },
    "typescript": None,  # Reuse javascript patterns.
    "cpp": {
        "class": re.compile(r"class\s+(\w+)", re.MULTILINE),
        "function": re.compile(
            r"(?:\w[\w:*&<>,\s]*)\s+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*\{",
            re.MULTILINE,
        ),
        "import": re.compile(r'#include\s*[<"]([^>"]+)[>"]', re.MULTILINE),
    },
}
_PATTERNS["typescript"] = _PATTERNS["javascript"]
_PATTERNS["c"] = _PATTERNS["cpp"]


def _parse_file_regex(file_path: Path, language: str) -> List[GraphNode]:
    """Extract symbols from a file using regex patterns."""
    nodes = []
    patterns = _PATTERNS.get(language)
    if not patterns:
        return nodes

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return nodes

    lines = content.split("\n")

    # Extract classes.
    for match in patterns.get("class", re.compile(r"$^")).finditer(content):
        name = match.group(1)
        line = content[:match.start()].count("\n") + 1
        nodes.append(GraphNode(
            id=f"{file_path}:{name}",
            name=name,
            kind="class",
            file_path=str(file_path),
            line_start=line,
            language=language,
        ))

    # Extract functions.
    for match in patterns.get("function", re.compile(r"$^")).finditer(content):
        name = match.group(1) or (match.group(3) if match.lastindex >= 3 else None)
        if not name or name.startswith("_") and name != "__init__":
            continue
        sig = match.group(2) if match.lastindex >= 2 and match.group(2) else ""
        line = content[:match.start()].count("\n") + 1
        nodes.append(GraphNode(
            id=f"{file_path}:{name}",
            name=name,
            kind="function",
            file_path=str(file_path),
            line_start=line,
            language=language,
            signature=sig[:100],  # Truncate long signatures.
        ))

    return nodes


def _extract_imports_regex(file_path: Path, language: str) -> List[str]:
    """Extract import targets from a file."""
    patterns = _PATTERNS.get(language)
    if not patterns or "import" not in patterns:
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    imports = []
    for match in patterns["import"].finditer(content):
        for group in match.groups():
            if group:
                imports.append(group.strip())
    return imports


# ============================================================================
# Codebase Graph Manager
# ============================================================================

class CodebaseGraphManager:
    """Manages codebase knowledge graphs for workspaces.

    Supports multiple workspaces simultaneously.
    Persists graphs to disk for fast reload.
    """

    def __init__(self, cache_dir: str = None):
        self._graphs: Dict[str, CodebaseGraph] = {}
        self._cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".hermes", "graph_cache"
        )
        os.makedirs(self._cache_dir, exist_ok=True)

    def index_workspace(
        self,
        workspace_path: str,
        force: bool = False,
        use_graphify: bool = True,
    ) -> CodebaseGraph:
        """Index a workspace into a knowledge graph.

        Args:
            workspace_path: Absolute path to the project root.
            force: Re-index even if cached.
            use_graphify: Try Graphify first (full AST + MCP).

        Returns:
            CodebaseGraph ready for querying.
        """
        workspace_path = os.path.abspath(workspace_path)

        # Check cache.
        if not force and workspace_path in self._graphs:
            cached = self._graphs[workspace_path]
            # Re-index if older than 1 hour.
            if time.time() - cached.indexed_at < 3600:
                return cached

        # Try loading from disk cache.
        cache_file = self._cache_path(workspace_path)
        if not force and os.path.exists(cache_file):
            try:
                graph = self._load_cache(cache_file)
                if graph and time.time() - graph.indexed_at < 3600:
                    self._graphs[workspace_path] = graph
                    return graph
            except Exception:
                pass

        # Try Graphify first (best quality).
        if use_graphify:
            graph = self._try_graphify(workspace_path)
            if graph:
                self._graphs[workspace_path] = graph
                self._save_cache(cache_file, graph)
                return graph

        # Fallback: built-in regex parser.
        graph = self._index_regex(workspace_path)
        self._graphs[workspace_path] = graph
        self._save_cache(cache_file, graph)
        return graph

    def get_graph(self, workspace_path: str) -> Optional[CodebaseGraph]:
        """Get an existing graph (or None if not indexed)."""
        return self._graphs.get(os.path.abspath(workspace_path))

    def query(self, workspace_path: str, question: str) -> str:
        """Query the graph with natural language. Returns context string."""
        graph = self.get_graph(workspace_path)
        if not graph:
            return "Workspace not indexed. Call index_workspace first."

        # Simple keyword extraction from question.
        words = re.findall(r'\b\w{3,}\b', question)
        relevant_nodes = []
        for word in words:
            results = graph.search_nodes(word)
            relevant_nodes.extend(results[:3])

        if not relevant_nodes:
            return graph.to_context_string(max_tokens=1000)

        # Build focused context.
        lines = [f"# Relevant code for: {question}\n"]
        seen = set()
        for node in relevant_nodes[:10]:
            if node.id in seen:
                continue
            seen.add(node.id)
            lines.append(f"- **{node.kind}** `{node.name}` in `{os.path.basename(node.file_path)}` L{node.line_start}")
            if node.signature:
                lines.append(f"  Signature: `{node.signature}`")

            # Add neighbors.
            neighbors = graph.get_neighbors(node.id)
            if neighbors:
                for n_node, n_edge in neighbors[:5]:
                    lines.append(f"  -> {n_edge.kind} `{n_node.name}` ({n_node.kind})")

        return "\n".join(lines)

    def get_context_for_file(self, workspace_path: str, file_path: str) -> str:
        """Get graph context relevant to a specific file.

        Used by the graph engine's execute node to auto-include
        related code when the agent is editing a file.
        """
        graph = self.get_graph(workspace_path)
        if not graph:
            return ""

        file_nodes = graph.get_file_nodes(file_path)
        if not file_nodes:
            return ""

        lines = [f"# Related context for {os.path.basename(file_path)}\n"]
        for node in file_nodes[:20]:
            lines.append(f"- {node.kind}: {node.name}")
            neighbors = graph.get_neighbors(node.id, direction="both")
            for n_node, n_edge in neighbors[:3]:
                if n_node.file_path != file_path:
                    rel = os.path.relpath(n_node.file_path, workspace_path) if n_node.file_path else "?"
                    lines.append(f"  {n_edge.kind} -> {n_node.name} ({rel})")

        return "\n".join(lines)

    # ----------------------------------------------------------------
    # Graphify Integration
    # ----------------------------------------------------------------

    def _try_graphify(self, workspace_path: str) -> Optional[CodebaseGraph]:
        """Try using Graphify for high-quality graph generation."""
        try:
            import subprocess
            # Check if graphify is available.
            result = subprocess.run(
                ["graphify", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None

            # Check if graph.json already exists.
            graph_json = os.path.join(workspace_path, "graphify-out", "graph.json")
            if os.path.exists(graph_json):
                return self._load_graphify_json(workspace_path, graph_json)

            # Generate the graph (Pass 1 only — deterministic, no LLM cost).
            logger.info("Running Graphify on %s (Pass 1, deterministic)...", workspace_path)
            result = subprocess.run(
                ["graphify", workspace_path, "--pass", "1"],
                capture_output=True, text=True, timeout=300,
                cwd=workspace_path,
            )

            if os.path.exists(graph_json):
                return self._load_graphify_json(workspace_path, graph_json)

        except (FileNotFoundError, ImportError):
            logger.debug("Graphify not installed — using regex fallback")
        except Exception as e:
            logger.debug("Graphify failed: %s — using regex fallback", e)

        return None

    def _load_graphify_json(self, workspace_path: str, json_path: str) -> CodebaseGraph:
        """Load a Graphify-generated graph.json into our CodebaseGraph."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        graph = CodebaseGraph(
            workspace_path=workspace_path,
            indexed_at=time.time(),
        )

        # Parse Graphify nodes.
        for node_data in data.get("nodes", []):
            node_id = node_data.get("id", "")
            graph.nodes[node_id] = GraphNode(
                id=node_id,
                name=node_data.get("name", node_data.get("label", "")),
                kind=node_data.get("type", "unknown").lower(),
                file_path=node_data.get("file_path", ""),
                line_start=node_data.get("line", 0),
                language=node_data.get("language", ""),
                signature=node_data.get("signature", ""),
                docstring=node_data.get("docstring", ""),
            )

        # Parse Graphify edges.
        for edge_data in data.get("edges", []):
            graph.edges.append(GraphEdge(
                source=edge_data.get("source", ""),
                target=edge_data.get("target", ""),
                kind=edge_data.get("type", "unknown").lower(),
                confidence=edge_data.get("confidence", "EXTRACTED"),
            ))

        graph.file_count = len(set(n.file_path for n in graph.nodes.values() if n.file_path))
        logger.info("Loaded Graphify graph: %d nodes, %d edges", graph.node_count, graph.edge_count)
        return graph

    # ----------------------------------------------------------------
    # Built-in Regex Parser
    # ----------------------------------------------------------------

    def _index_regex(self, workspace_path: str) -> CodebaseGraph:
        """Build a graph using regex-based symbol extraction."""
        graph = CodebaseGraph(
            workspace_path=workspace_path,
            indexed_at=time.time(),
        )

        root = Path(workspace_path)
        files_indexed = 0

        for path in root.rglob("*"):
            if not path.is_file() or not _should_index(path):
                continue

            language = _LANGUAGE_MAP.get(path.suffix.lower(), "")
            if not language:
                continue

            # Count language stats.
            graph.language_stats[language] = graph.language_stats.get(language, 0) + 1

            # Add file node.
            file_id = str(path)
            graph.nodes[file_id] = GraphNode(
                id=file_id,
                name=path.name,
                kind="file",
                file_path=str(path),
                language=language,
            )

            # Extract symbols.
            symbols = _parse_file_regex(path, language)
            for sym in symbols:
                graph.nodes[sym.id] = sym

                # Edge: file defines symbol.
                graph.edges.append(GraphEdge(
                    source=file_id,
                    target=sym.id,
                    kind="defines",
                    confidence="EXTRACTED",
                ))

            # Extract imports.
            imports = _extract_imports_regex(path, language)
            for imp in imports:
                graph.edges.append(GraphEdge(
                    source=file_id,
                    target=f"import:{imp}",
                    kind="imports",
                    confidence="EXTRACTED",
                ))

            files_indexed += 1

        graph.file_count = files_indexed
        logger.info(
            "Regex index complete: %d files, %d nodes, %d edges",
            files_indexed, graph.node_count, graph.edge_count,
        )
        return graph

    # ----------------------------------------------------------------
    # Caching
    # ----------------------------------------------------------------

    def _cache_path(self, workspace_path: str) -> str:
        """Get cache file path for a workspace."""
        import hashlib
        h = hashlib.sha256(workspace_path.encode()).hexdigest()[:12]
        return os.path.join(self._cache_dir, f"graph_{h}.json")

    def _save_cache(self, cache_file: str, graph: CodebaseGraph) -> None:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(graph.to_json(), f)
        except Exception as e:
            logger.debug("Cache save failed: %s", e)

    def _load_cache(self, cache_file: str) -> Optional[CodebaseGraph]:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            graph = CodebaseGraph(
                workspace_path=data["workspace_path"],
                indexed_at=data["indexed_at"],
                file_count=data["file_count"],
                language_stats=data.get("language_stats", {}),
            )
            for nid, ndata in data.get("nodes", {}).items():
                graph.nodes[nid] = GraphNode(**ndata)
            for edata in data.get("edges", []):
                graph.edges.append(GraphEdge(**edata))
            return graph
        except Exception:
            return None


# ============================================================================
# Singleton
# ============================================================================

_manager: Optional[CodebaseGraphManager] = None


def get_graph_manager() -> CodebaseGraphManager:
    """Get or create the global graph manager."""
    global _manager
    if _manager is None:
        _manager = CodebaseGraphManager()
    return _manager
