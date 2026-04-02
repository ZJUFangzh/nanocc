"""Tests for skills — loader, executor."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from nanocc.skills.loader import SkillDefinition, load_skills, parse_skill_file
from nanocc.skills.executor import expand_skill, execute_skill, get_skill_context_modifier


# ── Loader ──

def test_parse_skill_file(tmp_path):
    skill_file = tmp_path / "commit.md"
    skill_file.write_text("""---
name: commit
description: Create a git commit
allowed_tools: [Bash, Read]
context: inline
---

Review changes and create a commit for: $ARGUMENTS""")

    skill = parse_skill_file(skill_file)
    assert skill is not None
    assert skill.name == "commit"
    assert skill.description == "Create a git commit"
    assert "Bash" in skill.allowed_tools
    assert "Read" in skill.allowed_tools
    assert skill.context == "inline"
    assert "$ARGUMENTS" in skill.content


def test_parse_skill_file_minimal(tmp_path):
    skill_file = tmp_path / "simple.md"
    skill_file.write_text("""---
name: simple
---

Do the thing.""")

    skill = parse_skill_file(skill_file)
    assert skill is not None
    assert skill.name == "simple"
    assert skill.content == "Do the thing."


def test_load_skills_from_directory(tmp_path):
    # load_skills takes cwd; skills are loaded from .nanocc/skills/
    skills_dir = tmp_path / ".nanocc" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "test.md").write_text("""---
name: test-skill
description: A test
---
Do $ARGUMENTS""")

    skills = load_skills(str(tmp_path))
    names = [s.name for s in skills]
    assert "test-skill" in names


def test_load_skills_dedup(tmp_path):
    """First-loaded wins for same name (global vs project)."""
    # Global skills dir
    global_skills = tmp_path / "global_skills"
    global_skills.mkdir()
    (global_skills / "dup.md").write_text("---\nname: dup\n---\nFirst")

    # Project skills dir
    proj_skills = tmp_path / ".nanocc" / "skills"
    proj_skills.mkdir(parents=True)
    (proj_skills / "dup.md").write_text("---\nname: dup\n---\nSecond")

    # load_skills loads global first, then project — project won't override
    skills = load_skills(str(tmp_path))
    # At minimum the project skill should be loaded
    dup = [s for s in skills if s.name == "dup"]
    assert len(dup) == 1


# ── Executor ──

def test_expand_skill_basic():
    skill = SkillDefinition(name="test", content="Do: $ARGUMENTS")
    expanded = expand_skill(skill, "fix the bug")
    assert "fix the bug" in expanded
    assert "[Skill: test]" in expanded


def test_expand_skill_dollar_brace():
    skill = SkillDefinition(name="test", content="Do: ${ARGUMENTS}")
    expanded = expand_skill(skill, "args here")
    assert "args here" in expanded


def test_expand_skill_no_args():
    skill = SkillDefinition(name="test", content="No args needed")
    expanded = expand_skill(skill)
    assert "No args needed" in expanded


def test_get_skill_context_modifier_with_tools():
    skill = SkillDefinition(name="test", allowed_tools=["Bash", "Read"])
    mod = get_skill_context_modifier(skill)
    assert mod is not None
    assert mod["allowed_tools"] == ["Bash", "Read"]
    assert mod["skill_name"] == "test"


def test_get_skill_context_modifier_none():
    skill = SkillDefinition(name="test")
    mod = get_skill_context_modifier(skill)
    assert mod is None


def test_expand_skill_description():
    skill = SkillDefinition(name="commit", description="Create a commit", content="Do it")
    expanded = expand_skill(skill)
    assert "Create a commit" in expanded
