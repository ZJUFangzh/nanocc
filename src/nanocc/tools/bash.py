"""BashTool — execute shell commands."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from nanocc.constants import BASH_DEFAULT_TIMEOUT_MS, BASH_MAX_OUTPUT_UPPER_LIMIT
from nanocc.tools.base import BaseTool
from nanocc.types import PermissionBehavior, PermissionResult, ToolResult, ToolUseContext


class BashTool(BaseTool):
    name = "Bash"
    description = "Execute a shell command and return its output."
    is_read_only = False
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds (max 600000).",
            },
        },
        "required": ["command"],
    }

    async def check_permissions(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> PermissionResult:
        return PermissionResult(behavior=PermissionBehavior.ASK, message=input.get("command", ""))

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        command = input.get("command", "")
        timeout_ms = min(input.get("timeout", BASH_DEFAULT_TIMEOUT_MS), 600_000)
        timeout_s = timeout_ms / 1000

        cwd = context.cwd or "."

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, "TERM": "dumb"},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    content=f"Command timed out after {timeout_s:.0f}s",
                    is_error=True,
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Truncate large output
            if len(stdout) > BASH_MAX_OUTPUT_UPPER_LIMIT:
                stdout = stdout[:BASH_MAX_OUTPUT_UPPER_LIMIT] + "\n... (truncated)"
            if len(stderr) > BASH_MAX_OUTPUT_UPPER_LIMIT:
                stderr = stderr[:BASH_MAX_OUTPUT_UPPER_LIMIT] + "\n... (truncated)"

            output_parts = []
            if stdout.strip():
                output_parts.append(stdout.rstrip())
            if stderr.strip():
                output_parts.append(f"STDERR:\n{stderr.rstrip()}")

            exit_code = proc.returncode or 0
            if exit_code != 0:
                output_parts.append(f"Exit code: {exit_code}")

            content = "\n".join(output_parts) if output_parts else "(no output)"

            return ToolResult(content=content, is_error=exit_code != 0)

        except Exception as e:
            return ToolResult(content=f"Error executing command: {e}", is_error=True)
