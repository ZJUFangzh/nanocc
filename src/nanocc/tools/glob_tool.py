"""GlobTool — fast file pattern matching."""

from __future__ import annotations

import glob as glob_mod
import os
from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class GlobTool(BaseTool):
    name = "Glob"
    description = "Find files matching a glob pattern. Returns paths sorted by modification time."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": 'Glob pattern (e.g. "**/*.py", "src/**/*.ts").',
            },
            "path": {
                "type": "string",
                "description": "Directory to search in. Default: cwd.",
            },
        },
        "required": ["pattern"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        pattern = input.get("pattern", "")
        base_path = input.get("path", "") or context.cwd

        if not os.path.isabs(base_path):
            base_path = os.path.join(context.cwd, base_path)

        search_pattern = os.path.join(base_path, pattern)

        try:
            matches = glob_mod.glob(search_pattern, recursive=True)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)

        # Sort by modification time (newest first)
        try:
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        except OSError:
            matches.sort()

        # Limit results
        max_results = 100
        truncated = len(matches) > max_results
        matches = matches[:max_results]

        if not matches:
            return ToolResult(content=f"No files matched pattern: {pattern}")

        content = "\n".join(matches)
        if truncated:
            content += f"\n\n... (showing first {max_results} of {len(matches)} results)"

        return ToolResult(content=content)
