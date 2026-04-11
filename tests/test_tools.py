"""Tests for tool system — registry, orchestration, individual tools."""

from __future__ import annotations

import asyncio
import time

import pytest

from nanocc.tools.base import BaseTool
from nanocc.tools.registry import find_tool, get_all_tools
from nanocc.tools.orchestration import (
    execute_single_tool,
    partition_tool_calls,
    run_tools,
)
from nanocc.types import ToolResult, ToolUseBlock, ToolUseContext


# ── Registry ──

def test_get_all_tools():
    tools = get_all_tools()
    names = [t.name for t in tools]
    assert len(tools) == 10
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
    # Brief/Sleep are assistant-mode-only tools (not in default registry).
    # The cowork product appends them when assistant_mode is enabled.
    assert "Brief" not in names
    assert "Sleep" not in names


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


# ── Concurrent execution (gather) ──

class SlowTool(BaseTool):
    """A tool that sleeps to simulate slow I/O (e.g. API calls)."""
    name = "SlowTool"
    description = "Sleeps for a bit"
    is_read_only = True
    input_schema = {"type": "object", "properties": {"delay": {"type": "number"}}}

    async def execute(self, input, context):
        await asyncio.sleep(input.get("delay", 0.1))
        return ToolResult(content=f"slept {input.get('delay')}")


@pytest.mark.asyncio
async def test_concurrent_tools_run_in_parallel():
    """Two read-only tools should run concurrently via asyncio.gather, not serially."""
    tools = [SlowTool()]
    ctx = ToolUseContext(cwd=".", tools=tools, model="test")
    blocks = [
        ToolUseBlock(id="t1", name="SlowTool", input={"delay": 0.2}),
        ToolUseBlock(id="t2", name="SlowTool", input={"delay": 0.2}),
    ]
    start = time.monotonic()
    results = await run_tools(blocks, tools, ctx)
    elapsed = time.monotonic() - start

    assert len(results) == 2
    assert not results[0].is_error
    assert not results[1].is_error
    # If run in parallel, total time should be ~0.2s, not ~0.4s
    assert elapsed < 0.35, f"Expected parallel execution but took {elapsed:.2f}s"


class FailingTool(BaseTool):
    """A tool that raises an exception."""
    name = "FailingTool"
    description = "Always fails"
    is_read_only = True
    input_schema = {"type": "object", "properties": {}}

    async def execute(self, input, context):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_concurrent_tools_one_failure_does_not_block_others():
    """If one concurrent tool fails, the others should still complete."""
    tools = [SlowTool(), FailingTool()]
    ctx = ToolUseContext(cwd=".", tools=tools, model="test")
    blocks = [
        ToolUseBlock(id="t1", name="SlowTool", input={"delay": 0.05}),
        ToolUseBlock(id="t2", name="FailingTool", input={}),
    ]
    results = await run_tools(blocks, tools, ctx)
    assert len(results) == 2
    assert not results[0].is_error
    assert "slept" in results[0].content
    # FailingTool should produce an error result, not crash the batch
    assert results[1].is_error
