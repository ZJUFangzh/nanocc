"""Memory extraction — background analysis of conversation for long-term memory.

After each turn, a background task analyzes the conversation for information
worth persisting as long-term memory (user/feedback/project/reference types).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from nanocc.messages import get_text_content
from nanocc.types import AssistantMessage, Message, UserMessage

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """Analyze the most recent exchange in the conversation below.
Identify any information that should be saved as long-term memory.

Memory types:
- user: Information about the user's role, preferences, expertise
- feedback: User corrections or confirmations of approach
- project: Ongoing work, goals, decisions, deadlines
- reference: Pointers to external resources

Rules:
- Only extract genuinely useful information for future conversations
- Do NOT extract: code patterns (derivable from code), git history, debugging solutions, ephemeral task details
- Convert relative dates to absolute dates
- If nothing is worth saving, respond with "NO_MEMORY"

If there is something to save, respond in this format:
TYPE: <user|feedback|project|reference>
NAME: <short name>
DESCRIPTION: <one-line description>
CONTENT:
<memory content>

Recent exchange:
{exchange}"""


def build_extract_prompt(messages: list[Message], last_n: int = 4) -> str | None:
    """Build the extraction prompt from recent messages.

    Returns None if there's nothing meaningful to extract from.
    """
    recent = messages[-last_n:] if len(messages) > last_n else messages

    parts: list[str] = []
    for msg in recent:
        if isinstance(msg, UserMessage):
            text = get_text_content(msg)
            if text and len(text) > 20:
                parts.append(f"User: {text[:2000]}")
        elif isinstance(msg, AssistantMessage):
            text = get_text_content(msg)
            if text:
                parts.append(f"Assistant: {text[:2000]}")

    if not parts:
        return None

    exchange = "\n\n".join(parts)
    return EXTRACT_PROMPT.format(exchange=exchange)


def parse_extract_response(response: str) -> dict[str, str] | None:
    """Parse the LLM's memory extraction response.

    Returns dict with type, name, description, content, or None.
    """
    if "NO_MEMORY" in response:
        return None

    result: dict[str, str] = {}
    content_lines: list[str] = []
    in_content = False

    for line in response.splitlines():
        if in_content:
            content_lines.append(line)
            continue

        if line.startswith("TYPE:"):
            result["type"] = line[5:].strip().lower()
        elif line.startswith("NAME:"):
            result["name"] = line[5:].strip()
        elif line.startswith("DESCRIPTION:"):
            result["description"] = line[12:].strip()
        elif line.startswith("CONTENT:"):
            in_content = True

    if content_lines:
        result["content"] = "\n".join(content_lines).strip()

    if result.get("type") and result.get("name") and result.get("content"):
        return result

    return None
