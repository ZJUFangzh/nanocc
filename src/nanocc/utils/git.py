"""Git status snapshot for system context injection."""

from __future__ import annotations

import asyncio
import os


async def get_git_context(cwd: str) -> str | None:
    """Get a concise git status snapshot for the system prompt.

    Returns None if not in a git repo.
    """
    try:
        # Check if in a git repo
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--is-inside-work-tree",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode != 0:
            return None
    except (FileNotFoundError, asyncio.TimeoutError):
        return None

    parts: list[str] = []

    # Current branch
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "branch", "--show-current",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        branch = stdout.decode().strip()
        if branch:
            parts.append(f"Branch: {branch}")
    except (FileNotFoundError, asyncio.TimeoutError):
        pass

    # Short status
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--short",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        status = stdout.decode().strip()
        if status:
            lines = status.splitlines()
            if len(lines) > 10:
                parts.append(f"Changed files ({len(lines)}):\n" + "\n".join(lines[:10]) + "\n...")
            else:
                parts.append(f"Changed files:\n{status}")
        else:
            parts.append("Working tree clean")
    except (FileNotFoundError, asyncio.TimeoutError):
        pass

    # Recent commits (last 3)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--oneline", "-3",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        log = stdout.decode().strip()
        if log:
            parts.append(f"Recent commits:\n{log}")
    except (FileNotFoundError, asyncio.TimeoutError):
        pass

    return "\n".join(parts) if parts else None
