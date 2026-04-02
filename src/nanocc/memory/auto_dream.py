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
        # Phase 1 (Orient): Read existing memories
        existing_memories: list[dict[str, str]] = []
        for path in sorted(self._memory_dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            try:
                content = path.read_text(encoding="utf-8")
                existing_memories.append({"filename": path.name, "content": content})
            except OSError:
                continue

        logger.info("Dream Phase 1: found %d memory files", len(existing_memories))

        # Phase 2 (Gather): Scan transcripts for key signals
        sessions_dir = get_global_config_dir() / "sessions"
        gathered_signals: list[str] = []

        if sessions_dir.is_dir():
            for session_dir in sorted(sessions_dir.iterdir(), reverse=True)[:10]:
                transcript_path = session_dir / "transcript.jsonl"
                if not transcript_path.is_file():
                    continue
                try:
                    with open(transcript_path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            # Look for key signals: corrections, decisions, references
                            lower = line.lower()
                            if any(kw in lower for kw in (
                                "don't", "don't", "stop doing", "always", "never",
                                "remember", "important", "decided", "deadline",
                                "bug", "fixed", "broken",
                            )):
                                # Extract just the content text, truncated
                                try:
                                    msg = json.loads(line)
                                    content = msg.get("content", "")
                                    if isinstance(content, str) and len(content) > 30:
                                        gathered_signals.append(content[:500])
                                except json.JSONDecodeError:
                                    pass
                except OSError:
                    continue

        logger.info("Dream Phase 2: gathered %d signals from transcripts", len(gathered_signals))

        if not gathered_signals and not existing_memories:
            return

        # Phase 3 (Consolidate): LLM merge, deduplicate, update
        existing_summary = "\n---\n".join(
            f"File: {m['filename']}\n{m['content'][:500]}" for m in existing_memories
        ) or "(no existing memories)"

        signals_text = "\n---\n".join(gathered_signals[:20]) or "(no new signals)"

        consolidate_prompt = f"""You are a memory consolidation assistant. Review existing memories and new conversation signals, then output updated memory files.

## Existing memories:
{existing_summary}

## New signals from recent conversations:
{signals_text}

## Instructions:
1. Identify memories that are outdated, duplicate, or should be merged
2. Identify new information from signals that deserves a memory entry
3. Convert any relative dates to absolute dates
4. Output updated memory files in this format (one or more):

MEMORY_FILE: <filename.md>
---
name: <name>
description: <one-line description>
type: <user|feedback|project|reference>
---
<content>

END_FILE

If no changes are needed, respond with NO_CHANGES."""

        from nanocc.messages import to_api_system_prompt
        response_text = ""
        async for event in provider.stream(
            messages=[{"role": "user", "content": consolidate_prompt}],
            system_prompt=to_api_system_prompt("You consolidate long-term memories."),
            tools=[],
            model=model,
            max_tokens=4096,
        ):
            if event.text:
                response_text += event.text

        if "NO_CHANGES" in response_text:
            logger.info("Dream Phase 3: no changes needed")
            return

        # Parse and write memory files
        files_written = 0
        for block in response_text.split("MEMORY_FILE:")[1:]:
            block = block.strip()
            end_idx = block.find("END_FILE")
            if end_idx > 0:
                block = block[:end_idx].strip()

            # Extract filename from first line
            lines = block.split("\n", 1)
            if len(lines) < 2:
                continue
            filename = lines[0].strip()
            content = lines[1].strip()

            if not filename.endswith(".md"):
                filename += ".md"

            filepath = self._memory_dir / filename
            filepath.write_text(content, encoding="utf-8")
            files_written += 1

        logger.info("Dream Phase 3: wrote %d memory files", files_written)

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
