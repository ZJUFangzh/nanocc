"""AskUserTool — ask the user a question during execution."""

from __future__ import annotations

from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class AskUserTool(BaseTool):
    name = "AskUser"
    description = "Ask the user a question to gather preferences, clarify requirements, or get decisions."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to ask the user.",
            },
        },
        "required": ["question"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        question = input.get("question", "")

        # In CLI mode, this will be handled by the UI layer
        # The tool returns the question; the CLI intercepts and prompts
        ask_handler = context.options.get("ask_handler")
        if ask_handler:
            answer = await ask_handler(question)
            return ToolResult(content=f"User answered: {answer}")

        # Fallback: return the question as the result
        # The UI layer should intercept this tool before execution
        return ToolResult(content=f"[Question for user: {question}]")
