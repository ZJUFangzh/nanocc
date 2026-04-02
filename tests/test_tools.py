"""Tests for tool system — registry, orchestration, individual tools."""

from __future__ import annotations

import pytest

from nanocc.tools.base import BaseTool
from nanocc.tools.registry import find_tool, get_all_tools
from nanocc.tools.orchestration import (
    execute_single_tool,
    partition_tool_calls,
    run_tools,
)
from nanocc.types import ToolUseBlock


# ── Registry ──

def test_get_all_tools():
    tools = get_all_tools()
    names = [t.name for t in tools]
    assert len(tools) == 12
    assert "Bash" in names
    assert "Read" in names
    assert "Write" in names
    assert "Edit" in names
    assert "Glob" in names
    assert "Grep" in names
    assert "WebFetch" in names
    assert "AskUser" in names
    assert "Agent" in names
    assert "Skill" in names
    assert "Brief" in names
    assert "Sleep" in names


def test_find_tool():
    tools = get_all_tools()
    bash = find_tool(tools, "Bash")
    assert bash is not None
    assert bash.name == "Bash"

    missing = find_tool(tools, "NonExistent")
    assert missing is None


# ── Partition ──

def test_partition_all_read_only(basic_tools):
    blocks = [
        ToolUseBlock(id="t1", name="Read", input={"file_path": "a.txt"}),
        ToolUseBlock(id="t2", name="Read", input={"file_path": "b.txt"}),
    ]
    batches = partition_tool_calls(blocks, basic_tools)
    assert len(batches) == 1
    assert batches[0].is_concurrent
    assert len(batches[0].blocks) == 2


def test_partition_write_serial(all_tools):
    blocks = [
        ToolUseBlock(id="t1", name="Write", input={"file_path": "a.txt", "content": "x"}),
        ToolUseBlock(id="t2", name="Write", input={"file_path": "b.txt", "content": "y"}),
    ]
    batches = partition_tool_calls(blocks, all_tools)
    # Write is not concurrent, each gets its own batch
    assert len(batches) == 2
    assert not batches[0].is_concurrent
    assert not batches[1].is_concurrent


def test_partition_mixed(all_tools):
    blocks = [
        ToolUseBlock(id="t1", name="Read", input={"file_path": "a.txt"}),
        ToolUseBlock(id="t2", name="Read", input={"file_path": "b.txt"}),
        ToolUseBlock(id="t3", name="Write", input={"file_path": "c.txt", "content": "x"}),
        ToolUseBlock(id="t4", name="Read", input={"file_path": "d.txt"}),
    ]
    batches = partition_tool_calls(blocks, all_tools)
    assert len(batches) == 3  # [Read,Read], [Write], [Read]
    assert batches[0].is_concurrent
    assert not batches[1].is_concurrent
    assert batches[2].is_concurrent


# ── Execute single tool ──

@pytest.mark.asyncio
async def test_execute_bash(basic_tools, tool_context):
    block = ToolUseBlock(id="t1", name="Bash", input={"command": "echo hello_test"})
    result = await execute_single_tool(block, basic_tools, tool_context)
    assert "hello_test" in result.content
    assert not result.is_error


@pytest.mark.asyncio
async def test_execute_unknown_tool(basic_tools, tool_context):
    block = ToolUseBlock(id="t1", name="NonExistent", input={})
    result = await execute_single_tool(block, basic_tools, tool_context)
    assert result.is_error
    assert "Unknown tool" in result.content


@pytest.mark.asyncio
async def test_execute_with_hook_engine(basic_tools, tool_context, hook_engine):
    from nanocc.hooks.types import Hook, HookEvent
    hook_engine.register(HookEvent.TOOL_START, None, [Hook(type="prompt", prompt="start")])
    hook_engine.register(HookEvent.TOOL_COMPLETE, None, [Hook(type="prompt", prompt="complete")])

    block = ToolUseBlock(id="t1", name="Bash", input={"command": "echo hi"})
    result = await execute_single_tool(block, basic_tools, tool_context, hook_engine=hook_engine)
    assert not result.is_error


# ── run_tools ──

@pytest.mark.asyncio
async def test_run_tools_preserves_order(basic_tools, tool_context):
    blocks = [
        ToolUseBlock(id="t1", name="Bash", input={"command": "echo first"}),
        ToolUseBlock(id="t2", name="Bash", input={"command": "echo second"}),
    ]
    results = await run_tools(blocks, basic_tools, tool_context)
    assert len(results) == 2
    assert results[0].tool_use_id == "t1"
    assert results[1].tool_use_id == "t2"
    assert "first" in results[0].content
    assert "second" in results[1].content


@pytest.mark.asyncio
async def test_run_tools_with_hook_engine(basic_tools, tool_context, hook_engine):
    blocks = [ToolUseBlock(id="t1", name="Bash", input={"command": "echo test"})]
    results = await run_tools(blocks, basic_tools, tool_context, hook_engine=hook_engine)
    assert len(results) == 1
    assert not results[0].is_error
