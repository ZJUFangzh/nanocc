"""Tests for MCP — client, config, tool_wrapper."""

from __future__ import annotations

import pytest

from nanocc.mcp.client import MCPClient, MCPResource, MCPToolSchema
from nanocc.mcp.config import MCPServerConfig, load_mcp_config


# ── MCPServerConfig ──

def test_config_defaults():
    config = MCPServerConfig(name="test")
    assert config.transport == "stdio"
    assert config.command == ""
    assert config.url == ""
    assert config.args == []
    assert config.env == {}


def test_config_http():
    config = MCPServerConfig(name="test", transport="http", url="http://localhost:8080")
    assert config.transport == "http"
    assert config.url == "http://localhost:8080"


# ── MCPClient init ──

def test_client_init_stdio():
    config = MCPServerConfig(name="test-stdio", command="echo", args=["hello"])
    client = MCPClient(config)
    assert client.server_name == "test-stdio"
    assert not client._connected


def test_client_init_http():
    config = MCPServerConfig(name="test-http", transport="http", url="http://localhost:9999")
    client = MCPClient(config)
    assert client.server_name == "test-http"


def test_client_init_sse():
    config = MCPServerConfig(name="test-sse", transport="sse", url="http://localhost:9998")
    client = MCPClient(config)
    assert client.server_name == "test-sse"


# ── MCPClient methods when not connected ──

@pytest.mark.asyncio
async def test_client_call_tool_not_connected():
    config = MCPServerConfig(name="test")
    client = MCPClient(config)
    result = await client.call_tool("test", {})
    assert "Not connected" in result


@pytest.mark.asyncio
async def test_client_list_tools_not_connected():
    config = MCPServerConfig(name="test")
    client = MCPClient(config)
    tools = await client.list_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_client_list_resources_not_connected():
    config = MCPServerConfig(name="test")
    client = MCPClient(config)
    resources = await client.list_resources()
    assert resources == []


@pytest.mark.asyncio
async def test_client_read_resource_not_connected():
    config = MCPServerConfig(name="test")
    client = MCPClient(config)
    result = await client.read_resource("test://foo")
    assert "Not connected" in result


# ── MCPToolSchema / MCPResource ──

def test_tool_schema():
    schema = MCPToolSchema(name="test_tool", description="A test", input_schema={"type": "object"})
    assert schema.name == "test_tool"
    assert schema.input_schema == {"type": "object"}


def test_resource():
    res = MCPResource(uri="file:///test.txt", name="test", description="A test file")
    assert res.uri == "file:///test.txt"


# ── load_mcp_config ──

def test_load_mcp_config_empty(tmp_path):
    # No settings.json → empty config
    config = load_mcp_config(str(tmp_path))
    assert config == {}


# ── tool_wrapper ──

def test_mcp_tool_wrapper():
    from nanocc.mcp.tool_wrapper import MCPToolWrapper
    schema = MCPToolSchema(
        name="search",
        description="Search the web",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )

    config = MCPServerConfig(name="web")
    client = MCPClient(config)
    tool = MCPToolWrapper(client, schema)

    assert tool.name == "mcp__web__search"
    assert tool.description == "Search the web"
    assert tool.input_schema == schema.input_schema
    assert tool.is_read_only  # MCP tools default to read-only
