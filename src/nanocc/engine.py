"""QueryEngine — stateful session container.

Wraps query() with persistent state across multiple user turns:
- mutableMessages survives across turns
- Tracks usage/cost
- Manages abort controller lifecycle
- Triggers memory extraction after each turn
- Supports session suspend/resume
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from nanocc.compact.auto_compact import AutoCompactTracking
from nanocc.context import build_system_prompt, system_prompt_to_text
from nanocc.memory.claude_md import load_claude_md
from nanocc.memory.memdir import build_memory_prompt
from nanocc.memory.session_memory import SessionMemory
from nanocc.memory.extract import build_extract_prompt, parse_extract_response
from nanocc.messages import create_user_message, from_api_messages, to_api_messages
from nanocc.providers.base import LLMProvider
from nanocc.query import query
from nanocc.tools.base import BaseTool
from nanocc.tools.registry import get_all_tools
from nanocc.types import (
    AssistantMessage,
    Message,
    QueryParams,
    StreamEvent,
    Terminal,
    TerminalReason,
    ToolResultBlock,
    ToolUseBlock,
    ToolUseContext,
)
from nanocc.utils.abort import AbortController
from nanocc.utils.cost import UsageTracker
from nanocc.utils.tokens import token_count_with_estimation

logger = logging.getLogger(__name__)


@dataclass
class QueryEngineConfig:
    provider: LLMProvider
    model: str
    cwd: str = "."
    tools: list[BaseTool] | None = None
    system_prompt: str = ""
    max_turns: int = 0
    max_tokens: int = 16_384
    assistant_mode: bool = False
    session_id: str = ""


class QueryEngine:
    """Stateful session container — the main interface for SDK, CLI, and Channels."""

    def __init__(self, config: QueryEngineConfig) -> None:
        self.config = config
        self.session_id = config.session_id or str(uuid.uuid4())[:8]
        self.cwd = os.path.abspath(config.cwd)

        # Persistent state
        self.messages: list[Message] = []
        self.tools = config.tools or get_all_tools()
        self.usage = UsageTracker()
        self.session_memory = SessionMemory()
        self.compact_tracking = AutoCompactTracking()
        self._abort: AbortController | None = None

    async def submit_message(
        self, prompt: str | list[Any],
    ) -> AsyncGenerator[StreamEvent | Message | Terminal, None]:
        """Submit a user message and stream the response.

        This is the main entry point — CLI, SDK, and Channels all call this.
        """
        # Create user message
        if isinstance(prompt, str):
            user_msg = create_user_message(prompt)
        else:
            from nanocc.messages import create_user_message_with_blocks
            user_msg = create_user_message_with_blocks(prompt)

        self.messages.append(user_msg)

        # Build system prompt with context
        system_blocks = self._build_system_prompt()

        # Fresh abort controller per turn
        self._abort = AbortController()

        tool_context = ToolUseContext(
            cwd=self.cwd,
            tools=self.tools,
            messages=self.messages,
            model=self.config.model,
            abort_controller=self._abort,
            options={
                "provider": self.config.provider,
                "system_prompt": self.config.system_prompt,
            },
        )

        params = QueryParams(
            messages=self.messages,
            system_prompt=system_blocks,
            provider=self.config.provider,
            model=self.config.model,
            tools=self.tools,
            abort_controller=self._abort,
            max_turns=self.config.max_turns,
            max_tokens=self.config.max_tokens,
            tool_use_context=tool_context,
            assistant_mode=self.config.assistant_mode,
            proactive_engine=getattr(self, 'proactive_engine', None),
        )

        # Track tool calls for session memory
        tool_calls_this_turn = 0

        async for event in query(params):
            if isinstance(event, AssistantMessage):
                # Track usage
                if event.usage:
                    self.usage.add(
                        input_tokens=event.usage.input_tokens,
                        output_tokens=event.usage.output_tokens,
                        cache_creation=event.usage.cache_creation_input_tokens,
                        cache_read=event.usage.cache_read_input_tokens,
                    )
                # Count tool uses
                tool_calls_this_turn += sum(
                    1 for b in event.content if isinstance(b, ToolUseBlock)
                )

            yield event

            if isinstance(event, Terminal):
                break

        # Post-turn: check session memory update
        current_tokens = token_count_with_estimation(self.messages)
        if self.session_memory.should_update(current_tokens, tool_calls_this_turn):
            logger.debug("Session memory update triggered")
            self.session_memory.tool_calls_since_update = 0

        # Post-turn: extract memories (background, fire-and-forget)
        import asyncio
        extract_prompt = build_extract_prompt(self.messages)
        if extract_prompt:
            asyncio.create_task(self._run_extract(extract_prompt))

    def abort(self) -> None:
        """Abort the current query."""
        if self._abort:
            self._abort.abort()

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        self.session_memory = SessionMemory()
        self.compact_tracking = AutoCompactTracking()

    def _build_system_prompt(self) -> list[dict[str, Any]]:
        """Build full system prompt with all context layers."""
        user_context: dict[str, str] = {}

        # CLAUDE.md
        claude_md = load_claude_md(self.cwd)
        if claude_md:
            user_context["Project Instructions"] = claude_md

        # Memory
        memory = build_memory_prompt(self.cwd)
        if memory:
            user_context["Memory"] = memory

        # Session memory
        sm = self.session_memory.get_prompt()
        if sm:
            user_context["Session Memory"] = sm

        # System context
        system_context: dict[str, str] = {}

        return build_system_prompt(
            base_prompt=self.config.system_prompt or "",
            user_context=user_context if user_context else None,
            system_context=system_context if system_context else None,
            cwd=self.cwd,
        )

    def get_state(self) -> dict[str, Any]:
        """Serialize engine state for session persistence."""
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "model": self.config.model,
            "messages": to_api_messages(self.messages),
            "usage": {
                "input": self.usage.total_input_tokens,
                "output": self.usage.total_output_tokens,
                "api_calls": self.usage.api_calls,
            },
            "session_memory": self.session_memory.content,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore engine state from a serialized dict (for --continue)."""
        # Restore messages
        api_msgs = state.get("messages", [])
        self.messages = from_api_messages(api_msgs)

        # Restore usage
        usage_data = state.get("usage", {})
        self.usage.total_input_tokens = usage_data.get("input", 0)
        self.usage.total_output_tokens = usage_data.get("output", 0)
        self.usage.api_calls = usage_data.get("api_calls", 0)

        # Restore session memory
        sm_content = state.get("session_memory", "")
        if sm_content:
            self.session_memory.content = sm_content
            self.session_memory.initialized = True

        # Restore cwd
        if state.get("cwd"):
            self.cwd = state["cwd"]

        # Restore session id
        if state.get("session_id"):
            self.session_id = state["session_id"]

        logger.info("Engine state restored: session=%s, %d messages",
                     self.session_id, len(self.messages))

    async def _run_extract(self, prompt: str) -> None:
        """Background memory extraction via LLM side-query."""
        try:
            # Use a non-streaming single-shot call to the provider
            from nanocc.messages import to_api_system_prompt
            response_text = ""
            async for event in self.config.provider.stream(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=to_api_system_prompt("You are a memory extraction assistant."),
                tools=[],
                model=self.config.model,
                max_tokens=1024,
            ):
                if event.text:
                    response_text += event.text

            result = parse_extract_response(response_text)
            if result:
                from nanocc.utils.config import get_memory_dir
                memory_dir = get_memory_dir(self.cwd)
                # Write memory file
                filename = f"{result['type']}_{result['name'].replace(' ', '_').lower()}.md"
                filepath = memory_dir / filename
                content = f"---\nname: {result['name']}\ndescription: {result['description']}\ntype: {result['type']}\n---\n\n{result['content']}"
                filepath.write_text(content, encoding="utf-8")
                logger.info("Extracted memory: %s -> %s", result['name'], filename)
        except Exception as e:
            logger.debug("Memory extraction failed (non-critical): %s", e)
