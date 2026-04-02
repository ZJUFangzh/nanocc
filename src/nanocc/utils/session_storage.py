"""Session transcript persistence — save/load conversation history."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from nanocc.utils.config import get_sessions_dir


def save_transcript(session_id: str, messages: list[dict[str, Any]]) -> Path:
    """Save conversation transcript as JSONL."""
    sessions_dir = get_sessions_dir()
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = session_dir / "transcript.jsonl"
    with open(transcript_path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    # Save metadata
    meta_path = session_dir / "meta.json"
    meta = {
        "session_id": session_id,
        "timestamp": time.time(),
        "message_count": len(messages),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return transcript_path


def load_transcript(session_id: str) -> list[dict[str, Any]] | None:
    """Load conversation transcript from JSONL."""
    sessions_dir = get_sessions_dir()
    transcript_path = sessions_dir / session_id / "transcript.jsonl"

    if not transcript_path.is_file():
        return None

    messages = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def save_session_state(session_id: str, state: dict[str, Any]) -> None:
    """Save session state (usage, cwd, memory path, etc.)."""
    sessions_dir = get_sessions_dir()
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

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


def list_sessions() -> list[dict[str, Any]]:
    """List all saved sessions, newest first."""
    sessions_dir = get_sessions_dir()
    sessions = []
    if not sessions_dir.is_dir():
        return sessions

    for d in sessions_dir.iterdir():
        if d.is_dir():
            meta_path = d / "meta.json"
            if meta_path.is_file():
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                        sessions.append(meta)
                except (json.JSONDecodeError, OSError):
                    pass

    sessions.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
    return sessions
