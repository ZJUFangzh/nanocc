"""Tests for agents — fork, coordinator."""

from __future__ import annotations

import pytest

from nanocc.agents.fork import fork_agent
from nanocc.agents.coordinator import run_parallel_subtasks, run_serial_subtasks, SubtaskResult
from nanocc.types import AssistantMessage, Terminal, TerminalReason
from nanocc.utils.abort import AbortController

from tests.conftest import MockProvider, text_events


# ── fork_agent ──

@pytest.mark.asyncio
async def test_fork_agent_basic():
    provider = MockProvider([text_events("forked reply")])
    events = []
    async for event in fork_agent(
        prompt="do something",
        provider=provider,
        model="test",
        system_prompt="You are a test.",
        tools=[],
    ):
        events.append(event)

    terminals = [e for e in events if isinstance(e, Terminal)]
    assert len(terminals) == 1
    assert terminals[0].reason == TerminalReason.COMPLETED

    msgs = [e for e in events if isinstance(e, AssistantMessage)]
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_fork_agent_with_parent_abort():
    parent_abort = AbortController()
    provider = MockProvider([text_events("hi")])

    events = []
    async for event in fork_agent(
        prompt="test",
        provider=provider,
        model="test",
        system_prompt="test",
        tools=[],
        parent_abort=parent_abort,
    ):
        events.append(event)

    assert any(isinstance(e, Terminal) for e in events)


# ── coordinator ──

@pytest.mark.asyncio
async def test_run_parallel_subtasks():
    provider = MockProvider([text_events("parallel result")])
    results = await run_parallel_subtasks(
        subtasks=["task1", "task2", "task3"],
        provider=provider,
        model="test",
        system_prompt="test",
        tools=[],
        max_concurrent=2,
    )
    assert len(results) == 3
    assert all(isinstance(r, SubtaskResult) for r in results)
    assert all(r.success for r in results)


@pytest.mark.asyncio
async def test_run_serial_subtasks():
    call_order = []

    class OrderedProvider:
        def __init__(self):
            self.call_count = 0
        def get_context_window(self, model): return 100000
        async def stream(self, **kw):
            self.call_count += 1
            call_order.append(self.call_count)
            for e in text_events(f"result_{self.call_count}"):
                yield e

    provider = OrderedProvider()
    results = await run_serial_subtasks(
        subtasks=["write1", "write2"],
        provider=provider,
        model="test",
        system_prompt="test",
        tools=[],
    )
    assert len(results) == 2
    assert all(r.success for r in results)
    # Verify sequential execution
    assert call_order == [1, 2]
