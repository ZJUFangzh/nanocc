"""Wrap MCP server tools as nanocc Tool instances."""

from __future__ import annotations

from typing import Any

from nanocc.constants import MCP_MAX_RESULT_CHARS
from nanocc.mcp.client import MCPClient, MCPToolSchema
from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class MCPToolWrapper(BaseTool):
    """Wraps a single MCP tool as a nanocc BaseTool."""

    is_read_only = True  # Conservative default

    def __init__(self, client: MCPClient, schema: MCPToolSchema) -> None:
        self._client = client
        self.name = f"mcp__{client.server_name}__{schema.name}"
        self.description = schema.description or f"MCP tool: {schema.name}"
        self.input_schema = schema.input_schema or {"type": "object", "properties": {}}

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        try:
            result = await self._client.call_tool(
                self.name.split("__")[-1],  # Extract original tool name
                input,
            )
            # Truncate oversized results
            if len(result) > MCP_MAX_RESULT_CHARS:
                result = result[:MCP_MAX_RESULT_CHARS] + "\n... [truncated]"
            return ToolResult(content=result)
        except Exception as e:
            return ToolResult(content=f"MCP tool error: {e}", is_error=True)


def wrap_mcp_tools(client: MCPClient) -> list[BaseTool]:
    """Wrap all tools from an MCP client as nanocc tools."""
    tools: list[BaseTool] = []
    for schema in client._tools:
        tools.append(MCPToolWrapper(client, schema))
    return tools
