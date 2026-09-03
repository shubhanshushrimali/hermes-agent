"""Hard-stop the core turn on spend / token budget."""

from types import SimpleNamespace

from agent.spend_budget import (
    SPEND_BUDGET_WRAPUP_NOTICE,
    maybe_inject_spend_budget_wrapup,
    record_turn_cost,
    reset_budget_for_tests,
    spend_or_token_budget_reason,
)


def setup_function():
    reset_budget_for_tests()


def _agent(**kwargs):
    defaults = dict(
        max_daily_cost_usd=10.0,
        max_session_cost_usd=None,
        max_session_tokens=None,
        session_estimated_cost_usd=0.0,
        session_total_tokens=0,
        _spend_budget_wrapup_injected=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_session_cost_cap_stops():
    agent = _agent(max_daily_cost_usd=None, max_session_cost_usd=0.50, session_estimated_cost_usd=0.50)
    assert spend_or_token_budget_reason(agent) == "spend_budget_exhausted"


def test_session_cost_under_cap_continues():
    agent = _agent(max_daily_cost_usd=None, max_session_cost_usd=1.0, session_estimated_cost_usd=0.10)
    assert spend_or_token_budget_reason(agent) is None


def test_token_cap_stops():
    agent = _agent(max_daily_cost_usd=None, max_session_tokens=1000, session_total_tokens=1000)
    assert spend_or_token_budget_reason(agent) == "token_budget_exhausted"


def test_no_caps_never_stop():
    agent = _agent(max_daily_cost_usd=None, max_session_cost_usd=None, max_session_tokens=None)
    agent.session_estimated_cost_usd = 999
    agent.session_total_tokens = 10_000_000
    assert spend_or_token_budget_reason(agent) is None


def test_daily_cap_stops_after_record():
    agent = _agent(max_daily_cost_usd=1.0)
    record_turn_cost(agent, 1.0)
    assert spend_or_token_budget_reason(agent) == "spend_budget_exhausted"


def test_daily_record_skipped_when_daily_cap_off():
    agent = _agent(max_daily_cost_usd=None)
    record_turn_cost(agent, 100.0)
    # Session cap still off; daily guard must not have been fed.
    from agent.spend_budget import get_budget

    assert get_budget().daily_spend == 0.0


def test_wrapup_at_80_percent_session_cost():
    agent = _agent(max_daily_cost_usd=None, max_session_cost_usd=1.0, session_estimated_cost_usd=0.81)
    messages = [{"role": "tool", "content": "ok"}]
    assert maybe_inject_spend_budget_wrapup(agent, messages) is True
    assert SPEND_BUDGET_WRAPUP_NOTICE in messages[0]["content"]
    assert maybe_inject_spend_budget_wrapup(agent, messages) is False


def test_wrapup_skipped_before_80():
    agent = _agent(max_daily_cost_usd=None, max_session_cost_usd=1.0, session_estimated_cost_usd=0.50)
    messages = [{"role": "tool", "content": "ok"}]
    assert maybe_inject_spend_budget_wrapup(agent, messages) is False


def test_record_tracks_by_model():
    from agent.spend_budget import get_budget

    agent = _agent(max_daily_cost_usd=10.0, model="gpt-test")
    record_turn_cost(agent, 1.25)
    assert get_budget().by_model["gpt-test"] == 1.25
    days = get_budget().last_7_days
    assert days[-1]["cost"] == 1.25


def test_dashboard_cap_tighter_than_agent_config():
    from agent.spend_budget import get_budget

    agent = _agent(max_daily_cost_usd=10.0)
    get_budget().max_daily_usd = 1.0
    record_turn_cost(agent, 1.0)
    assert spend_or_token_budget_reason(agent) == "spend_budget_exhausted"

