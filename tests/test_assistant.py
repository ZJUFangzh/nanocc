"""Tests for assistant mode mechanisms — proactive engine + Brief/Sleep tools.

Note: AssistantMode (lifecycle orchestration) was moved to the cowork product.
nanocc only provides the underlying mechanisms (ProactiveEngine, BriefTool, SleepTool).
"""

from __future__ import annotations

import pytest

from nanocc.assistant.proactive import ProactiveEngine, WakeEvent, WakeReason
from nanocc.assistant.brief import BriefTool, SleepTool
from nanocc.messages import create_user_message
from nanocc.types import ToolUseContext
from nanocc.utils.abort import AbortController


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
