"""SkillTool — expand and inject skill prompts into the agent loop."""

from __future__ import annotations

from typing import Any

from nanocc.skills.executor import expand_skill
from nanocc.skills.loader import SkillDefinition, load_skills
from nanocc.tools.base import BaseTool
from nanocc.types import PermissionBehavior, PermissionResult, ToolResult, ToolUseContext


class SkillTool(BaseTool):
    name = "Skill"
    description = "Execute a skill (slash command) by name. Skills are prompt templates that provide specialized capabilities."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "The skill name to execute (e.g. 'commit', 'review-pr').",
            },
            "args": {
                "type": "string",
                "description": "Optional arguments for the skill.",
            },
        },
        "required": ["skill"],
    }

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] | None = None

    def _ensure_loaded(self, context: ToolUseContext) -> None:
        if self._skills is None:
            skills = load_skills(context.cwd)
            self._skills = {s.name: s for s in skills}

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        self._ensure_loaded(context)

        skill_name = input.get("skill", "")
        args = input.get("args", "")

        skill = self._skills.get(skill_name) if self._skills else None
        if not skill:
            available = list(self._skills.keys()) if self._skills else []
            return ToolResult(
                content=f"Unknown skill: '{skill_name}'. Available: {', '.join(available)}",
                is_error=True,
            )

        expanded = expand_skill(skill, args)
        return ToolResult(content=expanded)
