"""Brief tool — structured message output for Assistant mode.

Instead of streaming text directly, Assistant mode sends messages
through this tool, enabling Channel adapters to format and route them.
"""

from __future__ import annotations

from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class BriefTool(BaseTool):
    name = "Brief"
    description = "Send a structured message to the user. Use in Assistant mode for notifications and updates."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Message content (markdown supported).",
            },
            "status": {
                "type": "string",
                "enum": ["normal", "proactive"],
                "description": "Message type. 'proactive' for self-initiated messages.",
            },
        },
        "required": ["message"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        message = input.get("message", "")
        status = input.get("status", "normal")

        # In CLI mode: just return the message content
        # Channel mode: the channel adapter intercepts and routes
        brief_handler = context.options.get("brief_handler")
        if brief_handler:
            await brief_handler(message, status)
            return ToolResult(content=f"[Brief sent: {status}]")

        return ToolResult(content=message)


class SleepTool(BaseTool):
    """Proactive mode: agent declares it has nothing useful to do."""

    name = "Sleep"
    description = "Declare that there's nothing useful to do right now. Required when tick-woken with no work."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "duration": {
                "type": "integer",
                "description": "Sleep duration in seconds.",
            },
        },
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        import asyncio
        duration = min(input.get("duration", 60), 300)
        await asyncio.sleep(duration)
        return ToolResult(content="Woke up")
