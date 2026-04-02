"""Tests for hooks — engine, matching, firing, types."""

from __future__ import annotations

import pytest

from nanocc.hooks.engine import HookEngine, load_hooks_from_settings
from nanocc.hooks.types import Hook, HookEvent, HookRegistration


# ── HookEvent enum ──

def test_hook_events():
    assert len(HookEvent) == 5
    assert HookEvent.TOOL_START.value == "tool_start"
    assert HookEvent.TOOL_COMPLETE.value == "tool_complete"
    assert HookEvent.TOOL_ERROR.value == "tool_error"
    assert HookEvent.STOP.value == "stop"
    assert HookEvent.SUBAGENT_STOP.value == "subagent_stop"


# ── Hook dataclass ──

def test_hook_defaults():
    h = Hook(type="command", command="echo hi")
    assert h.timeout == 30
    assert h.once is False
    assert h.async_ is False
    assert h.if_condition is None


# ── HookEngine ──

@pytest.mark.asyncio
async def test_fire_tool_start(hook_engine):
    hook_engine.register(HookEvent.TOOL_START, "Bash", [
        Hook(type="prompt", prompt="start_fired"),
    ])
    outputs = await hook_engine.fire(HookEvent.TOOL_START, tool_name="Bash", tool_input={})
    assert outputs == ["start_fired"]


@pytest.mark.asyncio
async def test_fire_tool_complete(hook_engine):
    hook_engine.register(HookEvent.TOOL_COMPLETE, "Bash", [
        Hook(type="prompt", prompt="complete_fired"),
    ])
    outputs = await hook_engine.fire(HookEvent.TOOL_COMPLETE, tool_name="Bash")
    assert outputs == ["complete_fired"]


@pytest.mark.asyncio
async def test_fire_stop(hook_engine):
    hook_engine.register(HookEvent.STOP, None, [
        Hook(type="prompt", prompt="stop_fired"),
    ])
    outputs = await hook_engine.fire(HookEvent.STOP)
    assert outputs == ["stop_fired"]


@pytest.mark.asyncio
async def test_matcher_filtering(hook_engine):
    hook_engine.register(HookEvent.TOOL_START, "Bash", [
        Hook(type="prompt", prompt="bash_only"),
    ])
    # Should not match Read
    outputs = await hook_engine.fire(HookEvent.TOOL_START, tool_name="Read", tool_input={})
    assert outputs == []


@pytest.mark.asyncio
async def test_wildcard_matcher(hook_engine):
    hook_engine.register(HookEvent.TOOL_START, "File*", [
        Hook(type="prompt", prompt="file_match"),
    ])
    out1 = await hook_engine.fire(HookEvent.TOOL_START, tool_name="FileRead")
    assert out1 == ["file_match"]
    out2 = await hook_engine.fire(HookEvent.TOOL_START, tool_name="FileWrite")
    assert out2 == ["file_match"]
    out3 = await hook_engine.fire(HookEvent.TOOL_START, tool_name="Bash")
    assert out3 == []


@pytest.mark.asyncio
async def test_once_hook_auto_remove(hook_engine):
    hook_engine.register(HookEvent.TOOL_COMPLETE, None, [
        Hook(type="prompt", prompt="once", once=True),
    ])
    out1 = await hook_engine.fire(HookEvent.TOOL_COMPLETE, tool_name="Bash")
    assert out1 == ["once"]
    out2 = await hook_engine.fire(HookEvent.TOOL_COMPLETE, tool_name="Bash")
    assert out2 == []


@pytest.mark.asyncio
async def test_if_condition(hook_engine):
    hook_engine.register(HookEvent.TOOL_COMPLETE, "Bash", [
        Hook(type="prompt", prompt="git_only", if_condition="Bash(git *)"),
    ])
    out1 = await hook_engine.fire(HookEvent.TOOL_COMPLETE, tool_name="Bash", tool_input={"command": "git status"})
    assert out1 == ["git_only"]
    out2 = await hook_engine.fire(HookEvent.TOOL_COMPLETE, tool_name="Bash", tool_input={"command": "npm test"})
    assert out2 == []


@pytest.mark.asyncio
async def test_command_hook(hook_engine):
    hook_engine.register(HookEvent.TOOL_START, None, [
        Hook(type="command", command="echo cmd_output"),
    ])
    outputs = await hook_engine.fire(HookEvent.TOOL_START, tool_name="Bash")
    assert outputs == ["cmd_output"]


@pytest.mark.asyncio
async def test_unregister_session(hook_engine):
    hook_engine.register(HookEvent.STOP, None, [
        Hook(type="prompt", prompt="persistent"),
    ], source="settings", session_scoped=False)
    hook_engine.register(HookEvent.STOP, None, [
        Hook(type="prompt", prompt="session"),
    ], source="skill", session_scoped=True)

    out1 = await hook_engine.fire(HookEvent.STOP)
    assert len(out1) == 2

    hook_engine.unregister_session()
    out2 = await hook_engine.fire(HookEvent.STOP)
    assert out2 == ["persistent"]


# ── load_hooks_from_settings ──

def test_load_hooks_from_settings():
    settings = {
        "hooks": {
            "tool_complete": [{
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "echo done", "if": "Bash(npm *)"}],
            }],
            "stop": [{
                "hooks": [{"type": "prompt", "prompt": "review"}],
            }],
        }
    }
    regs = load_hooks_from_settings(settings)
    assert len(regs) == 2
    assert regs[0].event == HookEvent.TOOL_COMPLETE
    assert regs[0].matcher == "Bash"
    assert regs[0].hooks[0].if_condition == "Bash(npm *)"
    assert regs[1].event == HookEvent.STOP
    assert regs[1].hooks[0].prompt == "review"


def test_load_hooks_ignores_unknown_events():
    settings = {"hooks": {"unknown_event": [{"hooks": [{"type": "prompt", "prompt": "x"}]}]}}
    regs = load_hooks_from_settings(settings)
    assert regs == []
