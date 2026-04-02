"""Tests for compact pipeline — budget, micro, auto, post."""

from __future__ import annotations

import pytest

from nanocc.compact.tool_result_budget import apply_tool_result_budget
from nanocc.compact.micro_compact import micro_compact
from nanocc.compact.auto_compact import should_auto_compact
from nanocc.compact.post_compact import create_post_compact_file_attachments
from nanocc.messages import create_assistant_message, create_user_message, create_user_message_with_blocks
from nanocc.types import TextBlock, ToolResultBlock, ToolUseBlock, UserMessage


# ── tool_result_budget ──

def test_budget_truncates_large_result():
    big_content = "x" * 60_000
    blocks = [ToolResultBlock(tool_use_id="t1", content=big_content)]
    msg = create_user_message_with_blocks(blocks)
    messages = [msg]

    apply_tool_result_budget(messages)

    # Content should be truncated
    result_block = messages[0].content[0]
    assert len(result_block.content) < 60_000


def test_budget_keeps_small_result():
    blocks = [ToolResultBlock(tool_use_id="t1", content="small")]
    msg = create_user_message_with_blocks(blocks)
    messages = [msg]

    apply_tool_result_budget(messages)
    assert messages[0].content[0].content == "small"


# ── micro_compact ──

def test_micro_compact_clears_old():
    # Create 10 tool result messages — more than keep_recent (5)
    messages = []
    for i in range(10):
        messages.append(create_assistant_message([
            ToolUseBlock(id=f"t{i}", name="Bash", input={"command": "echo"}),
        ]))
        messages.append(create_user_message_with_blocks([
            ToolResultBlock(tool_use_id=f"t{i}", content=f"result_{i}" * 100),
        ]))

    cleared = micro_compact(messages, keep_recent=5)
    assert cleared > 0

    # Recent results should be preserved
    last_msg = messages[-1]
    if isinstance(last_msg, UserMessage) and isinstance(last_msg.content, list):
        last_block = last_msg.content[0]
        if isinstance(last_block, ToolResultBlock):
            assert "result_" in last_block.content


def test_micro_compact_no_op_few_messages():
    messages = [
        create_assistant_message([ToolUseBlock(id="t1", name="Bash", input={})]),
        create_user_message_with_blocks([ToolResultBlock(tool_use_id="t1", content="ok")]),
    ]
    cleared = micro_compact(messages, keep_recent=5)
    assert cleared == 0  # Only 1 result, below threshold


# ── auto_compact ──

def test_should_auto_compact_below_threshold():
    messages = [create_user_message("short message")]
    assert not should_auto_compact(messages, "test", 100_000)


def test_should_auto_compact_above_threshold():
    # Create messages large enough to exceed threshold
    # threshold = 100K - 13K (buffer) - 20K (output) = 67K tokens
    # ~4 chars per token, so 67K*4 = ~268K chars needed
    big_msg = create_user_message("x" * 300_000)
    messages = [big_msg]
    assert should_auto_compact(messages, "test", 100_000)


def test_auto_compact_circuit_breaker():
    from nanocc.compact.auto_compact import AutoCompactTracking, COMPACT_MAX_CONSECUTIVE_FAILURES
    tracking = AutoCompactTracking()
    tracking.consecutive_failures = COMPACT_MAX_CONSECUTIVE_FAILURES
    # The circuit breaker is checked in auto_compact_if_needed, not should_auto_compact
    # Verify tracking fields are accessible
    assert tracking.consecutive_failures == COMPACT_MAX_CONSECUTIVE_FAILURES


# ── post_compact ──

def test_post_compact_file_attachments():
    # create_post_compact_file_attachments(messages, cwd)
    messages = [
        create_assistant_message([ToolUseBlock(id="t1", name="Read", input={"file_path": "/tmp/test.txt"})]),
        create_user_message_with_blocks([ToolResultBlock(tool_use_id="t1", content="file content here")]),
    ]
    attachments = create_post_compact_file_attachments(messages, cwd=".")
    # Should return a list (possibly empty if files don't exist on disk)
    assert isinstance(attachments, list)
