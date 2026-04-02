"""Tool result budget enforcement — truncate/persist oversized results.

CC Layer 1: Applied before every LLM call.
- Per-result: truncate at DEFAULT_MAX_RESULT_SIZE_CHARS (50K)
- Per-message aggregate: cap at MAX_TOOL_RESULTS_PER_MESSAGE_CHARS (200K)
"""

from __future__ import annotations

import logging
from typing import Any

from nanocc.constants import DEFAULT_MAX_RESULT_SIZE_CHARS, MAX_TOOL_RESULTS_PER_MESSAGE_CHARS
from nanocc.types import Message, ToolResultBlock, UserMessage

logger = logging.getLogger(__name__)

TRUNCATION_MARKER = "\n\n... [output truncated — {original} chars, showing first {kept}]"


def apply_tool_result_budget(messages: list[Message]) -> None:
    """Enforce size limits on tool results in-place.

    Mutates messages list: truncates oversized tool_result content blocks.
    """
    for msg in messages:
        if not isinstance(msg, UserMessage):
            continue
        if isinstance(msg.content, str):
            continue

        total_size = 0
        for i, block in enumerate(msg.content):
            if not isinstance(block, ToolResultBlock):
                continue

            content = block.content
            if not isinstance(content, str):
                continue

            content_len = len(content)

            # Per-result truncation
            if content_len > DEFAULT_MAX_RESULT_SIZE_CHARS:
                kept = DEFAULT_MAX_RESULT_SIZE_CHARS
                block.content = (
                    content[:kept]
                    + TRUNCATION_MARKER.format(original=content_len, kept=kept)
                )
                content_len = len(block.content)
                logger.debug(
                    "Truncated tool result %s: %d -> %d chars",
                    block.tool_use_id, content_len, kept,
                )

            # Per-message aggregate check
            total_size += content_len
            if total_size > MAX_TOOL_RESULTS_PER_MESSAGE_CHARS:
                # Truncate this and remaining results aggressively
                remaining_budget = max(0, MAX_TOOL_RESULTS_PER_MESSAGE_CHARS - (total_size - content_len))
                if remaining_budget < content_len:
                    block.content = (
                        block.content[:remaining_budget]
                        + f"\n\n... [aggregate budget exceeded — {total_size} chars total]"
                    )
