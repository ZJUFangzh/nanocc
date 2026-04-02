"""Auto compact — LLM-powered conversation summarization.

CC Layer 5: When token count exceeds threshold, summarize the conversation
and replace messages with a compact summary + boundary marker.

Trigger: token_count > (context_window - AUTOCOMPACT_BUFFER_TOKENS - max_output_tokens)
Circuit breaker: stops after MAX_CONSECUTIVE_FAILURES consecutive failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nanocc.constants import (
    AUTOCOMPACT_BUFFER_TOKENS,
    COMPACT_MAX_CONSECUTIVE_FAILURES,
    COMPACT_MAX_OUTPUT_TOKENS,
    POST_COMPACT_MAX_FILES,
    POST_COMPACT_MAX_TOKENS,
)
from nanocc.messages import create_system_message, create_user_message, get_text_content
from nanocc.providers.base import LLMProvider, ProviderEvent, ProviderEventType
from nanocc.types import (
    AssistantMessage,
    Message,
    SystemMessage,
    SystemMessageSubtype,
    UserMessage,
)
from nanocc.utils.tokens import token_count_with_estimation

logger = logging.getLogger(__name__)


@dataclass
class AutoCompactTracking:
    """Tracks compact state across turns."""
    consecutive_failures: int = 0
    last_compacted_at_turn: int = 0
    total_compactions: int = 0


def should_auto_compact(
    messages: list[Message],
    model: str,
    context_window: int,
    max_output_tokens: int = COMPACT_MAX_OUTPUT_TOKENS,
) -> bool:
    """Check if auto compact should trigger."""
    threshold = context_window - AUTOCOMPACT_BUFFER_TOKENS - max_output_tokens
    current_tokens = token_count_with_estimation(messages)
    return current_tokens >= threshold


async def auto_compact_if_needed(
    messages: list[Message],
    provider: LLMProvider,
    model: str,
    context_window: int,
    tracking: AutoCompactTracking,
    turn: int,
) -> list[Message] | None:
    """Run auto compact if needed. Returns new message list or None if not triggered.

    Circuit breaker: stops after MAX_CONSECUTIVE_FAILURES.
    """
    if tracking.consecutive_failures >= COMPACT_MAX_CONSECUTIVE_FAILURES:
        logger.warning("Auto compact circuit breaker: %d consecutive failures", tracking.consecutive_failures)
        return None

    if not should_auto_compact(messages, model, context_window):
        return None

    logger.info("Auto compact triggered at turn %d", turn)

    try:
        summary = await _generate_summary(messages, provider, model)
        if not summary:
            tracking.consecutive_failures += 1
            return None

        new_messages = _build_post_compact_messages(messages, summary)
        tracking.consecutive_failures = 0
        tracking.last_compacted_at_turn = turn
        tracking.total_compactions += 1
        logger.info("Auto compact succeeded. Messages: %d -> %d", len(messages), len(new_messages))
        return new_messages

    except Exception as e:
        tracking.consecutive_failures += 1
        logger.error("Auto compact failed: %s", e)
        return None


async def _generate_summary(
    messages: list[Message],
    provider: LLMProvider,
    model: str,
) -> str | None:
    """Generate a conversation summary using the LLM."""
    from nanocc.messages import to_api_messages

    # Build the summary request
    conversation_text = _format_conversation_for_summary(messages)

    summary_prompt = f"""{_COMPACT_PROMPT}

<conversation>
{conversation_text}
</conversation>"""

    api_messages = [{"role": "user", "content": summary_prompt}]
    system = [{"type": "text", "text": "You are a conversation summarizer. Respond with text only. Do NOT call any tools."}]

    # Stream the summary
    collected_text = ""
    try:
        async for event in provider.stream(
            messages=api_messages,
            system_prompt=system,
            tools=[],  # No tools for summary
            model=model,
            max_tokens=COMPACT_MAX_OUTPUT_TOKENS,
        ):
            if event.type == ProviderEventType.CONTENT_BLOCK_DELTA and event.text:
                collected_text += event.text
    except Exception as e:
        logger.error("Summary generation error: %s", e)
        return None

    if not collected_text.strip():
        return None

    # Format: strip <analysis>, keep <summary>
    return _format_summary(collected_text)


def _format_conversation_for_summary(messages: list[Message]) -> str:
    """Format messages into text for the summarizer."""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        role = "User" if isinstance(msg, UserMessage) else "Assistant"
        text = get_text_content(msg)
        if text:
            # Truncate very long messages
            if len(text) > 2000:
                text = text[:2000] + "..."
            parts.append(f"{role}: {text}")
    return "\n\n".join(parts)


def _format_summary(raw_summary: str) -> str:
    """Strip <analysis> tags, extract <summary> content."""
    import re

    # Remove analysis block
    result = re.sub(r"<analysis>[\s\S]*?</analysis>", "", raw_summary)

    # Extract summary content
    match = re.search(r"<summary>([\s\S]*?)</summary>", result)
    if match:
        result = f"Summary:\n{match.group(1).strip()}"
    else:
        # No tags — use as-is
        result = result.strip()

    # Clean excessive whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def _build_post_compact_messages(
    original_messages: list[Message],
    summary: str,
) -> list[Message]:
    """Build the post-compact message list.

    Structure: [boundary_marker, summary_message]
    Phase 4 will add: file re-injection, skill re-injection, etc.
    """
    boundary = create_system_message(
        SystemMessageSubtype.COMPACT_BOUNDARY,
        f"Conversation compacted. Original messages: {len(original_messages)}",
    )

    summary_msg = create_user_message(
        f"[Previous conversation summary]\n\n{summary}\n\n"
        "[The conversation was compacted. Continue from where we left off.]"
    )

    return [boundary, summary_msg]


# ── Compact Prompt (CC-faithful) ────────────────────────────────────────────

_COMPACT_PROMPT = """Your task is to create a detailed summary of the conversation so far.

Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts.

Your summary should include:
1. Primary Request and Intent: Capture all explicit and implicit user requests
2. Key Technical Concepts: Technologies, frameworks, and patterns discussed
3. Files and Code Sections: Enumerate all files mentioned or modified, with key changes
4. Errors and Fixes: All errors encountered and their solutions
5. Problem Solving: Current state of solved problems and ongoing troubleshooting
6. All User Messages: Preserve ALL non-tool-result user messages verbatim
7. Pending Tasks: Any explicitly requested tasks not yet completed
8. Current Work: What was being worked on immediately before this summary
9. Optional Next Step: Suggest a next step related to the most recent work

Wrap your final summary in <summary> tags.

CRITICAL: Respond with TEXT ONLY. Do NOT call any tools."""
