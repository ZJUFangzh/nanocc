"""Micro compact — clear old tool results to free context space.

CC Layer 3: Replaces old tool_result content with '[Old tool result cleared]'.
Keeps the N most recent tool results intact.

Applied before every LLM call, after tool_result_budget.
"""

from __future__ import annotations

import logging
from typing import Any

from nanocc.types import Message, ToolResultBlock, UserMessage

logger = logging.getLogger(__name__)

CLEARED_MESSAGE = "[Old tool result content cleared]"

# Tools eligible for clearing (stateless results that can be re-fetched)
COMPACTABLE_TOOLS: set[str] = {
    "Read", "Bash", "Grep", "Glob", "WebFetch", "Edit", "Write",
}

# Keep the N most recent tool results intact
DEFAULT_KEEP_RECENT = 5


def micro_compact(
    messages: list[Message],
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> int:
    """Clear old tool result content in-place.

    Returns the number of tool results cleared.
    """
    # Collect all tool_result IDs in order (oldest first)
    all_tool_results: list[tuple[UserMessage, int]] = []  # (message, block_index)

    for msg in messages:
        if not isinstance(msg, UserMessage):
            continue
        if isinstance(msg.content, str):
            continue
        for i, block in enumerate(msg.content):
            if isinstance(block, ToolResultBlock):
                all_tool_results.append((msg, i))

    if len(all_tool_results) <= keep_recent:
        return 0

    # Determine which results to clear
    to_clear = all_tool_results[: len(all_tool_results) - keep_recent]
    cleared = 0

    for msg, block_idx in to_clear:
        block = msg.content[block_idx]  # type: ignore
        if not isinstance(block, ToolResultBlock):
            continue

        content = block.content
        if isinstance(content, str) and content == CLEARED_MESSAGE:
            continue  # Already cleared

        if isinstance(content, str) and len(content) > 100:
            block.content = CLEARED_MESSAGE
            cleared += 1

    if cleared:
        logger.debug("Micro-compact: cleared %d old tool results", cleared)

    return cleared
