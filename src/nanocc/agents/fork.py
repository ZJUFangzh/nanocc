"""Forked sub-agent — runs query() with inherited context.

CacheSafeParams: inherits parent's system prompt/tools but gets
isolated message history and abort controller.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from nanocc.messages import create_user_message
from nanocc.providers.base import LLMProvider
from nanocc.query import query
from nanocc.tools.base import BaseTool
from nanocc.types import (
    Message,
    QueryParams,
    StreamEvent,
    Terminal,
    TerminalReason,
    ToolUseContext,
)
from nanocc.utils.abort import AbortController

logger = logging.getLogger(__name__)


async def fork_agent(
    prompt: str,
    provider: LLMProvider,
    model: str,
    system_prompt: str | list[dict[str, Any]],
    tools: list[BaseTool],
    cwd: str = ".",
    max_turns: int = 10,
    parent_abort: AbortController | None = None,
) -> AsyncGenerator[StreamEvent | Message | Terminal, None]:
    """Fork a sub-agent with inherited context but isolated state.

    The sub-agent gets:
    - Same provider, model, system prompt, tools (CacheSafeParams)
    - Fresh message history (just the prompt)
    - Own abort controller (linked to parent)
    """
    abort = AbortController()

    # Link to parent abort
    if parent_abort:
        parent_abort.on_abort(abort.abort)

    tool_context = ToolUseContext(
        cwd=cwd,
        tools=tools,
        model=model,
        abort_controller=abort,
        options={
            "provider": provider,
            "system_prompt": system_prompt,
        },
    )

    params = QueryParams(
        messages=[create_user_message(prompt)],
        system_prompt=system_prompt,
        provider=provider,
        model=model,
        tools=tools,
        abort_controller=abort,
        max_turns=max_turns,
        tool_use_context=tool_context,
    )

    async for event in query(params):
        yield event
