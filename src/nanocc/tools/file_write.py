"""FileWriteTool — create or overwrite a file."""

from __future__ import annotations

import os
from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import PermissionBehavior, PermissionResult, ToolResult, ToolUseContext


class FileWriteTool(BaseTool):
    name = "Write"
    description = "Create a new file or completely overwrite an existing file."
    is_read_only = False
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to write.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
        "required": ["file_path", "content"],
    }

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionResult:
        return PermissionResult(behavior=PermissionBehavior.ASK, message=input.get("file_path", ""))

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        file_path = input.get("file_path", "")
        content = input.get("content", "")

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)

        try:
            # Create parent directories
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return ToolResult(content=f"Successfully wrote {line_count} lines to {file_path}")

        except Exception as e:
            return ToolResult(content=f"Error writing file: {e}", is_error=True)
