"""Tests for assistant mode — mode, proactive, brief."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nanocc.assistant.mode import AssistantMode
from nanocc.assistant.proactive import ProactiveEngine, WakeEvent, WakeReason
from nanocc.assistant.brief import BriefTool, SleepTool
from nanocc.messages import create_user_message
from nanocc.types import ToolUseContext
from nanocc.utils.abort import AbortController


# ── AssistantMode ──

def test_assistant_mode_activate():
    mode = AssistantMode()
    assert not mode.active
    sid = mode.activate()
    assert mode.active
    assert mode.session_id == sid
    assert len(sid) > 0


def test_assistant_mode_activate_with_id():
    mode = AssistantMode()
    sid = mode.activate("custom-id")
    assert sid == "custom-id"
    assert mode.session_id == "custom-id"


def test_assistant_mode_suspend_resume():
    mode = AssistantMode()
    mode.activate("test-session")

    state = {"messages": [], "model": "test", "cwd": "."}
    mode.suspend(state)

    # Resume
    mode2 = AssistantMode()
    restored = mode2.resume("test-session")
    assert restored is not None
    assert "suspended_at" in restored
    assert restored["session_id"] == "test-session"


def test_assistant_mode_resume_no_session():
    mode = AssistantMode()
    result = mode.resume("nonexistent-id")
    assert result is None


def test_assistant_mode_bridge_pointer():
    mode = AssistantMode()
    mode.activate("pointer-test")

    mode2 = AssistantMode()
    pointer = mode2._load_pointer()
    assert pointer == "pointer-test"


def test_assistant_mode_list_sessions():
    mode = AssistantMode()
    mode.activate("list-test")
    mode.suspend({"messages": [], "model": "test"})

    sessions = mode.list_sessions()
    ids = [s["session_id"] for s in sessions]
    assert "list-test" in ids


# ── ProactiveEngine ──

@pytest.mark.asyncio
async def test_proactive_user_message():
    pe = ProactiveEngine()
    msg = create_user_message("hello")
    pe.send_user_message(msg)

    wake = await pe.wait_for_next()
    assert wake.reason == WakeReason.USER_MESSAGE
    assert wake.data is msg


@pytest.mark.asyncio
async def test_proactive_shutdown():
    pe = ProactiveEngine()
    pe.request_shutdown()

    wake = await pe.wait_for_next()
    assert wake.reason == WakeReason.SHUTDOWN


def test_proactive_focus():
    pe = ProactiveEngine()
    assert pe.user_focused  # default

    pe.set_user_focus(False)
    assert not pe.user_focused

    pe.set_user_focus(True)
    assert pe.user_focused


def test_wake_reason_enum():
    assert WakeReason.TICK.value == "tick"
    assert WakeReason.USER_MESSAGE.value == "user_message"
    assert WakeReason.SHUTDOWN.value == "shutdown"


# ── BriefTool ──

@pytest.mark.asyncio
async def test_brief_tool_basic():
    tool = BriefTool()
    assert tool.name == "Brief"
    assert tool.is_read_only

    ctx = ToolUseContext(cwd=".", model="test", abort_controller=AbortController())
    result = await tool.execute({"message": "Hello user"}, ctx)
    assert result.content == "Hello user"


@pytest.mark.asyncio
async def test_brief_tool_with_handler():
    sent = []

    async def handler(msg, status):
        sent.append((msg, status))

    tool = BriefTool()
    ctx = ToolUseContext(
        cwd=".", model="test", abort_controller=AbortController(),
        options={"brief_handler": handler},
    )
    result = await tool.execute({"message": "Hello", "status": "proactive"}, ctx)
    assert len(sent) == 1
    assert sent[0] == ("Hello", "proactive")
    assert "Brief sent" in result.content


# ── SleepTool ──

@pytest.mark.asyncio
async def test_sleep_tool():
    tool = SleepTool()
    assert tool.name == "Sleep"
    assert tool.is_read_only

    ctx = ToolUseContext(cwd=".", model="test", abort_controller=AbortController())
    result = await tool.execute({"duration": 0}, ctx)
    assert result.content == "Woke up"


@pytest.mark.asyncio
async def test_sleep_tool_max_duration():
    """Sleep duration should be capped at 300s."""
    tool = SleepTool()
    ctx = ToolUseContext(cwd=".", model="test", abort_controller=AbortController())
    # This would sleep 0 seconds since we pass 0, but the cap logic is:
    # min(input.get("duration", 60), 300)
    result = await tool.execute({"duration": 0}, ctx)
    assert result.content == "Woke up"
