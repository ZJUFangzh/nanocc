"""FileEditTool — exact string replacement in files.

Replicates Claude Code's edit pattern:
- old_string must be unique (or use replace_all)
- Preserves file encoding and line endings
"""

from __future__ import annotations

import os
from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import PermissionBehavior, PermissionResult, ToolResult, ToolUseContext


class FileEditTool(BaseTool):
    name = "Edit"
    description = "Perform exact string replacements in a file."
    is_read_only = False
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to edit.",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace.",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace it with.",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences. Default: false.",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionResult:
        return PermissionResult(behavior=PermissionBehavior.ASK, message=input.get("file_path", ""))

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        file_path = input.get("file_path", "")
        old_string = input.get("old_string", "")
        new_string = input.get("new_string", "")
        replace_all = input.get("replace_all", False)

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)

        if not os.path.exists(file_path):
            return ToolResult(content=f"Error: File not found: {file_path}", is_error=True)

        if old_string == new_string:
            return ToolResult(content="Error: old_string and new_string are identical.", is_error=True)

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return ToolResult(content=f"Error reading file: {e}", is_error=True)

        # Count matches
        match_count = content.count(old_string)

        if match_count == 0:
            return ToolResult(
                content=f"Error: old_string not found in {file_path}. Make sure it matches exactly.",
                is_error=True,
            )

        if match_count > 1 and not replace_all:
            return ToolResult(
                content=(
                    f"Error: Found {match_count} matches of old_string in {file_path}. "
                    f"Provide a larger context to make it unique, or set replace_all=true."
                ),
                is_error=True,
            )

        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            replaced = match_count if replace_all else 1
            return ToolResult(
                content=f"Successfully replaced {replaced} occurrence(s) in {file_path}"
            )
        except Exception as e:
            return ToolResult(content=f"Error writing file: {e}", is_error=True)
