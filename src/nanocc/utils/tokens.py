"""Token counting and estimation utilities.

Replicates Claude Code's tokenCountWithEstimation logic:
- Use actual usage from last assistant message when available
- Fall back to rough character-based estimation (padded by 4/3)
"""

from __future__ import annotations

import json
from typing import Any

from nanocc.types import (
    AssistantMessage,
    Message,
    MessageUsage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

# Rough estimation: ~4 chars per token, padded by 4/3 for safety
CHARS_PER_TOKEN = 4
ESTIMATION_PADDING = 4 / 3
IMAGE_TOKEN_ESTIMATE = 1_600


def get_token_count_from_usage(usage: MessageUsage) -> int:
    """Total tokens consumed from a usage record."""
    return (
        usage.input_tokens
        + usage.output_tokens
        + usage.cache_creation_input_tokens
        + usage.cache_read_input_tokens
    )


def estimate_tokens_for_text(text: str) -> int:
    """Rough token estimate for a text string."""
    return max(1, int(len(text) / CHARS_PER_TOKEN * ESTIMATION_PADDING))


def estimate_tokens_for_message(msg: Message) -> int:
    """Rough token estimate for a single message."""
    if isinstance(msg, UserMessage):
        if isinstance(msg.content, str):
            return estimate_tokens_for_text(msg.content)
        total = 0
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += estimate_tokens_for_text(block.text)
            elif isinstance(block, ToolResultBlock):
                content = block.content
                if isinstance(content, str):
                    total += estimate_tokens_for_text(content)
                else:
                    total += estimate_tokens_for_text(json.dumps(content))
            elif isinstance(block, dict):
                if block.get("type") == "image":
                    total += IMAGE_TOKEN_ESTIMATE
                else:
                    total += estimate_tokens_for_text(json.dumps(block))
        return total

    elif isinstance(msg, AssistantMessage):
        total = 0
        for block in msg.content:
            if isinstance(block, TextBlock):
                total += estimate_tokens_for_text(block.text)
            elif isinstance(block, ToolUseBlock):
                total += estimate_tokens_for_text(block.name)
                total += estimate_tokens_for_text(json.dumps(block.input))
            elif isinstance(block, ThinkingBlock):
                total += estimate_tokens_for_text(block.thinking)
        return total

    else:
        # SystemMessage
        return estimate_tokens_for_text(getattr(msg, "text", ""))


def estimate_tokens_for_messages(messages: list[Message]) -> int:
    """Rough token estimate for a list of messages."""
    return sum(estimate_tokens_for_message(m) for m in messages)


def token_count_with_estimation(messages: list[Message]) -> int:
    """Best-effort token count.

    Uses actual usage from the last assistant message if available,
    then estimates any messages that came after it.
    Falls back to full estimation if no usage data exists.
    """
    # Find last assistant message with usage
    last_usage_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, AssistantMessage) and msg.usage:
            last_usage_idx = i
            break

    if last_usage_idx >= 0:
        usage = messages[last_usage_idx].usage  # type: ignore
        base = get_token_count_from_usage(usage)
        # Estimate tokens for messages after the last usage
        after = messages[last_usage_idx + 1 :]
        return base + estimate_tokens_for_messages(after)

    # No usage data — estimate everything
    return estimate_tokens_for_messages(messages)
