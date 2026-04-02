"""Session memory — structured working notes that survive compact.

Fixed sections: Current State, Task, Files, Errors, Worklog.
Triggers: 10K token init, 5K token increment, 3+ tool calls.
Updated via LLM side-query after significant work.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from nanocc.constants import (
    SESSION_MEMORY_INIT_THRESHOLD_TOKENS,
    SESSION_MEMORY_MIN_TOOL_CALLS,
    SESSION_MEMORY_UPDATE_THRESHOLD_TOKENS,
)

logger = logging.getLogger(__name__)

SECTIONS = [
    "Current State",
    "Task",
    "Key Files",
    "Recent Changes",
    "Errors Encountered",
    "Worklog",
]

TEMPLATE = "\n\n".join(f"## {s}\n(empty)" for s in SECTIONS)


@dataclass
class SessionMemory:
    """Tracks structured working notes for the current session."""

    content: str = ""
    tokens_at_last_update: int = 0
    tool_calls_since_update: int = 0
    initialized: bool = False

    def should_update(self, current_tokens: int, tool_calls: int) -> bool:
        """Check if session memory should be updated."""
        self.tool_calls_since_update += tool_calls

        if not self.initialized:
            return (
                current_tokens >= SESSION_MEMORY_INIT_THRESHOLD_TOKENS
                and self.tool_calls_since_update >= SESSION_MEMORY_MIN_TOOL_CALLS
            )

        token_delta = current_tokens - self.tokens_at_last_update
        return (
            token_delta >= SESSION_MEMORY_UPDATE_THRESHOLD_TOKENS
            and self.tool_calls_since_update >= SESSION_MEMORY_MIN_TOOL_CALLS
        )

    def update(self, new_content: str, current_tokens: int) -> None:
        """Update session memory content."""
        self.content = new_content
        self.tokens_at_last_update = current_tokens
        self.tool_calls_since_update = 0
        self.initialized = True

    def get_prompt(self) -> str:
        """Get session memory for system prompt injection."""
        if not self.content:
            return ""
        return f"# Session Memory\n\n{self.content}"

    def get_update_prompt(self, conversation_summary: str) -> str:
        """Build prompt for LLM to update session memory."""
        current = self.content or TEMPLATE
        return f"""Update the session memory below based on the recent conversation.
Keep the same section structure. Be concise but preserve important details.

Current session memory:
{current}

Recent conversation context:
{conversation_summary}

Output the updated session memory with the same section headers."""
