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

import ast
import hashlib
import json
import logging
import os
import re
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
    backend: str = "regex"
    warnings: List[str] = field(default_factory=list)
    file_mtimes: Dict[str, float] = field(default_factory=dict)

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
                     f"{self.file_count} files ({self.backend})")
        if self.warnings:
            lines.append("# Warnings:")
            for warning in self.warnings:
                lines.append(f"#   {warning}")
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
            "backend": self.backend,
            "warnings": list(self.warnings or []),
            "file_mtimes": dict(self.file_mtimes or {}),
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


def _parse_file_python_ast(file_path: Path) -> tuple[List[GraphNode], List[str]]:
    """Extract symbols and imports from a Python file via the stdlib AST."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
    except Exception:
        return [], []

    nodes: List[GraphNode] = []
    imports: List[str] = []
    path_str = str(file_path)

    for item in ast.walk(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = item.name
            if name.startswith("_") and name != "__init__":
                continue
            args = []
            try:
                args = [a.arg for a in item.args.args]
            except Exception:
                args = []
            nodes.append(GraphNode(
                id=f"{path_str}:{name}",
                name=name,
                kind="function",
                file_path=path_str,
                line_start=getattr(item, "lineno", 0),
                language="python",
                signature=", ".join(args)[:100],
            ))
        elif isinstance(item, ast.ClassDef):
            nodes.append(GraphNode(
                id=f"{path_str}:{item.name}",
                name=item.name,
                kind="class",
                file_path=path_str,
                line_start=getattr(item, "lineno", 0),
                language="python",
            ))
        elif isinstance(item, ast.Import):
            for alias in item.names:
                if alias.name:
                    imports.append(alias.name)
        elif isinstance(item, ast.ImportFrom) and item.module:
            imports.append(item.module)

    return nodes, imports


def _parse_file_treesitter(file_path: Path, language: str) -> Optional[tuple[List[GraphNode], List[str]]]:
    """Optional tree-sitter parse. Returns None when the grammar is missing."""
    lang_mod = None
    try:
        if language == "python":
            import tree_sitter_python as lang_mod
        elif language in ("javascript", "typescript"):
            import tree_sitter_javascript as lang_mod
        else:
            return None
        import tree_sitter
    except ImportError:
        return None

    try:
        parser = tree_sitter.Parser(tree_sitter.Language(lang_mod.language()))
        source = file_path.read_bytes()
        tree = parser.parse(source)
    except Exception:
        return None

    text = source.decode("utf-8", errors="replace")
    nodes: List[GraphNode] = []
    imports: List[str] = []
    path_str = str(file_path)

    def _node_text(node: Any) -> str:
        return text[node.start_byte:node.end_byte]

    def _walk(node: Any) -> None:
        kind = node.type
        if kind in ("function_definition", "function_declaration", "method_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(name_node)
                if name and not (name.startswith("_") and name != "__init__"):
                    nodes.append(GraphNode(
                        id=f"{path_str}:{name}",
                        name=name,
                        kind="function",
                        file_path=path_str,
                        line_start=node.start_point[0] + 1,
                        language=language,
                    ))
        elif kind in ("class_definition", "class_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _node_text(name_node)
                nodes.append(GraphNode(
                    id=f"{path_str}:{name}",
                    name=name,
                    kind="class",
                    file_path=path_str,
                    line_start=node.start_point[0] + 1,
                    language=language,
                ))
        elif kind in ("import_statement", "import_from_statement"):
            imports.append(_node_text(node)[:200])
        for child in node.children:
            _walk(child)

    _walk(tree.root_node)
    return nodes, imports


def _parse_file(file_path: Path, language: str) -> tuple[List[GraphNode], List[str], str]:
    """Parse one file. Prefer tree-sitter, then Python AST, then regex."""
    ts = _parse_file_treesitter(file_path, language)
    if ts is not None:
        return ts[0], ts[1], "treesitter"
    if language == "python":
        nodes, imports = _parse_file_python_ast(file_path)
        if nodes or imports:
            return nodes, imports, "ast"
    return (
        _parse_file_regex(file_path, language),
        _extract_imports_regex(file_path, language),
        "regex",
    )


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "what", "how",
    "why", "when", "where", "does", "into", "code", "file", "class",
    "function", "please", "just", "need", "want", "make", "call",
    "calls", "fix", "bug", "error", "add", "you", "can",
}

_FILE_IN_PROMPT_RE = re.compile(
    r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|cpp|c|h|rb|php)\b",
    re.IGNORECASE,
)
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
_ACTIVE_FILE_RE = re.compile(r"Active file:\s+(\S+)")


def extract_query_terms(question: str) -> List[str]:
    """Identifiers and file paths worth looking up in the graph."""
    seen: Set[str] = set()
    terms: List[str] = []
    for term in _FILE_IN_PROMPT_RE.findall(question) + _IDENT_RE.findall(question):
        key = term.lower()
        if key in _STOPWORDS or key in seen:
            continue
        seen.add(key)
        terms.append(term)
    return terms


def active_file_from_prompt(prompt: str) -> str:
    """Editor sidecar line: ``Active file: path``."""
    match = _ACTIVE_FILE_RE.search(prompt or "")
    return match.group(1) if match else ""


def _pick_backend(used: Set[str]) -> str:
    if "treesitter" in used:
        return "treesitter"
    if "ast" in used:
        return "ast"
    return "regex"


def _backend_rank_value(parser: str) -> int:
    if parser == "treesitter":
        return 3
    if parser == "ast":
        return 2
    if parser == "regex":
        return 1
    return 0


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

        if not force and workspace_path in self._graphs:
            cached = self._graphs[workspace_path]
            self._refresh_stale_files(cached)
            return cached

        cache_file = self._cache_path(workspace_path)
        if not force and os.path.exists(cache_file):
            try:
                graph = self._load_cache(cache_file)
                if graph:
                    self._graphs[workspace_path] = graph
                    self._refresh_stale_files(graph)
                    return graph
            except Exception:
                pass

        warnings: List[str] = []
        if use_graphify:
            graph, warnings = self._try_graphify(workspace_path)
            if graph:
                graph.warnings = list(warnings)
                self._stamp_mtimes(graph)
                self._graphs[workspace_path] = graph
                self._save_cache(cache_file, graph)
                return graph

        graph = self._index_builtin(workspace_path)
        graph.warnings = list(warnings)
        self._graphs[workspace_path] = graph
        self._save_cache(cache_file, graph)
        return graph

    def get_graph(self, workspace_path: str) -> Optional[CodebaseGraph]:
        """Get an existing graph (or None if not indexed)."""
        return self._graphs.get(os.path.abspath(workspace_path))

    def query(self, workspace_path: str, question: str) -> str:
        """Query the graph with natural language. Returns focused context."""
        return self.retrieve_context(workspace_path, question)

    def retrieve_context(
        self,
        workspace_path: str,
        question: str,
        active_file: str = "",
        max_tokens: int = 2000,
    ) -> str:
        """Retrieve neighbors of mentioned symbols and the active file.

        Does not dump the full repo map when anything matches.
        """
        graph = self.get_graph(workspace_path)
        if not graph:
            return "Workspace not indexed. Call index_workspace first."

        if not active_file:
            active_file = active_file_from_prompt(question)

        lines: List[str] = [f"# Relevant code for: {question[:120]}\n"]
        budget_chars = max_tokens * 4
        seen: Set[str] = set()
        matched_symbols = 0
        file_ctx = ""

        if active_file:
            abs_file = (
                active_file
                if os.path.isabs(active_file)
                else os.path.join(workspace_path, active_file)
            )
            file_ctx = self.get_context_for_file(workspace_path, os.path.abspath(abs_file))
            if file_ctx:
                lines.append(file_ctx)
                seen.add(os.path.abspath(abs_file))

        terms = extract_query_terms(question)
        ranked: List[GraphNode] = []
        for term in terms:
            exact = [n for n in graph.nodes.values() if n.name.lower() == term.lower()]
            if exact:
                ranked.extend(exact)
                continue
            ranked.extend(graph.search_nodes(re.escape(term))[:5])

        for node in ranked[:12]:
            if node.id in seen:
                continue
            seen.add(node.id)
            matched_symbols += 1
            rel = (
                os.path.relpath(node.file_path, workspace_path)
                if node.file_path
                else "?"
            )
            lines.append(
                f"- **{node.kind}** `{node.name}` in `{rel}` L{node.line_start}"
            )
            if node.signature:
                lines.append(f"  Signature: `{node.signature}`")
            for n_node, n_edge in graph.get_neighbors(node.id)[:5]:
                lines.append(f"  -> {n_edge.kind} `{n_node.name}` ({n_node.kind})")

        body = "\n".join(lines)
        if matched_symbols == 0 and not file_ctx:
            # Nothing matched — file names only, not a full symbol dump.
            file_names = [
                os.path.relpath(n.file_path, workspace_path)
                for n in graph.nodes.values()
                if n.kind == "file" and n.file_path
            ]
            preview = "\n".join(f"- {name}" for name in sorted(file_names)[:40])
            body = (
                f"# Files in {os.path.basename(workspace_path)} "
                f"({graph.backend}, {graph.file_count} files)\n{preview}"
            )

        if len(body) > budget_chars:
            return body[:budget_chars] + "\n..."
        return body

    def index_file(self, workspace_path: str, file_path: str) -> Optional[CodebaseGraph]:
        """Re-parse a single file into the in-memory graph."""
        workspace_path = os.path.abspath(workspace_path)
        file_path = os.path.abspath(file_path)
        graph = self.get_graph(workspace_path)
        if graph is None:
            graph = self.index_workspace(workspace_path)
        if not _should_index(Path(file_path)):
            return graph

        self._drop_file_nodes(graph, file_path)
        language = _LANGUAGE_MAP.get(Path(file_path).suffix.lower(), "")
        if not language:
            return graph

        path = Path(file_path)
        graph.nodes[file_path] = GraphNode(
            id=file_path,
            name=path.name,
            kind="file",
            file_path=file_path,
            language=language,
        )
        symbols, imports, parser = _parse_file(path, language)
        if _backend_rank_value(parser) > _backend_rank_value(graph.backend):
            graph.backend = parser
        for sym in symbols:
            graph.nodes[sym.id] = sym
            graph.edges.append(GraphEdge(
                source=file_path,
                target=sym.id,
                kind="defines",
                confidence="EXTRACTED",
            ))
        for imp in imports:
            graph.edges.append(GraphEdge(
                source=file_path,
                target=f"import:{imp}",
                kind="imports",
                confidence="EXTRACTED",
            ))
        try:
            graph.file_mtimes[file_path] = os.path.getmtime(file_path)
        except OSError:
            pass
        graph.indexed_at = time.time()
        graph.file_count = len({n.file_path for n in graph.nodes.values() if n.kind == "file"})
        self._save_cache(self._cache_path(workspace_path), graph)
        return graph

    def graph_status(self, workspace_path: str) -> dict:
        """Payload for the composer chip and GET /api/graph/status."""
        workspace_path = os.path.abspath(workspace_path) if workspace_path else ""
        graph = self.get_graph(workspace_path) if workspace_path else None
        if not graph:
            return {
                "indexed": False,
                "backend": "none",
                "nodes": 0,
                "edges": 0,
                "files": 0,
                "warnings": [],
                "indexed_at": 0,
                "stale": True,
                "degraded": False,
            }
        stale = self._is_stale(graph)
        return {
            "indexed": True,
            "backend": graph.backend,
            "nodes": graph.node_count,
            "edges": graph.edge_count,
            "files": graph.file_count,
            "warnings": list(graph.warnings or []),
            "indexed_at": graph.indexed_at,
            "stale": stale,
            "degraded": graph.backend == "regex",
        }

    def _drop_file_nodes(self, graph: CodebaseGraph, file_path: str) -> None:
        drop_ids = {
            nid for nid, node in graph.nodes.items()
            if node.file_path == file_path or nid == file_path
        }
        for nid in drop_ids:
            graph.nodes.pop(nid, None)
        graph.edges = [
            edge for edge in graph.edges
            if edge.source not in drop_ids and edge.target not in drop_ids
        ]
        graph.file_mtimes.pop(file_path, None)

    def _stamp_mtimes(self, graph: CodebaseGraph) -> None:
        for node in graph.nodes.values():
            if node.kind != "file" or not node.file_path:
                continue
            try:
                graph.file_mtimes[node.file_path] = os.path.getmtime(node.file_path)
            except OSError:
                pass

    def _is_stale(self, graph: CodebaseGraph) -> bool:
        checked = 0
        for path, stamped in list(graph.file_mtimes.items())[:80]:
            try:
                if os.path.getmtime(path) - stamped > 1.0:
                    return True
            except OSError:
                continue
            checked += 1
        return False

    def _refresh_stale_files(self, graph: CodebaseGraph) -> None:
        stale_paths: List[str] = []
        for path, stamped in list(graph.file_mtimes.items()):
            try:
                if os.path.getmtime(path) - stamped > 1.0:
                    stale_paths.append(path)
            except OSError:
                continue
            if len(stale_paths) >= 20:
                break
        for path in stale_paths:
            self.index_file(graph.workspace_path, path)

    def graph_context_for_turn(
        self,
        workspace_path: str,
        prompt: str,
        active_file: str = "",
        max_tokens: int = 2000,
    ) -> tuple[str, List[str], dict]:
        """Index if needed, then retrieve. Returns (context, warnings, status)."""
        workspace_path = os.path.abspath(workspace_path)
        graph = self.get_graph(workspace_path)
        if graph is None:
            graph = self.index_workspace(workspace_path)
        status = self.graph_status(workspace_path)
        warnings = list(getattr(graph, "warnings", []) or [])
        context = self.retrieve_context(
            workspace_path,
            prompt,
            active_file=active_file,
            max_tokens=max_tokens,
        )
        return context, warnings, status

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

    def _try_graphify(self, workspace_path: str) -> tuple[Optional[CodebaseGraph], List[str]]:
        """Try using Graphify for high-quality graph generation.

        Failures are warnings, never silent. The caller falls back to regex
        and surfaces ``warnings`` on the returned graph and in API JSON.
        """
        warnings: List[str] = []
        try:
            import subprocess
            result = subprocess.run(
                ["graphify", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                msg = (result.stderr or result.stdout or "graphify --version failed").strip()
                warnings.append(f"Graphify version check failed: {msg}")
                logger.warning("Graphify not usable: %s", msg)
                return None, warnings

            graph_json = os.path.join(workspace_path, "graphify-out", "graph.json")
            if os.path.exists(graph_json):
                graph = self._load_graphify_json(workspace_path, graph_json)
                graph.backend = "graphify"
                return graph, warnings

            logger.info("Running Graphify on %s (Pass 1, deterministic)...", workspace_path)
            result = subprocess.run(
                ["graphify", workspace_path, "--pass", "1"],
                capture_output=True, text=True, timeout=300,
                cwd=workspace_path,
            )

            if os.path.exists(graph_json):
                graph = self._load_graphify_json(workspace_path, graph_json)
                graph.backend = "graphify"
                if result.returncode != 0:
                    extra = (result.stderr or result.stdout or "").strip()
                    if extra:
                        warnings.append(f"Graphify exited {result.returncode}: {extra[:500]}")
                        logger.warning("Graphify produced graph.json with non-zero exit: %s", extra[:500])
                return graph, warnings

            extra = (result.stderr or result.stdout or "no graph.json").strip()
            warnings.append(f"Graphify produced no graph.json: {extra[:500]}")
            logger.warning("Graphify produced no graph.json for %s: %s", workspace_path, extra[:500])

        except FileNotFoundError:
            warnings.append("Graphify not installed — using regex fallback")
            logger.warning("Graphify not installed — using regex fallback")
        except ImportError:
            warnings.append("Graphify unavailable (subprocess import failed) — using regex fallback")
            logger.warning("Graphify unavailable — using regex fallback")
        except Exception as e:
            warnings.append(f"Graphify failed: {e}")
            logger.warning("Graphify failed: %s — using regex fallback", e)

        return None, warnings

    def _load_graphify_json(self, workspace_path: str, json_path: str) -> CodebaseGraph:
        """Load a Graphify-generated graph.json into our CodebaseGraph."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        graph = CodebaseGraph(
            workspace_path=workspace_path,
            indexed_at=time.time(),
            backend="graphify",
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

    def _index_builtin(self, workspace_path: str) -> CodebaseGraph:
        """Build a graph using tree-sitter, Python AST, then regex."""
        graph = CodebaseGraph(
            workspace_path=workspace_path,
            indexed_at=time.time(),
            backend="regex",
        )

        root = Path(workspace_path)
        files_indexed = 0
        used: Set[str] = set()

        for path in root.rglob("*"):
            if not path.is_file() or not _should_index(path):
                continue

            language = _LANGUAGE_MAP.get(path.suffix.lower(), "")
            if not language:
                continue

            graph.language_stats[language] = graph.language_stats.get(language, 0) + 1

            file_id = str(path)
            graph.nodes[file_id] = GraphNode(
                id=file_id,
                name=path.name,
                kind="file",
                file_path=file_id,
                language=language,
            )

            symbols, imports, parser = _parse_file(path, language)
            used.add(parser)
            for sym in symbols:
                graph.nodes[sym.id] = sym
                graph.edges.append(GraphEdge(
                    source=file_id,
                    target=sym.id,
                    kind="defines",
                    confidence="EXTRACTED",
                ))

            for imp in imports:
                graph.edges.append(GraphEdge(
                    source=file_id,
                    target=f"import:{imp}",
                    kind="imports",
                    confidence="EXTRACTED",
                ))

            try:
                graph.file_mtimes[file_id] = os.path.getmtime(file_id)
            except OSError:
                pass

            files_indexed += 1

        graph.file_count = files_indexed
        graph.backend = _pick_backend(used)
        logger.info(
            "Builtin index complete: %d files, %d nodes, %d edges (%s)",
            files_indexed, graph.node_count, graph.edge_count, graph.backend,
        )
        return graph

    def _index_regex(self, workspace_path: str) -> CodebaseGraph:
        """Back-compat alias used by tests that patch the builtin indexer."""
        return self._index_builtin(workspace_path)

    # ----------------------------------------------------------------
    # Caching
    # ----------------------------------------------------------------

    def _cache_path(self, workspace_path: str) -> str:
        """Get cache file path for a workspace."""
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
                backend=data.get("backend", "regex"),
                warnings=list(data.get("warnings") or []),
                file_mtimes=dict(data.get("file_mtimes") or {}),
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
