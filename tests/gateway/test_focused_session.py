"""Phone chat joins the focused desktop session."""

from gateway.focused_session import (
    get_focused_session,
    pick_live_session,
    reset_focused_session_for_tests,
    set_focused_session,
)


def setup_function():
    reset_focused_session_for_tests()


def test_set_and_get_focused_session():
    set_focused_session(session_id="sess-1", session_key="stored-1", cwd="/repo", model="gpt")
    assert get_focused_session() == {
        "session_id": "sess-1",
        "session_key": "stored-1",
        "cwd": "/repo",
        "model": "gpt",
    }


def test_pick_live_prefers_pin():
    set_focused_session(session_id="pinned")
    assert pick_live_session()["session_id"] == "pinned"
