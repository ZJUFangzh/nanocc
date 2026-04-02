"""Tool base class and helpers.

Tools implement execute() + check_permissions(). The base class provides
sensible defaults so most tools only override what they need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanocc.types import PermissionBehavior, PermissionResult, ToolResult, ToolUseContext


class BaseTool:
    """Base class for nanocc tools. Subclass and override execute()."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {}
    is_read_only: bool = False

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionResult:
        """Default: allow everything. Override for dangerous tools."""
        return PermissionResult(behavior=PermissionBehavior.ALLOW)

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        """Execute the tool. Must be overridden."""
        raise NotImplementedError

    def is_concurrency_safe(self, input: dict[str, Any]) -> bool:
        """Can this tool call run concurrently with others?
        Default: same as is_read_only."""
        return self.is_read_only

    def get_tool_schema(self) -> dict[str, Any]:
        """Return the tool schema for the API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
