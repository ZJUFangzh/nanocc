"""Hook engine — register, match, and execute hooks.

Hooks fire at tool_start, tool_complete, tool_error, and stop events.
Three types: command (shell), prompt (LLM injection), http (webhook).
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
from typing import Any

from nanocc.hooks.types import Hook, HookEvent, HookRegistration

logger = logging.getLogger(__name__)


class HookEngine:
    """Hook registration, matching, and execution."""

    def __init__(self) -> None:
        self._registrations: list[HookRegistration] = []

    def register(
        self,
        event: HookEvent,
        matcher: str | None,
        hooks: list[Hook],
        source: str = "settings",
        session_scoped: bool = False,
    ) -> None:
        self._registrations.append(
            HookRegistration(
                event=event, matcher=matcher, hooks=hooks,
                source=source, session_scoped=session_scoped,
            )
        )

    async def fire(
        self,
        event: HookEvent,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        result: Any = None,
    ) -> list[str]:
        """Fire hooks for an event. Returns list of output strings."""
        matched = self._match(event, tool_name, tool_input)
        if not matched:
            return []

        outputs: list[str] = []
        to_remove: list[HookRegistration] = []

        for reg, hook in matched:
            try:
                output = await self._execute_hook(hook, event, tool_name, tool_input, result)
                if output:
                    outputs.append(output)
            except Exception as e:
                logger.error("Hook execution error: %s", e)

            if hook.once:
                to_remove.append(reg)

        # Remove once-hooks
        for reg in to_remove:
            if reg in self._registrations:
                self._registrations.remove(reg)

        return outputs

    def unregister_session(self, source: str = "") -> None:
        """Remove session-scoped hooks."""
        self._registrations = [
            r for r in self._registrations
            if not r.session_scoped or (source and r.source != source)
        ]

    def _match(
        self,
        event: HookEvent,
        tool_name: str | None,
        tool_input: dict[str, Any] | None,
    ) -> list[tuple[HookRegistration, Hook]]:
        """Find matching hooks for an event."""
        matched: list[tuple[HookRegistration, Hook]] = []

        for reg in self._registrations:
            if reg.event != event:
                continue

            # Check matcher against tool name
            if reg.matcher and tool_name:
                if not fnmatch.fnmatch(tool_name, reg.matcher):
                    continue
            elif reg.matcher and not tool_name:
                continue

            for hook in reg.hooks:
                # Check if_condition
                if hook.if_condition and tool_name:
                    if not self._check_condition(hook.if_condition, tool_name, tool_input):
                        continue
                matched.append((reg, hook))

        return matched

    def _check_condition(
        self, condition: str, tool_name: str, tool_input: dict[str, Any] | None
    ) -> bool:
        """Check if a hook's if_condition matches.

        Format: "ToolName(pattern)" e.g. "Bash(git *)"
        """
        # Parse "ToolName(pattern)"
        if "(" in condition and condition.endswith(")"):
            cond_tool = condition[:condition.index("(")]
            cond_pattern = condition[condition.index("(") + 1:-1]

            if cond_tool != tool_name:
                return False

            # Match pattern against command/input
            if tool_input:
                cmd = tool_input.get("command", "")
                return fnmatch.fnmatch(cmd, cond_pattern)

        return fnmatch.fnmatch(tool_name, condition)

    async def _execute_hook(
        self,
        hook: Hook,
        event: HookEvent,
        tool_name: str | None,
        tool_input: dict[str, Any] | None,
        result: Any,
    ) -> str | None:
        """Execute a single hook."""
        env = {
            **os.environ,
            "HOOK_EVENT": event.value,
            "TOOL_NAME": tool_name or "",
        }

        if hook.type == "command" and hook.command:
            return await self._run_command(hook.command, env, hook.timeout)
        elif hook.type == "prompt" and hook.prompt:
            return hook.prompt  # Returned for injection into context
        elif hook.type == "http" and hook.url:
            return await self._send_http(hook.url, hook.headers, event, tool_name)
        return None

    async def _run_command(self, command: str, env: dict, timeout: int) -> str | None:
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace").strip()
            return output if output else None
        except asyncio.TimeoutError:
            logger.warning("Hook command timed out: %s", command[:50])
            return None
        except Exception as e:
            logger.error("Hook command error: %s", e)
            return None

    async def _send_http(
        self, url: str, headers: dict[str, str] | None,
        event: HookEvent, tool_name: str | None,
    ) -> str | None:
        try:
            import httpx
            payload = {"event": event.value, "tool": tool_name}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers or {})
                return resp.text if resp.status_code == 200 else None
        except Exception as e:
            logger.error("Hook HTTP error: %s", e)
            return None


def load_hooks_from_settings(settings: dict[str, Any]) -> list[HookRegistration]:
    """Parse hooks from settings.json format."""
    registrations: list[HookRegistration] = []
    hooks_config = settings.get("hooks", {})

    for event_name, entries in hooks_config.items():
        try:
            event = HookEvent(event_name)
        except ValueError:
            continue

        for entry in entries:
            matcher = entry.get("matcher")
            hooks = []
            for h in entry.get("hooks", []):
                hooks.append(Hook(
                    type=h.get("type", "command"),
                    command=h.get("command"),
                    prompt=h.get("prompt"),
                    url=h.get("url"),
                    headers=h.get("headers"),
                    if_condition=h.get("if"),
                    timeout=h.get("timeout", 30),
                    once=h.get("once", False),
                    async_=h.get("async", False),
                ))
            if hooks:
                registrations.append(HookRegistration(
                    event=event, matcher=matcher, hooks=hooks, source="settings",
                ))

    return registrations
