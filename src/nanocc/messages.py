"""Message creation, normalization, and API format conversion.

Handles the bidirectional mapping between nanocc's internal Message types
and the Anthropic API's message format.
"""

from __future__ import annotations

from typing import Any

from nanocc.types import (
    AssistantMessage,
    ContentBlock,
    MessageUsage,
    RedactedThinkingBlock,
    SystemMessage,
    SystemMessageSubtype,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    Message,
)


# ── Message Factories ───────────────────────────────────────────────────────


def create_user_message(text: str) -> UserMessage:
    return UserMessage(content=text)


def create_user_message_with_blocks(
    blocks: list[ContentBlock | dict[str, Any]],
) -> UserMessage:
    return UserMessage(content=blocks)


def create_assistant_message(
    content: list[ContentBlock],
    model: str = "",
    stop_reason: str | None = None,
    usage: MessageUsage | None = None,
) -> AssistantMessage:
    return AssistantMessage(
        content=content,
        model=model,
        stop_reason=stop_reason,
        usage=usage,
    )


def create_system_message(
    subtype: SystemMessageSubtype, text: str
) -> SystemMessage:
    return SystemMessage(subtype=subtype, text=text)


def create_tick_message() -> UserMessage:
    """Create a tick message for assistant mode proactive wake."""
    return UserMessage(content="<tick>You have been woken up by a periodic tick. "
        "Check if there's anything useful you can do proactively. "
        "If not, call the Sleep tool.</tick>")


# ── API Format Conversion ──────────────────────────────────────────────────


def content_block_to_api(block: ContentBlock) -> dict[str, Any]:
    """Convert internal ContentBlock to Anthropic API format."""
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    elif isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    elif isinstance(block, ToolResultBlock):
        result: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
        }
        if block.is_error:
            result["is_error"] = True
        return result
    elif isinstance(block, ThinkingBlock):
        return {
            "type": "thinking",
            "thinking": block.thinking,
            "signature": block.signature,
        }
    elif isinstance(block, RedactedThinkingBlock):
        return {"type": "redacted_thinking", "data": block.data}
    else:
        # dict passthrough
        return block  # type: ignore[return-value]


def message_to_api(msg: Message) -> dict[str, Any] | None:
    """Convert internal Message to Anthropic API message format.

    Returns None for system messages (they go in system_prompt).
    """
    if isinstance(msg, UserMessage):
        if isinstance(msg.content, str):
            return {"role": "user", "content": msg.content}
        else:
            return {
                "role": "user",
                "content": [
                    content_block_to_api(b) if not isinstance(b, dict) else b
                    for b in msg.content
                ],
            }
    elif isinstance(msg, AssistantMessage):
        content = [content_block_to_api(b) for b in msg.content]
        return {"role": "assistant", "content": content}
    elif isinstance(msg, SystemMessage):
        # Not sent to API, but needed for transcript persistence
        return None
    return None


def message_to_transcript(msg: Message) -> dict[str, Any]:
    """Convert internal Message to transcript format (includes SystemMessage)."""
    if isinstance(msg, SystemMessage):
        return {
            "role": "system",
            "subtype": msg.subtype.value,
            "content": msg.text,
        }
    api_msg = message_to_api(msg)
    if api_msg is not None:
        return api_msg
    return {"role": "unknown"}


def to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert message list to Anthropic API format, skipping system messages."""
    result = []
    for msg in messages:
        api_msg = message_to_api(msg)
        if api_msg is not None:
            result.append(api_msg)
    return result


def to_transcript_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert message list to transcript format (includes SystemMessage)."""
    return [message_to_transcript(msg) for msg in messages]


def to_api_system_prompt(
    text: str, *, enable_cache: bool = True
) -> list[dict[str, Any]]:
    """Build system prompt with optional cache_control."""
    block: dict[str, Any] = {"type": "text", "text": text}
    if enable_cache:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


# ── API Message Deserialization ────────────────────────────────────────────


def from_api_message(api_msg: dict[str, Any]) -> Message | None:
    """Convert an Anthropic API message dict back to internal Message type."""
    role = api_msg.get("role")
    content = api_msg.get("content")

    if role == "user":
        if isinstance(content, str):
            return UserMessage(content=content)
        # List of content blocks
        blocks: list[Any] = []
        for block in content or []:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "text":
                    blocks.append(TextBlock(text=block.get("text", "")))
                elif btype == "tool_result":
                    blocks.append(ToolResultBlock(
                        tool_use_id=block.get("tool_use_id", ""),
                        content=block.get("content", ""),
                        is_error=block.get("is_error", False),
                    ))
                else:
                    blocks.append(block)
            else:
                blocks.append(block)
        return UserMessage(content=blocks)

    elif role == "assistant":
        blocks = []
        for block in content or []:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "text":
                    blocks.append(TextBlock(text=block.get("text", "")))
                elif btype == "tool_use":
                    blocks.append(ToolUseBlock(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        input=block.get("input", {}),
                    ))
                elif btype == "thinking":
                    blocks.append(ThinkingBlock(
                        thinking=block.get("thinking", ""),
                        signature=block.get("signature", ""),
                    ))
                elif btype == "redacted_thinking":
                    blocks.append(RedactedThinkingBlock(data=block.get("data", "")))
                else:
                    blocks.append(block)
            else:
                blocks.append(block)
        return AssistantMessage(content=blocks)

    elif role == "system":
        subtype_str = api_msg.get("subtype", "")
        text = content if isinstance(content, str) else ""
        try:
            subtype = SystemMessageSubtype(subtype_str)
        except ValueError:
            subtype = SystemMessageSubtype.COMPACT_BOUNDARY
        return SystemMessage(subtype=subtype, text=text)

    return None


def from_api_messages(api_msgs: list[dict[str, Any]]) -> list[Message]:
    """Convert a list of API messages back to internal Message types."""
    messages: list[Message] = []
    for api_msg in api_msgs:
        msg = from_api_message(api_msg)
        if msg is not None:
            messages.append(msg)
    return messages


# ── Message Utilities ───────────────────────────────────────────────────────


def get_text_content(msg: Message) -> str:
    """Extract all text content from a message."""
    if isinstance(msg, UserMessage):
        if isinstance(msg.content, str):
            return msg.content
        parts = []
        for b in msg.content:
            if isinstance(b, TextBlock):
                parts.append(b.text)
            elif isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
        return "\n".join(parts)
    elif isinstance(msg, AssistantMessage):
        parts = []
        for b in msg.content:
            if isinstance(b, TextBlock):
                parts.append(b.text)
        return "\n".join(parts)
    elif isinstance(msg, SystemMessage):
        return msg.text
    return ""


def get_tool_use_blocks(msg: AssistantMessage) -> list[ToolUseBlock]:
    """Extract tool_use blocks from an assistant message."""
    return [b for b in msg.content if isinstance(b, ToolUseBlock)]


def get_tool_result_blocks(msg: UserMessage) -> list[ToolResultBlock]:
    """Extract tool_result blocks from a user message."""
    if isinstance(msg.content, str):
        return []
    return [b for b in msg.content if isinstance(b, ToolResultBlock)]


def has_tool_use(msg: AssistantMessage) -> bool:
    return any(isinstance(b, ToolUseBlock) for b in msg.content)


def count_content_blocks(msg: Message) -> int:
    if isinstance(msg, UserMessage):
        if isinstance(msg.content, str):
            return 1
        return len(msg.content)
    elif isinstance(msg, AssistantMessage):
        return len(msg.content)
    return 1


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)
