"""Ghost completion is a cheap LLM call — no agent tools, never persisted."""

from __future__ import annotations

import inspect

from gateway.ide_features import (
    clear_ghost_cache_for_tests,
    run_ghost_completion,
)
from hermes_cli.web_routers import ide as ide_routes


def setup_function():
    clear_ghost_cache_for_tests()


def test_ghost_completion_uses_oneshot_not_session_prompt(monkeypatch):
    captured = {}

    def fake_oneshot(**kwargs):
        captured.update(kwargs)
        return "foo()\nbar()"

    monkeypatch.setattr("agent.oneshot.run_oneshot", fake_oneshot)
    monkeypatch.setattr("gateway.ide_features.find_live_session", lambda _sid: None)

    text = run_ghost_completion(
        {"prefix": "def foo", "filePath": "a.py", "suffix": "\n"}
    )
    assert text == "foo()\nbar()"
    assert captured["max_tokens"] == 80
    assert captured["timeout"] == 5.0
    assert "tools" not in captured


def test_ghost_cache_hits_same_prefix(monkeypatch):
    calls = {"n": 0}

    def fake_oneshot(**_kwargs):
        calls["n"] += 1
        return "next_line"

    monkeypatch.setattr("agent.oneshot.run_oneshot", fake_oneshot)
    data = {"prefix": "abc", "filePath": "x.ts", "suffix": ""}
    assert run_ghost_completion(data) == "next_line"
    assert run_ghost_completion(data) == "next_line"
    assert calls["n"] == 1


def test_dashboard_ghost_route_does_not_spin_agent():
    source = inspect.getsource(ide_routes.ghost_completion)
    assert "run_ghost_completion_async" in source
    assert "_ide_turn" not in source
    assert "run_session_prompt" not in source
    assert "persist" not in source


def test_dashboard_inline_edit_busy_is_409():
    source = inspect.getsource(ide_routes.inline_edit)
    assert 'status_code=409' in source
    assert "busy" in source.lower()


def test_busy_persist_does_not_block_ghost(monkeypatch):
    """A live busy session must not 409 ghost text (ghost is not a turn)."""
    monkeypatch.setattr("agent.oneshot.run_oneshot", lambda **_k: "x")
    monkeypatch.setattr(
        "gateway.ide_features.find_live_session",
        lambda _sid: {"running": True, "agent": object()},
    )
    assert run_ghost_completion({"prefix": "a", "filePath": "a.py"}) == "x"
