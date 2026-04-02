"""MEMORY.md index + topic files — long-term memory system.

4 memory types: user, feedback, project, reference
- MEMORY.md is the index (max 200 lines / 25KB)
- Each memory is a separate file with YAML frontmatter
- Index loaded into system prompt; topic files loaded on demand
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from nanocc.constants import MEMORY_INDEX_MAX_BYTES, MEMORY_INDEX_MAX_LINES
from nanocc.utils.config import get_memory_dir

VALID_TYPES = {"user", "feedback", "project", "reference"}


def load_memory_index(cwd: str) -> str:
    """Load MEMORY.md content for system prompt injection."""
    memory_dir = get_memory_dir(cwd)
    index_path = memory_dir / "MEMORY.md"

    if not index_path.is_file():
        return ""

    try:
        content = index_path.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Enforce limits
    lines = content.splitlines()
    if len(lines) > MEMORY_INDEX_MAX_LINES:
        lines = lines[:MEMORY_INDEX_MAX_LINES]
        content = "\n".join(lines)

    if len(content.encode("utf-8")) > MEMORY_INDEX_MAX_BYTES:
        content = content[:MEMORY_INDEX_MAX_BYTES]

    return content


def load_memory_file(cwd: str, filename: str) -> dict[str, Any] | None:
    """Load a single memory topic file, parsing frontmatter."""
    memory_dir = get_memory_dir(cwd)
    path = memory_dir / filename

    if not path.is_file():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None

    return parse_memory_file(raw, filename)


def parse_memory_file(content: str, filename: str = "") -> dict[str, Any]:
    """Parse a memory file with YAML frontmatter."""
    frontmatter: dict[str, str] = {}
    body = content

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if match:
        fm_text = match.group(1)
        body = match.group(2)
        for line in fm_text.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                frontmatter[key.strip()] = val.strip()

    return {
        "filename": filename,
        "name": frontmatter.get("name", filename),
        "description": frontmatter.get("description", ""),
        "type": frontmatter.get("type", "project"),
        "body": body.strip(),
    }


def list_memory_files(cwd: str) -> list[dict[str, Any]]:
    """List all memory topic files with their frontmatter."""
    memory_dir = get_memory_dir(cwd)
    files = []

    if not memory_dir.is_dir():
        return files

    for path in sorted(memory_dir.glob("*.md")):
        if path.name == "MEMORY.md":
            continue
        info = load_memory_file(cwd, path.name)
        if info:
            files.append(info)

    return files


def build_memory_prompt(cwd: str) -> str:
    """Build the memory section for the system prompt."""
    index = load_memory_index(cwd)
    if not index:
        return ""
    return f"# Memory\n\n{index}"
