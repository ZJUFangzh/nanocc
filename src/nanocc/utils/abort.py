"""AbortController — asyncio-based cancellation signal."""

from __future__ import annotations

import asyncio
from typing import Callable


class AbortController:
    """Cancellation signal for the agent loop and tool execution.

    Mirrors the browser/Node.js AbortController pattern.
    """

    def __init__(self) -> None:
        self._aborted = False
        self._event = asyncio.Event()
        self._callbacks: list[Callable[[], None]] = []

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    def abort(self) -> None:
        if self._aborted:
            return
        self._aborted = True
        self._event.set()
        for cb in self._callbacks:
            cb()

    def on_abort(self, callback: Callable[[], None]) -> None:
        if self._aborted:
            callback()
        else:
            self._callbacks.append(callback)

    async def wait(self) -> None:
        """Block until aborted."""
        await self._event.wait()

    def reset(self) -> None:
        """Reset for reuse between turns."""
        self._aborted = False
        self._event.clear()
        self._callbacks.clear()
