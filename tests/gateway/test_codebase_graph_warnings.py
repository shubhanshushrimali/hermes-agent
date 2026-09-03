"""Retrieve by symbol, incremental index, and Graphify warnings."""

from gateway.codebase_graph import CodebaseGraphManager, extract_query_terms


def test_graphify_failure_surfaces_on_regex_graph(tmp_path, monkeypatch):
    manager = CodebaseGraphManager(cache_dir=str(tmp_path / "cache"))
    (tmp_path / "main.py").write_text("def hello():\n    return 1\n")

    def boom(_workspace):
        return None, ["Graphify failed: boom"]

    monkeypatch.setattr(manager, "_try_graphify", boom)
    graph = manager.index_workspace(str(tmp_path), force=True)
    assert graph.backend in ("regex", "ast", "treesitter")
    assert any("Graphify failed" in w for w in graph.warnings)
    dumped = graph.to_json()
    assert dumped["warnings"]


def test_retrieve_hits_symbol_neighbors_not_full_map(tmp_path, monkeypatch):
    manager = CodebaseGraphManager(cache_dir=str(tmp_path / "cache"))
    (tmp_path / "auth.py").write_text(
        "class AuthService:\n    def login(self):\n        return True\n"
    )
    (tmp_path / "db.py").write_text(
        "class DatabaseClient:\n    def connect(self):\n        return 1\n"
    )
    monkeypatch.setattr(manager, "_try_graphify", lambda _ws: (None, []))
    manager.index_workspace(str(tmp_path), force=True)

    ctx = manager.retrieve_context(str(tmp_path), "Fix AuthService login")
    assert "AuthService" in ctx
    assert "## db.py" not in ctx
    assert "DatabaseClient" not in ctx or "AuthService" in ctx


def test_incremental_index_replaces_one_file(tmp_path, monkeypatch):
    manager = CodebaseGraphManager(cache_dir=str(tmp_path / "cache"))
    target = tmp_path / "mod.py"
    target.write_text("def alpha():\n    return 1\n")
    monkeypatch.setattr(manager, "_try_graphify", lambda _ws: (None, []))
    manager.index_workspace(str(tmp_path), force=True)
    assert manager.get_graph(str(tmp_path)).search_nodes("alpha")

    target.write_text("def beta():\n    return 2\n")
    manager.index_file(str(tmp_path), str(target))
    graph = manager.get_graph(str(tmp_path))
    names = {n.name for n in graph.nodes.values() if n.kind == "function"}
    assert "beta" in names
    assert "alpha" not in names


def test_extract_query_terms_skips_stopwords():
    terms = extract_query_terms("Please fix the AuthService in auth.py for me")
    assert "AuthService" in terms
    assert "auth.py" in terms
    assert "the" not in terms
    assert "please" not in {t.lower() for t in terms}
