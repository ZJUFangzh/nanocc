"""CLAUDE.md hierarchical loading.

Loads CLAUDE.md from multiple levels:
1. ~/.nanocc/CLAUDE.md (global)
2. Project root CLAUDE.md
3. Current directory CLAUDE.md (if different from root)
"""

from __future__ import annotations

import os
from pathlib import Path

from nanocc.utils.config import GLOBAL_CONFIG_DIR


def load_claude_md(cwd: str) -> str:
    """Load and concatenate CLAUDE.md from all levels."""
    parts: list[str] = []

    # Global
    global_path = GLOBAL_CONFIG_DIR / "CLAUDE.md"
    if global_path.is_file():
        parts.append(_read_file(global_path, "Global"))

    # Find git root for project-level
    git_root = _find_git_root(cwd)

    if git_root:
        root_md = Path(git_root) / "CLAUDE.md"
        if root_md.is_file():
            parts.append(_read_file(root_md, "Project"))

    # Current directory (if different from git root)
    cwd_md = Path(cwd) / "CLAUDE.md"
    if cwd_md.is_file() and (not git_root or str(cwd_md.resolve()) != str((Path(git_root) / "CLAUDE.md").resolve())):
        parts.append(_read_file(cwd_md, "Local"))

    return "\n\n".join(parts)


def _read_file(path: Path, label: str) -> str:
    try:
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return f"# {label} CLAUDE.md\n{content}"
    except OSError:
        pass
    return ""


def _find_git_root(cwd: str) -> str | None:
    """Walk up to find .git directory."""
    current = Path(cwd).resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return str(current)
        current = current.parent
    return None
