"""MCP server configuration loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanocc.utils.config import load_settings


@dataclass
class MCPServerConfig:
    name: str
    command: str = ""         # stdio transport
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""             # http/sse transport
    transport: str = "stdio"  # "stdio", "http", "sse"


def load_mcp_config(cwd: str) -> dict[str, MCPServerConfig]:
    """Load MCP server configs from settings.json."""
    settings = load_settings(cwd)
    servers: dict[str, MCPServerConfig] = {}

    for name, cfg in settings.get("mcpServers", {}).items():
        servers[name] = MCPServerConfig(
            name=name,
            command=cfg.get("command", ""),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
            url=cfg.get("url", ""),
            transport=cfg.get("transport", "stdio"),
        )

    return servers
