"""Daily log memory — append-only journal for Assistant mode.

In Assistant mode, memory is written as daily logs instead of
real-time MEMORY.md index maintenance. /dream distills logs
into the index periodically.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path


class DailyLogMemory:
    """Append-only daily log for Assistant mode."""

    def __init__(self, memory_dir: Path) -> None:
        self._base_dir = memory_dir / "logs"

    def get_log_path(self, d: date | None = None) -> Path:
        """Get path for a specific date's log: logs/YYYY/MM/YYYY-MM-DD.md"""
        d = d or date.today()
        dir_path = self._base_dir / str(d.year) / f"{d.month:02d}"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{d.isoformat()}.md"

    async def append(self, content: str) -> None:
        """Append to today's log file."""
        path = self.get_log_path()
        with open(path, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%H:%M:%S")
            f.write(f"\n## {timestamp}\n\n{content}\n")

    def read_today(self) -> str:
        """Read today's log."""
        path = self.get_log_path()
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def read_recent(self, days: int = 3) -> str:
        """Read logs from the last N days."""
        parts: list[str] = []
        today = date.today()
        for i in range(days):
            d = date.fromordinal(today.toordinal() - i)
            path = self.get_log_path(d)
            if path.is_file():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"# {d.isoformat()}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    async def build_prompt(self, memory_index: str = "") -> str:
        """Build the Assistant mode memory prompt."""
        parts: list[str] = []

        if memory_index:
            parts.append(f"# Consolidated Memory\n\n{memory_index}")

        today_log = self.read_today()
        if today_log:
            parts.append(f"# Today's Log\n\n{today_log}")

        return "\n\n".join(parts)
