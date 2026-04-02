"""Shared test fixtures — mock provider, tools, hook engine."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nanocc.hooks.engine import HookEngine
from nanocc.hooks.types import Hook, HookEvent
from nanocc.providers.base import ProviderEvent, ProviderEventType
from nanocc.tools.bash import BashTool
from nanocc.tools.file_read import FileReadTool
from nanocc.tools.registry import get_all_tools
from nanocc.types import ToolUseContext
from nanocc.utils.abort import AbortController


class MockProvider:
    """Mock LLM provider that returns pre-scripted responses.

    Usage:
        provider = MockProvider([
            [text_event("hello")],                    # turn 1: text response
            [tool_use_event("Bash", {"command": "ls"})],  # turn 2: tool call
            [text_event("done")],                     # turn 3: text response
        ])
    """

    def __init__(self, turns: list[list[ProviderEvent]] | None = None) -> None:
        self.turns = turns or [[text_events("ok")]]
        self.call_count = 0

    def get_context_window(self, model: str) -> int:
        return 100_000

    async def stream(self, **kwargs: Any):
        idx = min(self.call_count, len(self.turns) - 1)
        self.call_count += 1
        for event in self.turns[idx]:
            yield event


def text_events(text: str) -> list[ProviderEvent]:
    """Generate stream events for a simple text response."""
    return [
        ProviderEvent(type=ProviderEventType.CONTENT_BLOCK_START, block_type="text"),
        ProviderEvent(type=ProviderEventType.CONTENT_BLOCK_DELTA, block_type="text", text=text),
        ProviderEvent(type=ProviderEventType.CONTENT_BLOCK_STOP),
        ProviderEvent(type=ProviderEventType.MESSAGE_STOP, stop_reason="end_turn"),
    ]


def tool_use_events(tool_name: str, tool_input: dict, tool_id: str = "tu1") -> list[ProviderEvent]:
    """Generate stream events for a tool_use response."""
    return [
        ProviderEvent(type=ProviderEventType.CONTENT_BLOCK_START, block_type="tool_use", tool_use_id=tool_id, tool_name=tool_name),
        ProviderEvent(type=ProviderEventType.CONTENT_BLOCK_DELTA, block_type="tool_use", partial_json=json.dumps(tool_input)),
        ProviderEvent(type=ProviderEventType.CONTENT_BLOCK_STOP),
        ProviderEvent(type=ProviderEventType.MESSAGE_STOP, stop_reason="tool_use"),
    ]


@pytest.fixture
def mock_provider():
    return MockProvider([text_events("hello")])


@pytest.fixture
def basic_tools():
    return [BashTool(), FileReadTool()]


@pytest.fixture
def all_tools():
    return get_all_tools()


@pytest.fixture
def abort_controller():
    return AbortController()


@pytest.fixture
def tool_context(basic_tools, abort_controller):
    return ToolUseContext(
        cwd=".",
        tools=basic_tools,
        model="test",
        abort_controller=abort_controller,
    )


@pytest.fixture
def hook_engine():
    return HookEngine()
