"""OpenAI-compatible provider — works with OpenRouter, Together, Groq, etc."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from nanocc.constants import DEFAULT_CONTEXT_WINDOW
from nanocc.providers.base import ProviderEvent, ProviderEventType
from nanocc.types import MessageUsage

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    """LLM provider for any OpenAI-compatible API (OpenRouter, Together, etc.)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or "https://openrouter.ai/api/v1",
        )

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
        """Stream completion, yielding normalized ProviderEvents."""

        # Convert Anthropic-style system prompt to OpenAI messages
        oai_messages: list[dict[str, Any]] = []
        if system_prompt:
            sys_text = ""
            for block in system_prompt:
                if isinstance(block, dict):
                    sys_text += block.get("text", "")
                elif isinstance(block, str):
                    sys_text += block
            if sys_text:
                oai_messages.append({"role": "system", "content": sys_text})

        # Convert Anthropic-style messages to OpenAI format
        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, list):
                oai_messages.extend(converted)
            else:
                oai_messages.append(converted)

        params: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if stop_sequences:
            params["stop"] = stop_sequences
        if temperature is not None:
            params["temperature"] = temperature

        # OpenAI tool format
        if tools:
            params["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {}),
                    },
                }
                for t in tools
            ]

        yield ProviderEvent(type=ProviderEventType.MESSAGE_START, model=model)

        input_tokens = 0
        output_tokens = 0
        current_tool_index: int | None = None

        response = await self._client.chat.completions.create(**params)

        async for chunk in response:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                # Usage-only chunk
                if chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens or 0
                    output_tokens = chunk.usage.completion_tokens or 0
                continue

            delta = choice.delta

            # Text content
            if delta.content:
                # Emit block start on first text
                if current_tool_index is None:
                    yield ProviderEvent(
                        type=ProviderEventType.CONTENT_BLOCK_START,
                        index=0,
                        block_type="text",
                    )
                    current_tool_index = -1  # sentinel: text block started

                yield ProviderEvent(
                    type=ProviderEventType.CONTENT_BLOCK_DELTA,
                    index=0,
                    block_type="text",
                    text=delta.content,
                )

            # Tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if tc.function and tc.function.name:
                        # New tool call start
                        yield ProviderEvent(
                            type=ProviderEventType.CONTENT_BLOCK_START,
                            index=idx + 1,  # offset by 1 for text block
                            block_type="tool_use",
                            tool_use_id=tc.id or f"call_{idx}",
                            tool_name=tc.function.name,
                        )
                    if tc.function and tc.function.arguments:
                        yield ProviderEvent(
                            type=ProviderEventType.CONTENT_BLOCK_DELTA,
                            index=idx + 1,
                            block_type="tool_use",
                            partial_json=tc.function.arguments,
                        )

            # Finish reason
            if choice.finish_reason:
                # Close any open blocks
                if current_tool_index == -1:
                    yield ProviderEvent(
                        type=ProviderEventType.CONTENT_BLOCK_STOP, index=0
                    )

                stop_reason = {
                    "stop": "end_turn",
                    "length": "max_tokens",
                    "tool_calls": "tool_use",
                }.get(choice.finish_reason, choice.finish_reason)

                yield ProviderEvent(
                    type=ProviderEventType.MESSAGE_DELTA,
                    stop_reason=stop_reason,
                    usage=MessageUsage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    ),
                )

        yield ProviderEvent(type=ProviderEventType.MESSAGE_STOP)

    def _convert_message(self, msg: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
        """Convert Anthropic-format message to OpenAI format.

        May return a list when a single Anthropic message maps to multiple
        OpenAI messages (e.g. multiple tool results).
        """
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            return {"role": role, "content": content}

        if not isinstance(content, list):
            return {"role": role, "content": str(content)}

        # Check if it contains tool results (from tool_result blocks)
        tool_results = [
            b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_result"
        ]
        if tool_results:
            return [
                {
                    "role": "tool",
                    "tool_call_id": tr.get("tool_use_id", ""),
                    "content": str(tr.get("content", "")),
                }
                for tr in tool_results
            ]

        # Check for tool_use blocks (assistant with tool calls)
        tool_uses = [
            b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if tool_uses:
            text_parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            return {
                "role": "assistant",
                "content": "\n".join(text_parts) if text_parts else None,
                "tool_calls": [
                    {
                        "id": tu.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tu.get("name", ""),
                            "arguments": (
                                __import__("json").dumps(tu.get("input", {}))
                            ),
                        },
                    }
                    for tu in tool_uses
                ],
            }

        # Regular text blocks — concatenate
        text = "\n".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in content
            if not isinstance(b, dict) or b.get("type") in ("text", None)
        )
        return {"role": role, "content": text}

    def count_tokens(self, messages: list[dict[str, Any]], model: str) -> int:
        import json
        return max(1, len(json.dumps(messages)) // 4)

    def get_context_window(self, model: str) -> int:
        # OpenRouter models vary; return a safe default
        return DEFAULT_CONTEXT_WINDOW
