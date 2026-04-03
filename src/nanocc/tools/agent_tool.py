"""AgentTool — spawn a sub-agent for complex, multi-step tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from nanocc.agents.fork import fork_agent
from nanocc.constants import SUBAGENT_TIMEOUT_SECONDS
from nanocc.messages import get_text_content
from nanocc.tools.base import BaseTool
from nanocc.types import AssistantMessage, Terminal, ToolResult, ToolUseContext


class AgentTool(BaseTool):
    name = "Agent"
    description = "Launch a sub-agent to handle a complex task autonomously. The sub-agent has access to the same tools."
    is_read_only = True  # The agent itself is read-only; it spawns tools internally
    input_schema = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task for the sub-agent to perform.",
            },
            "model": {
                "type": "string",
                "description": "Optional model override for the sub-agent.",
            },
        },
        "required": ["prompt"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        prompt = input.get("prompt", "")
        model = input.get("model", "") or context.model

        # Get provider from context options
        provider = context.options.get("provider")
        if not provider:
            return ToolResult(content="Error: No provider available for sub-agent", is_error=True)

        system_prompt = context.options.get("system_prompt", "You are a helpful sub-agent.")

        collected_text = ""

        async def _run_agent() -> str:
            text = ""
            async for event in fork_agent(
                prompt=prompt,
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                tools=context.tools,
                cwd=context.cwd,
                max_turns=10,
                parent_abort=context.abort_controller,
            ):
                if isinstance(event, AssistantMessage):
                    t = get_text_content(event)
                    if t:
                        text = t
                elif isinstance(event, Terminal):
                    break
            return text

        try:
            collected_text = await asyncio.wait_for(
                _run_agent(), timeout=SUBAGENT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                content=f"Sub-agent timed out after {SUBAGENT_TIMEOUT_SECONDS}s",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(content=f"Sub-agent error: {e}", is_error=True)

        return ToolResult(content=collected_text or "(Sub-agent produced no output)")
