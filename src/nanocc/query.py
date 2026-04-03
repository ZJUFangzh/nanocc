"""Agent loop — async generator state machine.

Faithfully replicates Claude Code's query() pattern:
  while True:
    1. context governance (compact, budget) — Phase 3
    2. LLM stream
    3. abort check
    4. tool execution — Phase 2
    5. end_turn → Terminal

"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from nanocc.compact.auto_compact import AutoCompactTracking, auto_compact_if_needed
from nanocc.compact.micro_compact import micro_compact
from nanocc.compact.tool_result_budget import apply_tool_result_budget
from nanocc.messages import create_assistant_message, create_tick_message, create_user_message_with_blocks, to_api_messages, to_api_system_prompt
from nanocc.tools.orchestration import run_tools
from nanocc.providers.base import LLMProvider, ProviderEvent, ProviderEventType
from nanocc.hooks.types import HookEvent
from nanocc.types import (
    AssistantMessage,
    ContentBlock,
    LoopState,
    Message,
    MessageUsage,
    QueryParams,
    StreamEvent,
    StreamEventType,
    Terminal,
    TerminalReason,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolUseContext,
)
from nanocc.utils.abort import AbortController

logger = logging.getLogger(__name__)


async def query(
    params: QueryParams,
) -> AsyncGenerator[StreamEvent | Message, None]:
    """The core agent loop. Yields streaming events and messages.

    The return value (Terminal) is yielded as the final item — callers should
    check for Terminal instances to detect loop completion.

    Phase 1: streams text only, no tool execution.
    """
    abort = params.abort_controller or AbortController()
    tool_use_context = params.tool_use_context or ToolUseContext(
        abort_controller=abort, model=params.model
    )

    state = LoopState(
        messages=params.messages,
        tool_use_context=tool_use_context,
    )
    compact_tracking = state.auto_compact_tracking or AutoCompactTracking()
    state.auto_compact_tracking = compact_tracking

    system_prompt = params.system_prompt
    if isinstance(system_prompt, str):
        system_prompt = to_api_system_prompt(system_prompt)

    turn = 0
    while True:
        turn += 1
        if params.max_turns and turn > params.max_turns:
            yield Terminal(reason=TerminalReason.MAX_TURNS)
            return

        # ── 1. Context governance pipeline ──────────────────────────────
        # Layer 1: truncate oversized tool results
        apply_tool_result_budget(state.messages)

        # Layer 2: clear old tool results
        micro_compact(state.messages)

        # Layer 3: auto compact if context is nearly full
        context_window = params.provider.get_context_window(params.model)
        compacted = await auto_compact_if_needed(
            state.messages, params.provider, params.model,
            context_window, compact_tracking, turn,
        )
        if compacted is not None:
            state.messages.clear()
            state.messages.extend(compacted)

        # ── 2. Build API messages and stream ────────────────────────────
        api_messages = to_api_messages(state.messages)

        # Build tool schemas for API
        tool_schemas: list[dict[str, Any]] = []
        for tool in params.tools:
            tool_schemas.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            })

        # Accumulate content blocks from the stream
        acc = _BlockAccumulator()
        msg_usage: MessageUsage | None = None
        stop_reason: str | None = None
        model_name: str = ""

        try:
            async for event in params.provider.stream(
                messages=api_messages,
                system_prompt=system_prompt,
                tools=tool_schemas,
                model=params.model,
                max_tokens=params.max_tokens,
            ):
                # Yield normalized stream event for UI rendering
                stream_event = _provider_to_stream_event(event)
                if stream_event:
                    yield stream_event

                # Accumulate content blocks
                acc.process(event)

                # Track usage
                if event.usage:
                    msg_usage = event.usage
                if event.stop_reason:
                    stop_reason = event.stop_reason
                if event.model:
                    model_name = event.model

                # Abort check mid-stream
                if abort.is_aborted:
                    break

        except Exception as e:
            logger.error("Provider stream error: %s", e)
            yield Terminal(reason=TerminalReason.MODEL_ERROR, error=str(e))
            return

        # ── 3. Abort check ──────────────────────────────────────────────
        if abort.is_aborted:
            acc.finalize()
            assistant_msg = create_assistant_message(
                acc.blocks, model=model_name,
                stop_reason="aborted", usage=msg_usage,
            )
            state.messages.append(assistant_msg)
            yield assistant_msg
            yield Terminal(reason=TerminalReason.ABORTED_STREAMING)
            return

        acc.finalize()

        # ── 4. Build assistant message ──────────────────────────────────
        assistant_msg = create_assistant_message(
            acc.blocks,
            model=model_name,
            stop_reason=stop_reason,
            usage=msg_usage,
        )
        state.messages.append(assistant_msg)
        yield assistant_msg

        # ── 5. Tool execution ───────────────────────────────────────────
        tool_use_blocks = [
            b for b in acc.blocks if isinstance(b, ToolUseBlock)
        ]

        if not tool_use_blocks:
            # Fire stop hook before completing
            if state.hook_engine:
                await state.hook_engine.fire(HookEvent.STOP)

            # Assistant mode: wait for tick or new user input instead of returning
            if params.assistant_mode and params.proactive_engine:
                from nanocc.assistant.proactive import WakeReason
                wake = await params.proactive_engine.wait_for_next()
                if wake.reason == WakeReason.TICK:
                    state.messages.append(create_tick_message())
                    continue
                elif wake.reason == WakeReason.USER_MESSAGE:
                    state.messages.append(wake.data)
                    continue
                # WakeReason.SHUTDOWN → fall through to return

            yield Terminal(reason=TerminalReason.COMPLETED)
            return

        if not params.tools:
            # Model tried to use tools but none are available
            if state.hook_engine:
                await state.hook_engine.fire(HookEvent.STOP)
            yield Terminal(reason=TerminalReason.COMPLETED)
            return

        # Execute tools (concurrent reads, serial writes) with hook engine
        tool_results = await run_tools(
            tool_use_blocks, params.tools, state.tool_use_context,
            hook_engine=state.hook_engine,
        )

        # Yield each result for UI rendering
        for result_block in tool_results:
            yield result_block

        # Append tool results as a user message (Anthropic API convention)
        tool_result_msg = create_user_message_with_blocks(tool_results)  # type: ignore[arg-type]
        state.messages.append(tool_result_msg)

        # Check abort after tool execution
        if abort.is_aborted:
            yield Terminal(reason=TerminalReason.ABORTED_TOOLS)
            return

        state.turn_count += 1
        # Continue the loop — model will see tool results and respond


def _provider_to_stream_event(event: ProviderEvent) -> StreamEvent | None:
    """Map ProviderEvent to StreamEvent for the UI layer."""
    type_map = {
        ProviderEventType.MESSAGE_START: StreamEventType.MESSAGE_START,
        ProviderEventType.MESSAGE_DELTA: StreamEventType.MESSAGE_DELTA,
        ProviderEventType.MESSAGE_STOP: StreamEventType.MESSAGE_STOP,
        ProviderEventType.CONTENT_BLOCK_START: StreamEventType.CONTENT_BLOCK_START,
        ProviderEventType.CONTENT_BLOCK_DELTA: StreamEventType.CONTENT_BLOCK_DELTA,
        ProviderEventType.CONTENT_BLOCK_STOP: StreamEventType.CONTENT_BLOCK_STOP,
    }

    stream_type = type_map.get(event.type)
    if stream_type is None:
        return None

    return StreamEvent(
        type=stream_type,
        index=event.index,
        block_type=event.block_type,
        tool_name=event.tool_name,
        usage=event.usage,
        stop_reason=event.stop_reason,
        delta={"text": event.text} if event.text else None,
    )


class _BlockAccumulator:
    """Accumulates streaming deltas into content blocks."""

    def __init__(self) -> None:
        self.blocks: list[ContentBlock] = []
        self._type: str = ""
        self._text: str = ""
        self._thinking: str = ""
        self._thinking_sig: str = ""
        self._tool_id: str = ""
        self._tool_name: str = ""
        self._tool_json: str = ""

    def process(self, event: ProviderEvent) -> None:
        if event.type == ProviderEventType.CONTENT_BLOCK_START:
            self._flush()
            self._type = event.block_type
            self._text = ""
            self._thinking = ""
            self._thinking_sig = ""
            self._tool_id = event.tool_use_id
            self._tool_name = event.tool_name
            self._tool_json = ""

        elif event.type == ProviderEventType.CONTENT_BLOCK_DELTA:
            if event.block_type == "text":
                self._text += event.text
            elif event.block_type == "thinking":
                if event.text:
                    self._thinking += event.text
                if event.signature:
                    self._thinking_sig += event.signature
            elif event.block_type == "tool_use":
                self._tool_json += event.partial_json

        elif event.type == ProviderEventType.CONTENT_BLOCK_STOP:
            self._flush()

    def finalize(self) -> None:
        self._flush()

    def _flush(self) -> None:
        if not self._type:
            return
        if self._type == "text" and self._text:
            self.blocks.append(TextBlock(text=self._text))
        elif self._type == "thinking" and self._thinking:
            self.blocks.append(
                ThinkingBlock(thinking=self._thinking, signature=self._thinking_sig)
            )
        elif self._type == "tool_use" and self._tool_id:
            try:
                tool_input = json.loads(self._tool_json) if self._tool_json else {}
            except json.JSONDecodeError:
                tool_input = {}
            self.blocks.append(
                ToolUseBlock(id=self._tool_id, name=self._tool_name, input=tool_input)
            )
        self._type = ""
