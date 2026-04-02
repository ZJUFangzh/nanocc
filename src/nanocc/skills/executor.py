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


async def execute_skill(
    skill: SkillDefinition,
    args: str,
    provider: Any,
    model: str,
    system_prompt: str | list,
    tools: list,
    cwd: str = ".",
    parent_abort: Any = None,
) -> str:
    """Execute a skill. Inline mode returns expanded prompt, fork mode runs in sub-agent.

    - context="inline": returns the expanded prompt for injection into current conversation
    - context="fork": runs in an isolated sub-agent, returns collected text response
    """
    expanded = expand_skill(skill, args)

    if skill.context != "fork":
        return expanded

    # Fork mode: run in isolated sub-agent
    from nanocc.agents.fork import fork_agent
    from nanocc.messages import get_text_content
    from nanocc.tools.base import BaseTool
    from nanocc.types import AssistantMessage, Terminal

    # Filter tools if skill specifies allowed_tools
    if skill.allowed_tools:
        from nanocc.tools.registry import find_tool
        fork_tools = [t for t in tools if t.name in skill.allowed_tools]
    else:
        fork_tools = tools

    response_parts: list[str] = []
    async for event in fork_agent(
        prompt=expanded,
        provider=provider,
        model=skill.model or model,
        system_prompt=system_prompt,
        tools=fork_tools,
        cwd=cwd,
        max_turns=10,
        parent_abort=parent_abort,
    ):
        if isinstance(event, AssistantMessage):
            text = get_text_content(event)
            if text:
                response_parts.append(text)
        elif isinstance(event, Terminal):
            break

    return "\n".join(response_parts) if response_parts else "(skill completed with no output)"
