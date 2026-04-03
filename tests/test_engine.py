"""Tests for QueryEngine — stateful session container."""

from __future__ import annotations

import pytest

from nanocc.engine import QueryEngine, QueryEngineConfig
from nanocc.messages import create_assistant_message, create_user_message
from nanocc.types import TextBlock, ToolUseBlock

from tests.conftest import MockProvider, text_events


@pytest.fixture
def engine():
    provider = MockProvider([text_events("engine reply")])
    config = QueryEngineConfig(provider=provider, model="test", cwd=".")
    return QueryEngine(config)


def test_engine_init(engine):
    assert engine.messages == []
    assert len(engine.tools) == 12
    assert engine.usage.api_calls == 0
    assert engine.session_memory.initialized is False


def test_engine_get_state(engine):
    engine.messages.append(create_user_message("hello"))
    engine.messages.append(create_assistant_message([TextBlock(text="hi")]))
    engine.usage.total_input_tokens = 100
    engine.usage.total_output_tokens = 50
    engine.usage.api_calls = 1
    engine.session_memory.content = "## Current State\nworking"
    engine.session_memory.initialized = True

    state = engine.get_state()
    assert len(state["messages"]) == 2
    assert state["usage"]["input"] == 100
    assert state["usage"]["output"] == 50
    assert state["usage"]["api_calls"] == 1
    assert "working" in state["session_memory"]


def test_engine_restore_state(engine):
    state = {
        "session_id": "test-123",
        "cwd": "/tmp/test",
        "model": "test",
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        ],
        "usage": {"input": 200, "output": 100, "api_calls": 3},
        "session_memory": "## Task\nfixing bug",
    }
    engine.restore_state(state)

    assert engine.session_id == "test-123"
    assert engine.cwd == "/tmp/test"
    assert len(engine.messages) == 2
    assert engine.usage.total_input_tokens == 200
    assert engine.usage.total_output_tokens == 100
    assert engine.usage.api_calls == 3
    assert engine.session_memory.content == "## Task\nfixing bug"
    assert engine.session_memory.initialized is True


def test_engine_get_restore_round_trip(engine):
    """get_state() → restore_state() should preserve messages."""
    engine.messages.append(create_user_message("hello"))
    engine.messages.append(create_assistant_message([
        TextBlock(text="hi"),
        ToolUseBlock(id="t1", name="Bash", input={"command": "ls"}),
    ]))

    state = engine.get_state()

    engine2 = QueryEngine(QueryEngineConfig(
        provider=MockProvider(), model="test", cwd=".",
    ))
    engine2.restore_state(state)

    state2 = engine2.get_state()
    assert state["messages"] == state2["messages"]


def test_engine_clear(engine):
    engine.messages.append(create_user_message("hello"))
    engine.session_memory.content = "some content"
    engine.session_memory.initialized = True

    engine.clear()
    assert engine.messages == []
    assert not engine.session_memory.initialized


@pytest.mark.asyncio
async def test_multi_turn_messages_accumulate():
    """Regression: assistant messages must persist across turns.

    Previously query.py copied params.messages into state.messages,
    so assistant replies were never written back to engine.messages.
    On the next turn the LLM only saw user messages (no assistant
    responses), causing it to re-process everything from scratch.
    """
    provider = MockProvider([
        text_events("reply 1"),
        text_events("reply 2"),
    ])
    config = QueryEngineConfig(provider=provider, model="test", cwd=".")
    eng = QueryEngine(config)

    # Turn 1
    async for _ in eng.submit_message("hello"):
        pass

    assert len(eng.messages) == 2, "should have [user, assistant] after turn 1"
    assert eng.messages[0].role == "user"
    assert eng.messages[1].role == "assistant"

    # Turn 2
    async for _ in eng.submit_message("world"):
        pass

    assert len(eng.messages) == 4, "should have [u1, a1, u2, a2] after turn 2"
    roles = [m.role for m in eng.messages]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_engine_abort(engine):
    engine._abort = None
    engine.abort()  # Should not raise

    from nanocc.utils.abort import AbortController
    engine._abort = AbortController()
    engine.abort()
    assert engine._abort.is_aborted
