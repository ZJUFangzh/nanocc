"""Core type definitions for nanocc.

Mirrors Claude Code's type system: Message, ContentBlock, StreamEvent, Terminal.
All types are plain dataclasses — no Pydantic dependency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


# ── Content Blocks ──────────────────────────────────────────────────────────


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | list[dict[str, Any]]
    is_error: bool = False
    type: str = "tool_result"


@dataclass
class ThinkingBlock:
    thinking: str
    signature: str = ""
    type: str = "thinking"


@dataclass
class RedactedThinkingBlock:
    data: str = ""
    type: str = "redacted_thinking"


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | RedactedThinkingBlock


# ── Messages ────────────────────────────────────────────────────────────────


@dataclass
class UserMessage:
    content: str | list[ContentBlock | dict[str, Any]]
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "user"


@dataclass
class AssistantMessage:
    content: list[ContentBlock]
    model: str = ""
    stop_reason: str | None = None
    usage: MessageUsage | None = None
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "assistant"


class SystemMessageSubtype(str, Enum):
    COMPACT_BOUNDARY = "compact_boundary"
    API_ERROR = "api_error"
    TOOL_RESULT_BUDGET = "tool_result_budget"
    TICK = "tick"


@dataclass
class SystemMessage:
    subtype: SystemMessageSubtype
    text: str
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "system"


Message = UserMessage | AssistantMessage | SystemMessage


@dataclass
class MessageUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


# ── Stream Events (normalized provider events) ─────────────────────────────


class StreamEventType(str, Enum):
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_STOP = "message_stop"
    CONTENT_BLOCK_START = "content_block_start"
    CONTENT_BLOCK_DELTA = "content_block_delta"
    CONTENT_BLOCK_STOP = "content_block_stop"


@dataclass
class StreamEvent:
    type: StreamEventType
    # For content_block_start
    index: int = 0
    content_block: ContentBlock | None = None
    block_type: str = ""  # "text", "tool_use", "thinking"
    tool_name: str = ""   # tool name when block_type == "tool_use"
    # For content_block_delta
    delta: dict[str, Any] | None = None
    # For message_start / message_delta
    message: dict[str, Any] | None = None
    usage: MessageUsage | None = None
    stop_reason: str | None = None


# ── Terminal (query loop exit) ──────────────────────────────────────────────


class TerminalReason(str, Enum):
    COMPLETED = "completed"
    ABORTED_STREAMING = "aborted_streaming"
    ABORTED_TOOLS = "aborted_tools"
    PROMPT_TOO_LONG = "prompt_too_long"
    MAX_TURNS = "max_turns"
    MODEL_ERROR = "model_error"


@dataclass
class Terminal:
    reason: TerminalReason
    error: str | None = None


# ── Tool Protocol ───────────────────────────────────────────────────────────


class PermissionBehavior(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionResult:
    behavior: PermissionBehavior
    message: str = ""


@dataclass
class ToolResult:
    content: str | list[dict[str, Any]]
    is_error: bool = False
    # Tools can inject new messages or modify context
    new_messages: list[Message] = field(default_factory=list)


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    is_read_only: bool

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionResult: ...

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult: ...


# ── Query Params & Loop State ───────────────────────────────────────────────


@dataclass
class ToolUseContext:
    """Carries shared state through tool execution."""

    cwd: str = "."
    tools: list[Tool] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    model: str = ""
    abort_controller: Any = None  # AbortController, forward ref
    permission_mode: str = "default"
    # Extensible options
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryParams:
    """Parameters for the query() agent loop."""

    messages: list[Message]
    system_prompt: str | list[dict[str, Any]]
    provider: Any  # LLMProvider, forward ref
    model: str
    tools: list[Tool] = field(default_factory=list)
    abort_controller: Any = None  # AbortController
    max_turns: int = 0  # 0 = unlimited
    max_tokens: int = 16_384
    tool_use_context: ToolUseContext | None = None
    assistant_mode: bool = False
    proactive_engine: Any = None  # ProactiveEngine, forward ref


@dataclass
class LoopState:
    """Mutable state for the agent loop."""

    messages: list[Message]
    tool_use_context: ToolUseContext
    turn_count: int = 0
    # Will be extended in later phases
    auto_compact_tracking: Any = None
    hook_engine: Any = None
