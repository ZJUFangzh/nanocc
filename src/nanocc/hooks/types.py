"""Hook event types and definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookEvent(str, Enum):
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    TOOL_ERROR = "tool_error"
    STOP = "stop"
    SUBAGENT_STOP = "subagent_stop"


@dataclass
class Hook:
    """A single hook definition."""
    type: str  # "command", "prompt", "http"
    # command type
    command: str | None = None
    # prompt type
    prompt: str | None = None
    # http type
    url: str | None = None
    headers: dict[str, str] | None = None
    # Common fields
    if_condition: str | None = None  # "Bash(git *)" match pattern
    timeout: int = 30
    once: bool = False
    async_: bool = False  # Run in background


@dataclass
class HookRegistration:
    """A hook bound to an event + optional matcher."""
    event: HookEvent
    matcher: str | None  # Tool name pattern to match
    hooks: list[Hook]
    source: str = "settings"  # "settings", "skill", "builtin"
    session_scoped: bool = False
