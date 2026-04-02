"""Skill discovery and loading — YAML frontmatter + Markdown prompt files.

Loading order (matching CC):
1. ~/.nanocc/skills/
2. .nanocc/skills/ (project-level)
3. Built-in bundled skills
Later-loaded same-name skills do NOT override earlier ones.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nanocc.utils.config import GLOBAL_CONFIG_DIR, PROJECT_CONFIG_DIR_NAME


@dataclass
class SkillDefinition:
    name: str
    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    context: str = "inline"  # "inline" or "fork"
    model: str | None = None
    hooks: dict[str, Any] | None = None
    content: str = ""  # Markdown prompt body
    source: str = ""   # File path


def load_skills(cwd: str) -> list[SkillDefinition]:
    """Load skills from all sources. First-loaded wins for same name."""
    skills: dict[str, SkillDefinition] = {}

    # 1. Global skills
    global_dir = GLOBAL_CONFIG_DIR / "skills"
    _load_skills_from_dir(global_dir, skills)

    # 2. Project skills
    proj_dir = Path(cwd) / PROJECT_CONFIG_DIR_NAME / "skills"
    _load_skills_from_dir(proj_dir, skills)

    # 3. Bundled skills
    bundled_dir = Path(__file__).parent / "bundled"
    _load_skills_from_dir(bundled_dir, skills)

    return list(skills.values())


def _load_skills_from_dir(directory: Path, skills: dict[str, SkillDefinition]) -> None:
    """Load .md skill files from a directory."""
    if not directory.is_dir():
        return

    for path in sorted(directory.glob("*.md")):
        try:
            skill = parse_skill_file(path)
            if skill and skill.name not in skills:
                skills[skill.name] = skill
        except Exception:
            pass


def parse_skill_file(path: Path) -> SkillDefinition | None:
    """Parse a skill .md file with YAML frontmatter."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Parse frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if not match:
        return None

    fm_text = match.group(1)
    body = match.group(2).strip()

    fm: dict[str, Any] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Handle list values (comma-separated)
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
            fm[key] = val

    name = fm.get("name", path.stem)
    if isinstance(name, list):
        name = name[0]

    allowed_tools = fm.get("allowed_tools", [])
    if isinstance(allowed_tools, str):
        allowed_tools = [t.strip() for t in allowed_tools.split(",")]

    return SkillDefinition(
        name=name,
        description=fm.get("description", ""),
        allowed_tools=allowed_tools,
        context=fm.get("context", "inline"),
        model=fm.get("model"),
        hooks=fm.get("hooks"),
        content=body,
        source=str(path),
    )
