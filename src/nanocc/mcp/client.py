"""MCP client — connect to MCP servers, discover tools and resources."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from nanocc.mcp.config import MCPServerConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPToolSchema:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResource:
    uri: str
    name: str = ""
    description: str = ""


class MCPClient:
    """Connect to a single MCP server and discover tools/resources."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.server_name = config.name
        self._process: asyncio.subprocess.Process | None = None
        self._tools: list[MCPToolSchema] = []
        self._resources: list[MCPResource] = []
        self._connected = False
        self._request_id = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> bool:
        """Connect to the MCP server via stdio transport."""
        if self.config.transport != "stdio" or not self.config.command:
            logger.warning("Only stdio transport supported currently for %s", self.server_name)
            return False

        try:
            import os
            env = {**os.environ, **self.config.env}
            self._process = await asyncio.create_subprocess_exec(
                self.config.command, *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._connected = True

            # Initialize
            resp = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nanocc", "version": "0.1.0"},
            })
            if resp:
                await self._send_notification("notifications/initialized", {})

            # Discover tools
            tools_resp = await self._send_request("tools/list", {})
            if tools_resp and "tools" in tools_resp:
                for t in tools_resp["tools"]:
                    self._tools.append(MCPToolSchema(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                    ))

            logger.info("MCP %s: connected, %d tools", self.server_name, len(self._tools))
            return True

        except Exception as e:
            logger.error("MCP %s connect failed: %s", self.server_name, e)
            return False

    async def disconnect(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._connected = False

    async def list_tools(self) -> list[MCPToolSchema]:
        return self._tools

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        """Call an MCP tool and return result as string."""
        if not self._connected:
            return "Error: Not connected to MCP server"

        resp = await self._send_request("tools/call", {
            "name": name,
            "arguments": args,
        })

        if not resp:
            return "Error: No response from MCP server"

        # Extract text content from response
        content = resp.get("content", [])
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else json.dumps(resp)

    async def _send_request(self, method: str, params: dict) -> dict | None:
        """Send a JSON-RPC request and wait for response."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            data = json.dumps(request) + "\n"
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()

            # Read response line
            line = await asyncio.wait_for(
                self._process.stdout.readline(), timeout=30
            )
            if line:
                resp = json.loads(line.decode())
                return resp.get("result")
        except Exception as e:
            logger.error("MCP %s request error: %s", self.server_name, e)

        return None

    async def _send_notification(self, method: str, params: dict) -> None:
        if not self._process or not self._process.stdin:
            return
        notif = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            data = json.dumps(notif) + "\n"
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()
        except Exception:
            pass
