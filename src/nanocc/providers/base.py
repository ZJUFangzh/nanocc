"""LLM Provider protocol and normalized event types.

The agent loop only handles ProviderEvent — it never touches SDK-specific types.
New backend = implement the LLMProvider protocol (~3 methods).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from nanocc.types import MessageUsage


# ── Provider Events (normalized) ────────────────────────────────────────────


class ProviderEventType(str, Enum):
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_STOP = "message_stop"
    CONTENT_BLOCK_START = "content_block_start"
    CONTENT_BLOCK_DELTA = "content_block_delta"
    CONTENT_BLOCK_STOP = "content_block_stop"


@dataclass
class ProviderEvent:
    """Normalized streaming event from any LLM provider."""

    type: ProviderEventType

    # content_block_start
    index: int = 0
    block_type: str = ""  # "text", "tool_use", "thinking"
    # For tool_use start
    tool_use_id: str = ""
    tool_name: str = ""

    # content_block_delta
    text: str = ""         # text or thinking delta
    partial_json: str = "" # tool_use input delta

    # message_start / message_delta
    usage: MessageUsage | None = None
    stop_reason: str | None = None
    model: str = ""

    # thinking block signature
    signature: str = ""


# ── Provider Protocol ───────────────────────────────────────────────────────


@runtime_checkable
class LLMProvider(Protocol):
    """Interface for LLM backends. Implement 3 methods to add a new provider."""

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str,
        max_tokens: int = 16_384,
        stop_sequences: list[str] | None = None,
        temperature: float | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> AsyncGenerator[ProviderEvent, None]:
        """Stream a completion, yielding normalized ProviderEvents."""
        ...

    def count_tokens(
        self, messages: list[dict[str, Any]], model: str
    ) -> int:
        """Estimate token count for a message list."""
        ...

    def get_context_window(self, model: str) -> int:
        """Return context window size for the given model."""
        ...
