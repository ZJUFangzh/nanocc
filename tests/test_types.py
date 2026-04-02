"""Tests for core types — Message, ContentBlock, Terminal, QueryParams."""

from __future__ import annotations

from nanocc.types import (
    AssistantMessage,
    LoopState,
    MessageUsage,
    QueryParams,
    Terminal,
    TerminalReason,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    ToolUseContext,
    UserMessage,
)


def test_user_message_string():
    msg = UserMessage(content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"


def test_user_message_blocks():
    msg = UserMessage(content=[TextBlock(text="hi")])
    assert isinstance(msg.content, list)
    assert msg.content[0].text == "hi"


def test_assistant_message():
    msg = AssistantMessage(content=[TextBlock(text="reply")])
    assert msg.role == "assistant"
    assert len(msg.content) == 1


def test_tool_use_block():
    block = ToolUseBlock(id="t1", name="Bash", input={"command": "ls"})
    assert block.type == "tool_use"
    assert block.name == "Bash"


def test_tool_result_block():
    block = ToolResultBlock(tool_use_id="t1", content="output", is_error=False)
    assert block.type == "tool_result"
    assert not block.is_error


def test_thinking_block():
    block = ThinkingBlock(thinking="thinking...", signature="sig")
    assert block.type == "thinking"


def test_terminal():
    t = Terminal(reason=TerminalReason.COMPLETED)
    assert t.reason == TerminalReason.COMPLETED
    assert t.error is None


def test_terminal_reasons():
    reasons = [r for r in TerminalReason]
    assert len(reasons) == 6
    assert TerminalReason.COMPLETED in reasons
    assert TerminalReason.MODEL_ERROR in reasons


def test_query_params_defaults():
    p = QueryParams(messages=[], system_prompt="", provider=None, model="test")
    assert p.max_turns == 0
    assert p.max_tokens == 16_384
    assert p.assistant_mode is False
    assert p.proactive_engine is None


def test_loop_state():
    from nanocc.utils.abort import AbortController
    ctx = ToolUseContext(cwd=".", model="test", abort_controller=AbortController())
    state = LoopState(messages=[], tool_use_context=ctx)
    assert state.turn_count == 0
    assert state.hook_engine is None


def test_message_usage():
    u = MessageUsage(input_tokens=10, output_tokens=20)
    assert u.input_tokens == 10
    assert u.cache_creation_input_tokens == 0
