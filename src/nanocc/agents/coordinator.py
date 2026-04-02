"""Coordinator — dispatcher + workers pattern.

Decomposes a task into subtasks, runs workers in parallel (reads)
or serially (writes), and aggregates results.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from nanocc.agents.fork import fork_agent
from nanocc.messages import get_text_content
from nanocc.providers.base import LLMProvider
from nanocc.tools.base import BaseTool
from nanocc.types import AssistantMessage, Terminal

logger = logging.getLogger(__name__)


@dataclass
class SubtaskResult:
    prompt: str
    response: str
    success: bool


async def run_parallel_subtasks(
    subtasks: list[str],
    provider: LLMProvider,
    model: str,
    system_prompt: str | list[dict[str, Any]],
    tools: list[BaseTool],
    cwd: str = ".",
    max_concurrent: int = 5,
) -> list[SubtaskResult]:
    """Run multiple subtasks in parallel with bounded concurrency."""
    sem = asyncio.Semaphore(max_concurrent)
    results: list[SubtaskResult] = []

    async def run_one(prompt: str) -> SubtaskResult:
        async with sem:
            collected_text = ""
            success = True
            async for event in fork_agent(
                prompt=prompt,
                provider=provider,
                model=model,
                system_prompt=system_prompt,
                tools=tools,
                cwd=cwd,
                max_turns=5,
            ):
                if isinstance(event, AssistantMessage):
                    text = get_text_content(event)
                    if text:
                        collected_text = text
                elif isinstance(event, Terminal):
                    if event.reason == Terminal.MODEL_ERROR:
                        success = False

            return SubtaskResult(
                prompt=prompt,
                response=collected_text,
                success=success,
            )

    tasks = [asyncio.create_task(run_one(p)) for p in subtasks]
    for task in asyncio.as_completed(tasks):
        result = await task
        results.append(result)

    return results
