"""Tool orchestration — concurrent/serial batch execution.

Replicates Claude Code's partitioning logic:
- Read-only tools run concurrently (up to MAX_TOOL_CONCURRENCY)
- Write tools run serially
- Consecutive concurrent tools are batched together
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from nanocc.constants import MAX_TOOL_CONCURRENCY
from nanocc.tools.base import BaseTool
from nanocc.tools.registry import find_tool
from nanocc.types import (
    PermissionBehavior,
    ToolResult,
    ToolUseBlock,
    ToolUseContext,
    ToolResultBlock,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolBatch:
    is_concurrent: bool
    blocks: list[ToolUseBlock]


def partition_tool_calls(
    blocks: list[ToolUseBlock],
    tools: list[BaseTool],
) -> list[ToolBatch]:
    """Partition tool calls into concurrent/serial batches.

    Consecutive concurrency-safe tools form one batch.
    Non-concurrent tools each get their own batch.
    """
    batches: list[ToolBatch] = []

    for block in blocks:
        tool = find_tool(tools, block.name)
        is_safe = False
        if tool:
            try:
                is_safe = tool.is_concurrency_safe(block.input)
            except Exception:
                is_safe = False

        if is_safe and batches and batches[-1].is_concurrent:
            batches[-1].blocks.append(block)
        else:
            batches.append(ToolBatch(is_concurrent=is_safe, blocks=[block]))

    return batches


async def execute_single_tool(
    block: ToolUseBlock,
    tools: list[BaseTool],
    context: ToolUseContext,
    hook_engine: Any = None,
) -> ToolResultBlock:
    """Execute a single tool call and return a ToolResultBlock."""
    tool = find_tool(tools, block.name)

    if not tool:
        return ToolResultBlock(
            tool_use_id=block.id,
            content=f"Error: Unknown tool '{block.name}'",
            is_error=True,
        )

    # Permission check
    try:
        perm = await tool.check_permissions(block.input, context)
        if perm.behavior == PermissionBehavior.DENY:
            return ToolResultBlock(
                tool_use_id=block.id,
                content=f"Permission denied: {perm.message}",
                is_error=True,
            )
        # ASK behavior — in Phase 2 we auto-allow; Phase 8 adds UI
        # For now, treat ASK as ALLOW
    except Exception as e:
        logger.error("Permission check error for %s: %s", block.name, e)
        return ToolResultBlock(
            tool_use_id=block.id,
            content=f"Permission check error: {e}",
            is_error=True,
        )

    # Fire tool_start hook
    if hook_engine:
        from nanocc.hooks.types import HookEvent
        await hook_engine.fire(HookEvent.TOOL_START, tool_name=block.name, tool_input=block.input)

    # Execute
    try:
        result = await tool.execute(block.input, context)
        content = result.content
        if isinstance(content, list):
            import json
            content = json.dumps(content)
        result_block = ToolResultBlock(
            tool_use_id=block.id,
            content=content,
            is_error=result.is_error,
        )
    except Exception as e:
        logger.error("Tool execution error for %s: %s", block.name, e)
        result_block = ToolResultBlock(
            tool_use_id=block.id,
            content=f"Error: {e}",
            is_error=True,
        )
        # Fire tool_error hook
        if hook_engine:
            from nanocc.hooks.types import HookEvent
            await hook_engine.fire(HookEvent.TOOL_ERROR, tool_name=block.name, tool_input=block.input)
        return result_block

    # Fire tool_complete hook
    if hook_engine:
        from nanocc.hooks.types import HookEvent
        await hook_engine.fire(HookEvent.TOOL_COMPLETE, tool_name=block.name, tool_input=block.input, result=result_block)

    return result_block


async def run_tools(
    blocks: list[ToolUseBlock],
    tools: list[BaseTool],
    context: ToolUseContext,
    hook_engine: Any = None,
) -> list[ToolResultBlock]:
    """Execute tool calls with proper concurrency.

    Returns ToolResultBlocks in the same order as input blocks.
    """
    batches = partition_tool_calls(blocks, tools)
    results: dict[str, ToolResultBlock] = {}

    for batch in batches:
        if batch.is_concurrent and len(batch.blocks) > 1:
            # Run concurrently with bounded parallelism
            sem = asyncio.Semaphore(MAX_TOOL_CONCURRENCY)

            async def run_with_sem(b: ToolUseBlock) -> tuple[str, ToolResultBlock]:
                async with sem:
                    r = await execute_single_tool(b, tools, context, hook_engine)
                    return b.id, r

            tasks = [run_with_sem(b) for b in batch.blocks]
            for coro in asyncio.as_completed(tasks):
                block_id, result = await coro
                results[block_id] = result
        else:
            # Run serially
            for block in batch.blocks:
                result = await execute_single_tool(block, tools, context, hook_engine)
                results[block.id] = result

    # Return in original order
    return [results[b.id] for b in blocks]
