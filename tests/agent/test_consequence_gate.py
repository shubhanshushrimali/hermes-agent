"""Pre-tool consequence gate for mutating tools."""

from types import SimpleNamespace

from agent.consequence_gate import (
    CONSEQUENCE_TOOLS,
    consequence_pre_tool_block,
    capture_assistant_for_consequence_gate,
)


def test_empty_assistant_blocks_write():
    agent = SimpleNamespace(_consequence_guidance=True)
    capture_assistant_for_consequence_gate(agent, SimpleNamespace(content=""))
    block = consequence_pre_tool_block(agent, "write_file")
    assert block is not None
    assert "responsible-action" in block
    assert "write_file" in block


def test_substantial_text_passes_and_sticky_for_turn():
    agent = SimpleNamespace(_consequence_guidance=True)
    capture_assistant_for_consequence_gate(
        agent,
        SimpleNamespace(
            content=(
                "I will change auth.py to reject empty tokens. "
                "This is reversible via git. Affects login callers only."
            )
        ),
    )
    assert consequence_pre_tool_block(agent, "write_file") is None
    assert consequence_pre_tool_block(agent, "terminal") is None


def test_yolo_skips_gate():
    agent = SimpleNamespace(_consequence_guidance=True, yolo_mode=True)
    capture_assistant_for_consequence_gate(agent, SimpleNamespace(content=""))
    assert consequence_pre_tool_block(agent, "terminal") is None


def test_read_file_is_not_gated():
    agent = SimpleNamespace(_consequence_guidance=True)
    capture_assistant_for_consequence_gate(agent, SimpleNamespace(content=""))
    assert consequence_pre_tool_block(agent, "read_file") is None
    assert "read_file" not in CONSEQUENCE_TOOLS
