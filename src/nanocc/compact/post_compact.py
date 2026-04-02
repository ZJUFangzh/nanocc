"""Post-compact cleanup and context restoration.

After auto compact replaces messages with a summary, this module:
- Clears stale caches
- Re-injects recently read files (up to 5, within token budget)
- Will re-inject skills and MCP tool deltas (Phase 5)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from nanocc.constants import POST_COMPACT_MAX_FILES, POST_COMPACT_MAX_TOKENS
from nanocc.messages import create_user_message
from nanocc.types import (
    AssistantMessage,
    Message,
    ToolUseBlock,
    UserMessage,
)
from nanocc.utils.tokens import estimate_tokens_for_text

logger = logging.getLogger(__name__)

# Per-file token cap
MAX_TOKENS_PER_FILE = 5_000


def create_post_compact_file_attachments(
    original_messages: list[Message],
    cwd: str,
    max_files: int = POST_COMPACT_MAX_FILES,
    total_token_budget: int = POST_COMPACT_MAX_TOKENS,
) -> list[Message]:
    """Re-inject recently read files as context after compaction.

    Scans original messages for Read tool calls, reads the most recent
    files (up to max_files within token budget), and creates attachment messages.
    """
    # Collect recently read file paths (most recent first)
    read_files: list[str] = []
    seen: set[str] = set()

    for msg in reversed(original_messages):
        if not isinstance(msg, AssistantMessage):
            continue
        for block in msg.content:
            if isinstance(block, ToolUseBlock) and block.name == "Read":
                path = block.input.get("file_path", "")
                if path and path not in seen:
                    seen.add(path)
                    read_files.append(path)
                    if len(read_files) >= max_files * 2:  # Collect extras in case some fail
                        break

    if not read_files:
        return []

    # Read files within budget
    attachments: list[Message] = []
    tokens_used = 0

    for path in read_files[:max_files]:
        if not os.path.isabs(path):
            path = os.path.join(cwd, path)

        if not os.path.isfile(path):
            continue

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue

        # Truncate per-file
        file_tokens = estimate_tokens_for_text(content)
        if file_tokens > MAX_TOKENS_PER_FILE:
            # Rough char truncation
            max_chars = MAX_TOKENS_PER_FILE * 3  # ~3 chars/token conservative
            content = content[:max_chars] + "\n... [truncated]"
            file_tokens = MAX_TOKENS_PER_FILE

        if tokens_used + file_tokens > total_token_budget:
            break

        tokens_used += file_tokens
        attachments.append(
            create_user_message(
                f"[Post-compact file context: {path}]\n\n{content}"
            )
        )

    if attachments:
        logger.debug(
            "Post-compact: re-injected %d files (%d tokens)",
            len(attachments), tokens_used,
        )

    return attachments
