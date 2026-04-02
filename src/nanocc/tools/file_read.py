"""FileReadTool — read file contents with offset/limit."""

from __future__ import annotations

import os
from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class FileReadTool(BaseTool):
    name = "Read"
    description = "Read a file from the filesystem. Returns content with line numbers."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to read.",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (0-based). Default: 0.",
            },
            "limit": {
                "type": "integer",
                "description": "Number of lines to read. Default: 2000.",
            },
        },
        "required": ["file_path"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        file_path = input.get("file_path", "")
        offset = input.get("offset", 0)
        limit = input.get("limit", 2000)

        # Resolve relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)

        if not os.path.exists(file_path):
            return ToolResult(content=f"Error: File not found: {file_path}", is_error=True)

        if os.path.isdir(file_path):
            return ToolResult(
                content=f"Error: {file_path} is a directory. Use Bash with ls instead.",
                is_error=True,
            )

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return ToolResult(content=f"Error reading file: {e}", is_error=True)

        total_lines = len(lines)
        selected = lines[offset : offset + limit]

        # Format with line numbers (cat -n style, 1-based)
        numbered = []
        for i, line in enumerate(selected, start=offset + 1):
            numbered.append(f"{i}\t{line.rstrip()}")

        content = "\n".join(numbered)

        if offset + limit < total_lines:
            content += f"\n\n... ({total_lines - offset - limit} more lines)"

        return ToolResult(content=content)
