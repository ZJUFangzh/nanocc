"""Proactive engine — tick-based autonomous work for Assistant mode.

The agent is periodically woken up to decide if there's useful work to do.
If not, it must call the Sleep tool — no idle token burning.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TICK_INTERVAL = 60  # seconds


class WakeReason(str, Enum):
    TICK = "tick"
    USER_MESSAGE = "user_message"
    SHUTDOWN = "shutdown"


@dataclass
class WakeEvent:
    reason: WakeReason
    data: Any = None


class ProactiveEngine:
    """Tick-based wake loop for Assistant mode."""

    def __init__(self, tick_interval: int = DEFAULT_TICK_INTERVAL) -> None:
        self._tick_interval = tick_interval
        self._tick_task: asyncio.Task | None = None
        self._wake_queue: asyncio.Queue[WakeEvent] = asyncio.Queue()
        self._user_focused = True
        self._running = False

    async def start(self) -> None:
        """Start the tick loop."""
        self._running = True
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info("Proactive engine started (interval=%ds)", self._tick_interval)

    async def stop(self) -> None:
        """Stop the tick loop."""
        self._running = False
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
        # Drain queue
        while not self._wake_queue.empty():
            try:
                self._wake_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def wait_for_next(self) -> WakeEvent:
        """Wait for the next wake event (tick, user message, or shutdown)."""
        return await self._wake_queue.get()

    def send_user_message(self, message: Any) -> None:
        """Inject a user message into the wake queue."""
        self._wake_queue.put_nowait(WakeEvent(reason=WakeReason.USER_MESSAGE, data=message))

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._wake_queue.put_nowait(WakeEvent(reason=WakeReason.SHUTDOWN))

    def set_user_focus(self, focused: bool) -> None:
        """Update terminal focus state."""
        self._user_focused = focused

    @property
    def user_focused(self) -> bool:
        return self._user_focused

    async def _tick_loop(self) -> None:
        """Periodically emit tick events."""
        while self._running:
            await asyncio.sleep(self._tick_interval)
            if self._running:
                self._wake_queue.put_nowait(WakeEvent(reason=WakeReason.TICK))
