"""Auto dream — offline memory consolidation.

Gate: 24h since last dream + 5 new sessions.
Three phases: Orient → Gather → Consolidate.
Uses file lock to prevent concurrent dreams.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from nanocc.constants import AUTO_DREAM_MIN_HOURS_BETWEEN, AUTO_DREAM_MIN_SESSIONS_TRIGGER
from nanocc.utils.config import get_global_config_dir

logger = logging.getLogger(__name__)


class AutoDreamEngine:
    """Offline memory distillation — consolidates memories across sessions."""

    def __init__(self, memory_dir: Path) -> None:
        self._memory_dir = memory_dir
        self._state_file = memory_dir / ".dream_state.json"
        self._lock_file = memory_dir / ".dream.lock"

    def should_dream(self) -> bool:
        """Check if dream conditions are met."""
        state = self._load_state()
        last_dream = state.get("last_dream_time", 0)
        sessions_since = state.get("sessions_since_dream", 0)

        hours_elapsed = (time.time() - last_dream) / 3600
        return (
            hours_elapsed >= AUTO_DREAM_MIN_HOURS_BETWEEN
            and sessions_since >= AUTO_DREAM_MIN_SESSIONS_TRIGGER
        )

    def record_session(self) -> None:
        """Record that a new session started (for dream gating)."""
        state = self._load_state()
        state["sessions_since_dream"] = state.get("sessions_since_dream", 0) + 1
        self._save_state(state)

    async def maybe_consolidate(self, provider: Any, model: str) -> bool:
        """Run dream consolidation if conditions are met.

        Returns True if dream was performed.
        """
        if not self.should_dream():
            return False

        if not self._acquire_lock():
            logger.debug("Dream lock held by another process")
            return False

        try:
            logger.info("Starting auto dream consolidation")
            await self._consolidate(provider, model)

            state = self._load_state()
            state["last_dream_time"] = time.time()
            state["sessions_since_dream"] = 0
            self._save_state(state)
            return True
        except Exception as e:
            logger.error("Dream consolidation failed: %s", e)
            return False
        finally:
            self._release_lock()

    async def _consolidate(self, provider: Any, model: str) -> None:
        """Three-phase memory consolidation.

        Phase 1 (Orient): Read existing memory structure
        Phase 2 (Gather): Scan transcripts for key signals
        Phase 3 (Consolidate): LLM merge, deduplicate, update files
        """
        # Phase 1: Read existing memories
        memory_files = []
        for path in self._memory_dir.glob("*.md"):
            if path.name in ("MEMORY.md", ".dream_state.json"):
                continue
            memory_files.append(path.name)

        # Phase 2 & 3 would use LLM to analyze transcripts and update memories
        # For now, this is a placeholder that logs the structure
        logger.info("Dream: found %d memory files", len(memory_files))

    def _acquire_lock(self) -> bool:
        try:
            fd = os.open(str(self._lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            # Check if lock is stale (>1 hour)
            try:
                age = time.time() - os.path.getmtime(self._lock_file)
                if age > 3600:
                    os.unlink(self._lock_file)
                    return self._acquire_lock()
            except OSError:
                pass
            return False

    def _release_lock(self) -> None:
        try:
            os.unlink(self._lock_file)
        except OSError:
            pass

    def _load_state(self) -> dict[str, Any]:
        if self._state_file.is_file():
            try:
                with open(self._state_file) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)
