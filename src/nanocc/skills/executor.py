"""Skill execution — expand skill prompts and inject into agent loop.

Skills are NOT code — they are prompt templates that get expanded
with $ARGUMENTS and injected as user messages.
"""

from __future__ import annotations

import logging
from typing import Any

from nanocc.skills.loader import SkillDefinition

logger = logging.getLogger(__name__)


def expand_skill(skill: SkillDefinition, args: str = "") -> str:
    """Expand a skill's content template with arguments.

    Replaces $ARGUMENTS placeholder with the provided args.
    """
    content = skill.content
    content = content.replace("$ARGUMENTS", args)
    content = content.replace("${ARGUMENTS}", args)

    # Add skill header
    header = f"[Skill: {skill.name}]"
    if skill.description:
        header += f" — {skill.description}"

    return f"{header}\n\n{content}"


def get_skill_context_modifier(skill: SkillDefinition) -> dict[str, Any] | None:
    """Get context modifications for a skill (temporary tool permissions).

    Returns a dict with allowed_tools to temporarily grant, or None.
    """
    if not skill.allowed_tools:
        return None

    return {
        "allowed_tools": skill.allowed_tools,
        "skill_name": skill.name,
    }
