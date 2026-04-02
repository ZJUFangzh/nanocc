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
        """Connect to the MCP server."""
        transport = self.config.transport or "stdio"

        if transport == "http":
            return await self._connect_http()
        elif transport == "sse":
            return await self._connect_sse()
        elif transport != "stdio" or not self.config.command:
            logger.warning("Unsupported transport '%s' for %s", transport, self.server_name)
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
        if hasattr(self, '_http_client'):
            await self._http_client.aclose()
            self._connected = False
            return

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
        # Use HTTP if connected via HTTP/SSE transport
        if hasattr(self, '_http_client'):
            return await self._http_request(method, params)

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

    async def list_resources(self) -> list[MCPResource]:
        """List resources from the MCP server."""
        if not self._connected:
            return []

        if self._resources:
            return self._resources

        resp = await self._send_request("resources/list", {})
        if resp and "resources" in resp:
            for r in resp["resources"]:
                self._resources.append(MCPResource(
                    uri=r.get("uri", ""),
                    name=r.get("name", ""),
                    description=r.get("description", ""),
                ))

        return self._resources

    async def read_resource(self, uri: str) -> str:
        """Read a resource by URI."""
        if not self._connected:
            return "Error: Not connected to MCP server"

        resp = await self._send_request("resources/read", {"uri": uri})
        if not resp:
            return "Error: No response from MCP server"

        contents = resp.get("contents", [])
        parts = []
        for item in contents:
            if isinstance(item, dict):
                text = item.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts) if parts else json.dumps(resp)

    async def _connect_http(self) -> bool:
        """Connect via HTTP transport (JSON-RPC over HTTP POST)."""
        if not self.config.url:
            logger.error("MCP %s: HTTP transport requires url", self.server_name)
            return False

        try:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=30)
            self._http_url = self.config.url

            # Initialize
            resp = await self._http_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nanocc", "version": "0.1.0"},
            })
            if resp:
                await self._http_request("notifications/initialized", {}, is_notification=True)
                self._connected = True

                # Discover tools
                tools_resp = await self._http_request("tools/list", {})
                if tools_resp and "tools" in tools_resp:
                    for t in tools_resp["tools"]:
                        self._tools.append(MCPToolSchema(
                            name=t.get("name", ""),
                            description=t.get("description", ""),
                            input_schema=t.get("inputSchema", {}),
                        ))

                logger.info("MCP %s (HTTP): connected, %d tools", self.server_name, len(self._tools))
                return True

        except Exception as e:
            logger.error("MCP %s HTTP connect failed: %s", self.server_name, e)
        return False

    async def _connect_sse(self) -> bool:
        """Connect via SSE transport (Server-Sent Events)."""
        if not self.config.url:
            logger.error("MCP %s: SSE transport requires url", self.server_name)
            return False

        try:
            import httpx

            # SSE: first GET to establish endpoint, then POST for messages
            self._http_client = httpx.AsyncClient(timeout=60)
            self._http_url = self.config.url

            # For SSE, the server sends events and we POST requests
            # Use the /message endpoint convention
            base = self.config.url.rstrip("/")
            self._http_url = f"{base}/message"

            resp = await self._http_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nanocc", "version": "0.1.0"},
            })
            if resp:
                await self._http_request("notifications/initialized", {}, is_notification=True)
                self._connected = True

                tools_resp = await self._http_request("tools/list", {})
                if tools_resp and "tools" in tools_resp:
                    for t in tools_resp["tools"]:
                        self._tools.append(MCPToolSchema(
                            name=t.get("name", ""),
                            description=t.get("description", ""),
                            input_schema=t.get("inputSchema", {}),
                        ))

                logger.info("MCP %s (SSE): connected, %d tools", self.server_name, len(self._tools))
                return True

        except Exception as e:
            logger.error("MCP %s SSE connect failed: %s", self.server_name, e)
        return False

    async def _http_request(
        self, method: str, params: dict, *, is_notification: bool = False,
    ) -> dict | None:
        """Send a JSON-RPC request over HTTP."""
        if not hasattr(self, '_http_client') or not hasattr(self, '_http_url'):
            return None

        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if not is_notification:
            self._request_id += 1
            payload["id"] = self._request_id

        try:
            resp = await self._http_client.post(self._http_url, json=payload)
            if is_notification:
                return {}
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result")
        except Exception as e:
            logger.error("MCP %s HTTP request error: %s", self.server_name, e)
        return None

    async def _send_notification(self, method: str, params: dict) -> None:
        if hasattr(self, '_http_client'):
            await self._http_request(method, params, is_notification=True)
            return

        if not self._process or not self._process.stdin:
            return
        notif = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            data = json.dumps(notif) + "\n"
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()
        except Exception:
            pass
