"""Anthropic Claude provider — streaming, thinking, cache_control."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import anthropic

from nanocc.constants import CONTEXT_WINDOWS, DEFAULT_CONTEXT_WINDOW
from nanocc.providers.base import ProviderEvent, ProviderEventType
from nanocc.types import MessageUsage

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """LLM provider for Claude via the Anthropic API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)

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
        """Stream completion from Claude, yielding normalized events."""

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system_prompt:
            params["system"] = system_prompt

        if tools:
            params["tools"] = tools

        if stop_sequences:
            params["stop_sequences"] = stop_sequences

        if temperature is not None:
            params["temperature"] = temperature

        if thinking:
            params["thinking"] = thinking

        async with self._client.messages.stream(**params) as stream:
            async for event in stream:
                normalized = self._normalize_event(event)
                if normalized is not None:
                    yield normalized

    def _normalize_event(self, event: Any) -> ProviderEvent | None:
        """Convert Anthropic SDK event to normalized ProviderEvent."""
        event_type = event.type

        if event_type == "message_start":
            msg = event.message
            usage = self._extract_usage(msg.usage) if msg.usage else None
            return ProviderEvent(
                type=ProviderEventType.MESSAGE_START,
                usage=usage,
                model=msg.model,
            )

        elif event_type == "message_delta":
            usage = (
                self._extract_usage(event.usage) if event.usage else None
            )
            return ProviderEvent(
                type=ProviderEventType.MESSAGE_DELTA,
                stop_reason=event.delta.stop_reason if event.delta else None,
                usage=usage,
            )

        elif event_type == "message_stop":
            return ProviderEvent(type=ProviderEventType.MESSAGE_STOP)

        elif event_type == "content_block_start":
            block = event.content_block
            block_type = block.type
            ev = ProviderEvent(
                type=ProviderEventType.CONTENT_BLOCK_START,
                index=event.index,
                block_type=block_type,
            )
            if block_type == "tool_use":
                ev.tool_use_id = block.id
                ev.tool_name = block.name
            return ev

        elif event_type == "content_block_delta":
            delta = event.delta
            delta_type = delta.type

            ev = ProviderEvent(
                type=ProviderEventType.CONTENT_BLOCK_DELTA,
                index=event.index,
            )

            if delta_type == "text_delta":
                ev.text = delta.text
                ev.block_type = "text"
            elif delta_type == "thinking_delta":
                ev.text = delta.thinking
                ev.block_type = "thinking"
            elif delta_type == "input_json_delta":
                ev.partial_json = delta.partial_json
                ev.block_type = "tool_use"
            elif delta_type == "signature_delta":
                ev.signature = delta.signature
                ev.block_type = "thinking"

            return ev

        elif event_type == "content_block_stop":
            return ProviderEvent(
                type=ProviderEventType.CONTENT_BLOCK_STOP,
                index=event.index,
            )

        return None

    def _extract_usage(self, usage: Any) -> MessageUsage:
        return MessageUsage(
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_creation_input_tokens=getattr(
                usage, "cache_creation_input_tokens", 0
            )
            or 0,
            cache_read_input_tokens=getattr(
                usage, "cache_read_input_tokens", 0
            )
            or 0,
        )

    def count_tokens(
        self, messages: list[dict[str, Any]], model: str
    ) -> int:
        """Estimate tokens. For exact count, use the API (sync only in Phase 1)."""
        text = json.dumps(messages)
        return max(1, len(text) // 4)

    def get_context_window(self, model: str) -> int:
        for prefix, window in CONTEXT_WINDOWS.items():
            if model.startswith(prefix):
                return window
        return DEFAULT_CONTEXT_WINDOW
