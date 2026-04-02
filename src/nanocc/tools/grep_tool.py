"""GrepTool — content search via ripgrep (with fallback to Python re)."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class GrepTool(BaseTool):
    name = "Grep"
    description = "Search file contents using regex. Uses ripgrep if available, else Python re."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in. Default: cwd.",
            },
            "glob": {
                "type": "string",
                "description": 'File glob filter (e.g. "*.py").',
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": "Output mode. Default: files_with_matches.",
            },
            "-i": {
                "type": "boolean",
                "description": "Case insensitive search.",
            },
            "-n": {
                "type": "boolean",
                "description": "Show line numbers. Default: true.",
            },
            "-C": {
                "type": "integer",
                "description": "Context lines around matches.",
            },
            "head_limit": {
                "type": "integer",
                "description": "Limit output entries. Default: 250.",
            },
        },
        "required": ["pattern"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        pattern = input.get("pattern", "")
        path = input.get("path", "") or context.cwd
        file_glob = input.get("glob", "")
        output_mode = input.get("output_mode", "files_with_matches")
        case_insensitive = input.get("-i", False)
        show_line_numbers = input.get("-n", True)
        context_lines = input.get("-C", 0)
        head_limit = input.get("head_limit", 250)

        if not os.path.isabs(path):
            path = os.path.join(context.cwd, path)

        # Try ripgrep first
        result = await self._try_ripgrep(
            pattern, path, file_glob, output_mode,
            case_insensitive, show_line_numbers, context_lines, head_limit,
        )
        if result is not None:
            return result

        # Fallback to Python re
        return self._python_grep(
            pattern, path, file_glob, output_mode,
            case_insensitive, show_line_numbers, head_limit,
        )

    async def _try_ripgrep(
        self,
        pattern: str,
        path: str,
        file_glob: str,
        output_mode: str,
        case_insensitive: bool,
        show_line_numbers: bool,
        context_lines: int,
        head_limit: int,
    ) -> ToolResult | None:
        """Try using ripgrep. Returns None if rg is not available."""
        import shutil
        rg_path = shutil.which("rg")
        if not rg_path:
            return None
        args = [rg_path]

        if output_mode == "files_with_matches":
            args.append("-l")
        elif output_mode == "count":
            args.append("-c")

        if case_insensitive:
            args.append("-i")
        if show_line_numbers and output_mode == "content":
            args.append("-n")
        if context_lines and output_mode == "content":
            args.extend(["-C", str(context_lines)])
        if file_glob:
            args.extend(["--glob", file_glob])

        args.extend(["--max-count", "1000"])
        args.append(pattern)
        args.append(path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        except FileNotFoundError:
            return None  # rg not installed
        except asyncio.TimeoutError:
            return ToolResult(content="Search timed out.", is_error=True)

        output = stdout.decode("utf-8", errors="replace").rstrip()

        if not output:
            return ToolResult(content="No matches found.")

        # Apply head limit
        lines = output.split("\n")
        if head_limit and len(lines) > head_limit:
            lines = lines[:head_limit]
            output = "\n".join(lines) + f"\n\n... (truncated at {head_limit} entries)"
        else:
            output = "\n".join(lines)

        return ToolResult(content=output)

    def _python_grep(
        self,
        pattern: str,
        path: str,
        file_glob: str,
        output_mode: str,
        case_insensitive: bool,
        show_line_numbers: bool,
        head_limit: int,
    ) -> ToolResult:
        """Fallback Python regex search."""
        import glob as glob_mod

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(content=f"Invalid regex: {e}", is_error=True)

        # Collect files to search
        if os.path.isfile(path):
            files = [path]
        else:
            glob_pattern = os.path.join(path, file_glob or "**/*")
            files = [f for f in glob_mod.glob(glob_pattern, recursive=True) if os.path.isfile(f)]

        results: list[str] = []
        count = 0

        for fpath in sorted(files):
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue

            file_matches = []
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    if output_mode == "content":
                        prefix = f"{i}:" if show_line_numbers else ""
                        file_matches.append(f"{prefix}{line.rstrip()}")
                    count += 1

            if file_matches and output_mode == "content":
                results.append(f"{fpath}:")
                results.extend(file_matches)
                results.append("")
            elif file_matches and output_mode == "files_with_matches":
                results.append(fpath)
            elif count and output_mode == "count":
                results.append(f"{fpath}:{count}")
                count = 0

            if head_limit and len(results) >= head_limit:
                results = results[:head_limit]
                break

        if not results:
            return ToolResult(content="No matches found.")

        return ToolResult(content="\n".join(results))
