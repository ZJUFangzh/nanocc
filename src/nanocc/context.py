"""System prompt assembly with cache control.

Three-segment structure (matching CC):
1. Static system prompt (cached)
2. User context (CLAUDE.md, memory — dynamic)
3. System context (git, cwd, date — dynamic)
"""

from __future__ import annotations

import os
import platform
from datetime import datetime
from typing import Any


def build_system_prompt(
    *,
    base_prompt: str = "",
    user_context: dict[str, str] | None = None,
    system_context: dict[str, str] | None = None,
    cwd: str = ".",
) -> list[dict[str, Any]]:
    """Assemble the system prompt with cache_control segments.

    Returns a list of text blocks suitable for the Anthropic API system param.
    For OpenAI compat, these get concatenated into a single system message.
    """
    blocks: list[dict[str, Any]] = []

    # ── Segment 1: Static base prompt (cacheable) ──────────────────────
    if not base_prompt:
        base_prompt = _default_system_prompt()

    blocks.append({
        "type": "text",
        "text": base_prompt,
        "cache_control": {"type": "ephemeral"},
    })

    # ── Segment 2: User context (CLAUDE.md, memory) ───────────────────
    user_ctx_parts: list[str] = []
    if user_context:
        for key, value in user_context.items():
            if value.strip():
                user_ctx_parts.append(f"# {key}\n{value}")

    if user_ctx_parts:
        blocks.append({
            "type": "text",
            "text": "\n\n".join(user_ctx_parts),
            "cache_control": {"type": "ephemeral"},
        })

    # ── Segment 3: System context (git, cwd, date) ────────────────────
    sys_ctx_parts: list[str] = []

    # Always include cwd and date — structured as a clear section
    sys_ctx_parts.append("# Environment")
    sys_ctx_parts.append(f"- Working directory: {os.path.abspath(cwd)}")
    sys_ctx_parts.append(f"- Platform: {_get_platform()}")
    sys_ctx_parts.append(f"- Current date: {datetime.now().strftime('%Y-%m-%d')}")
    sys_ctx_parts.append("")
    sys_ctx_parts.append(
        "The above environment information is already known to you. "
        "Do NOT run shell commands like `pwd` or `date` to obtain it. "
        "Use absolute paths based on the working directory for all file operations."
    )

    if system_context:
        for key, value in system_context.items():
            if value.strip():
                sys_ctx_parts.append(f"{key}: {value}")

    if sys_ctx_parts:
        blocks.append({
            "type": "text",
            "text": "\n".join(sys_ctx_parts),
        })

    return blocks


def system_prompt_to_text(blocks: list[dict[str, Any]]) -> str:
    """Flatten system prompt blocks to plain text (for OpenAI compat)."""
    return "\n\n".join(b.get("text", "") for b in blocks)


def _get_platform() -> str:
    """Get platform string like 'darwin', 'linux', 'win32'."""
    return platform.system().lower()


def _default_system_prompt() -> str:
    return """You are a helpful AI coding assistant. You have access to tools for reading files, editing files, running shell commands, and searching codebases.

Key behaviors:
- Always use absolute paths based on the working directory provided in the environment section
- Read files before modifying them
- Use tools when the user's request requires interacting with the filesystem or running commands
- Be concise and direct in responses
- When making code changes, explain what you changed and why"""
