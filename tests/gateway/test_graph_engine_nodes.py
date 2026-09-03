"""Graph engine execute/validate/model routing without running the agent."""

import subprocess

from gateway.graph_engine import ModelRouter, node_execute, node_validate


class _OpenBudget:
    def check_budget(self):
        return True


class _ClosedBudget:
    def check_budget(self):
        return False


def test_model_router_prefers_session_model():
    router = ModelRouter(budget=_OpenBudget())
    assert router.get_model("code", fallback="openai/gpt-4.1") == "openai/gpt-4.1"
    assert router.get_model("code") == ""


def test_model_router_budget_exhausted_stays_local():
    router = ModelRouter(budget=_ClosedBudget())
    assert router.get_model("code", fallback="anthropic/claude-sonnet-4-20250514") == "ollama/llama3.2:3b"
    assert router.get_model("code", fallback="ollama/llama3.2:3b") == "ollama/llama3.2:3b"


def test_validate_skips_without_code_changes(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("must not run tests")

    monkeypatch.setattr(subprocess, "run", boom)
    result = node_validate({
        "agent_response": "done",
        "code_changes": [],
        "intent": "code",
        "workspace_path": ".",
        "verify_commands": ["python -m pytest"],
    })
    assert result["test_passed"] is True
    assert "skipped" in result["test_results"]


def test_validate_runs_project_command_not_cwd_pytest(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs.get("cwd")

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = node_validate({
        "agent_response": "done",
        "code_changes": [{"path": "mod.py"}],
        "intent": "code",
        "workspace_path": str(tmp_path),
        "verify_commands": ["python -m pytest tests/test_mod.py"],
    })
    assert result["test_passed"] is True
    assert seen["cwd"] == str(tmp_path)
    assert seen["argv"][0] == "python"
    assert "pytest" in seen["argv"]
    assert seen["argv"] != ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"]


def test_execute_skip_flag_does_not_call_agent(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("must not run the agent")

    monkeypatch.setattr("gateway.graph_engine._run_execute_turn", boom)
    result = node_execute({
        "user_prompt": "hello",
        "plan": ["hello"],
        "skip_execute": True,
    })
    assert result["agent_response"] == ""
    assert result["enhanced_prompt"]
