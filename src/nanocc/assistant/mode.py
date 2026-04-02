"""Assistant mode — lifecycle management for long-running sessions.

Handles: activation, session persistence, suspend/resume, --continue.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from nanocc.utils.config import get_global_config_dir, get_sessions_dir

logger = logging.getLogger(__name__)

BRIDGE_POINTER_FILE = "bridge-pointer"


class AssistantMode:
    """Assistant mode lifecycle manager."""

    def __init__(self) -> None:
        self._active = False
        self._session_id: str | None = None
        self._state_dir = get_sessions_dir()

    @property
    def active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def activate(self, session_id: str | None = None) -> str:
        """Activate assistant mode. Returns session_id."""
        import uuid
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._active = True
        self._save_pointer()
        logger.info("Assistant mode activated: session=%s", self._session_id)
        return self._session_id

    def suspend(self, engine_state: dict[str, Any]) -> None:
        """Suspend session — serialize state to disk."""
        if not self._session_id:
            return

        session_dir = self._state_dir / self._session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        state_path = session_dir / "state.json"
        engine_state["suspended_at"] = time.time()
        engine_state["session_id"] = self._session_id

        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(engine_state, f, ensure_ascii=False, indent=2)

        self._save_pointer()
        logger.info("Session suspended: %s", self._session_id)

    def resume(self, session_id: str | None = None) -> dict[str, Any] | None:
        """Resume a session. Returns engine state or None."""
        sid = session_id or self._load_pointer()
        if not sid:
            logger.warning("No session to resume")
            return None

        session_dir = self._state_dir / sid
        state_path = session_dir / "state.json"

        if not state_path.is_file():
            logger.warning("Session state not found: %s", sid)
            return None

        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load session state: %s", e)
            return None

        self._session_id = sid
        self._active = True
        logger.info("Session resumed: %s", sid)
        return state

    def _save_pointer(self) -> None:
        """Write bridge-pointer so --continue can find the latest session."""
        pointer_path = get_global_config_dir() / BRIDGE_POINTER_FILE
        pointer_path.write_text(self._session_id or "")

    def _load_pointer(self) -> str | None:
        """Read the most recent session id from bridge-pointer."""
        pointer_path = get_global_config_dir() / BRIDGE_POINTER_FILE
        if pointer_path.is_file():
            sid = pointer_path.read_text().strip()
            return sid if sid else None
        return None

    def list_sessions(self) -> list[dict[str, Any]]:
        """List available sessions."""
        sessions = []
        if not self._state_dir.is_dir():
            return sessions

        for d in sorted(self._state_dir.iterdir(), reverse=True):
            state_path = d / "state.json"
            if state_path.is_file():
                try:
                    with open(state_path) as f:
                        state = json.load(f)
                        sessions.append({
                            "session_id": d.name,
                            "suspended_at": state.get("suspended_at", 0),
                            "cwd": state.get("cwd", ""),
                            "model": state.get("model", ""),
                        })
                except (json.JSONDecodeError, OSError):
                    pass

        return sessions
