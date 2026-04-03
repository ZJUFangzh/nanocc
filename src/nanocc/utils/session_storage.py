"""Session transcript persistence — incremental append + compact boundary aware loading."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from nanocc.utils.config import get_sessions_dir


# ── Transcript (append-only JSONL) ────────────────────────────────────────


def append_messages(
    session_id: str,
    messages: list[dict[str, Any]],
    last_saved_index: int = 0,
) -> int:
    """Append new messages to transcript JSONL.

    Args:
        session_id: Session identifier.
        messages: Full transcript message list (transcript format, includes system msgs).
        last_saved_index: Index of the first unsaved message.

    Returns:
        New last_saved_index (== len(messages)).
    """
    if last_saved_index >= len(messages):
        return last_saved_index

    session_dir = _ensure_session_dir(session_id)
    transcript_path = session_dir / "transcript.jsonl"

    with open(transcript_path, "a", encoding="utf-8") as f:
        for msg in messages[last_saved_index:]:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    return len(messages)


def load_transcript(session_id: str) -> list[dict[str, Any]] | None:
    """Load full conversation transcript from JSONL."""
    sessions_dir = get_sessions_dir()
    transcript_path = sessions_dir / session_id / "transcript.jsonl"

    if not transcript_path.is_file():
        return None

    messages: list[dict[str, Any]] = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def load_transcript_after_boundary(session_id: str) -> list[dict[str, Any]] | None:
    """Load messages after the last compact_boundary marker.

    If no boundary exists, returns the full transcript.
    The boundary message itself is included in the result.
    """
    all_messages = load_transcript(session_id)
    if all_messages is None:
        return None

    # Find the last compact_boundary
    last_boundary_idx = -1
    for i, msg in enumerate(all_messages):
        if (
            msg.get("role") == "system"
            and msg.get("subtype") == "compact_boundary"
        ):
            last_boundary_idx = i

    if last_boundary_idx == -1:
        return all_messages

    # Include boundary itself + everything after
    return all_messages[last_boundary_idx:]


# ── Session State ─────────────────────────────────────────────────────────


def save_session_state(session_id: str, state: dict[str, Any]) -> None:
    """Save session state (usage, cwd, memory, model, etc.)."""
    session_dir = _ensure_session_dir(session_id)
    state_path = session_dir / "state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, ensure_ascii=False, fp=f, indent=2)


def load_session_state(session_id: str) -> dict[str, Any] | None:
    """Load session state."""
    sessions_dir = get_sessions_dir()
    state_path = sessions_dir / session_id / "state.json"
    if not state_path.is_file():
        return None
    with open(state_path, encoding="utf-8") as f:
        return json.load(f)


# ── Session Metadata ──────────────────────────────────────────────────────


def save_meta(
    session_id: str,
    *,
    message_count: int,
    cwd: str = "",
    model: str = "",
    last_message: str = "",
) -> None:
    """Save/update session metadata."""
    session_dir = _ensure_session_dir(session_id)
    meta_path = session_dir / "meta.json"
    meta = {
        "session_id": session_id,
        "timestamp": time.time(),
        "message_count": message_count,
        "cwd": cwd,
        "model": model,
        "last_message": last_message[:120],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def list_sessions(cwd: str | None = None) -> list[dict[str, Any]]:
    """List all saved sessions, newest first. Optionally filter by cwd."""
    sessions_dir = get_sessions_dir()
    sessions: list[dict[str, Any]] = []
    if not sessions_dir.is_dir():
        return sessions

    for d in sessions_dir.iterdir():
        if d.is_dir():
            meta_path = d / "meta.json"
            if meta_path.is_file():
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                        if cwd is None or meta.get("cwd") == cwd:
                            sessions.append(meta)
                except (json.JSONDecodeError, OSError):
                    pass

    sessions.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
    return sessions


# ── Helpers ───────────────────────────────────────────────────────────────


def _ensure_session_dir(session_id: str) -> Path:
    sessions_dir = get_sessions_dir()
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir
