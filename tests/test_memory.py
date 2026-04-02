"""Tests for memory system — memdir, session_memory, extract, auto_dream, daily_log, claude_md."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from nanocc.memory.session_memory import SECTIONS, TEMPLATE, SessionMemory
from nanocc.memory.extract import build_extract_prompt, parse_extract_response
from nanocc.memory.auto_dream import AutoDreamEngine
from nanocc.memory.daily_log import DailyLogMemory
from nanocc.messages import create_assistant_message, create_user_message
from nanocc.types import TextBlock, UserMessage, AssistantMessage


# ── session_memory ──

def test_session_memory_10_sections():
    assert len(SECTIONS) == 10


def test_session_memory_sections_content():
    expected = [
        "Current State", "Task", "Key Files", "Recent Changes",
        "Errors Encountered", "Open Questions", "Dependencies",
        "Decisions Made", "Next Steps", "Worklog",
    ]
    assert SECTIONS == expected


def test_session_memory_template():
    for section in SECTIONS:
        assert f"## {section}" in TEMPLATE


def test_session_memory_should_update_init():
    sm = SessionMemory()
    # Below init threshold
    assert not sm.should_update(5000, 0)
    # Above threshold but no tool calls
    assert not sm.should_update(15000, 0)
    # Above threshold with tool calls
    assert sm.should_update(15000, 3)


def test_session_memory_should_update_incremental():
    sm = SessionMemory()
    sm.initialized = True
    sm.tokens_at_last_update = 10000
    sm.tool_calls_since_update = 0

    # Small delta
    assert not sm.should_update(11000, 1)
    # Large delta with enough tool calls
    assert sm.should_update(16000, 3)


def test_session_memory_update():
    sm = SessionMemory()
    sm.update("## Current State\nworking", 15000)
    assert sm.initialized
    assert sm.tokens_at_last_update == 15000
    assert sm.tool_calls_since_update == 0
    assert sm.content == "## Current State\nworking"


def test_session_memory_get_prompt():
    sm = SessionMemory()
    assert sm.get_prompt() == ""

    sm.content = "## Task\nfixing bugs"
    prompt = sm.get_prompt()
    assert "# Session Memory" in prompt
    assert "fixing bugs" in prompt


# ── extract ──

def test_build_extract_prompt_with_messages():
    msgs = [
        create_user_message("I'm a senior engineer working on auth"),
        create_assistant_message([TextBlock(text="I'll help with the auth system")]),
    ]
    prompt = build_extract_prompt(msgs)
    assert prompt is not None
    assert "senior engineer" in prompt
    assert "auth" in prompt


def test_build_extract_prompt_empty():
    prompt = build_extract_prompt([])
    assert prompt is None


def test_build_extract_prompt_short_messages():
    msgs = [create_user_message("hi")]
    prompt = build_extract_prompt(msgs)
    # "hi" is only 2 chars, below the 20 char threshold
    assert prompt is None


def test_parse_extract_response_valid():
    response = """TYPE: feedback
NAME: no_mocking
DESCRIPTION: Don't mock database in tests
CONTENT:
Integration tests must hit a real database, not mocks.
Reason: prior incident where mock/prod divergence masked a broken migration."""

    result = parse_extract_response(response)
    assert result is not None
    assert result["type"] == "feedback"
    assert result["name"] == "no_mocking"
    assert "real database" in result["content"]


def test_parse_extract_response_no_memory():
    assert parse_extract_response("NO_MEMORY") is None


def test_parse_extract_response_malformed():
    assert parse_extract_response("random text without structure") is None


# ── auto_dream ──

def test_auto_dream_should_dream_no_sessions():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = AutoDreamEngine(Path(tmpdir))
        assert not engine.should_dream()


def test_auto_dream_should_dream_gating():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = AutoDreamEngine(Path(tmpdir))

        # Set recent dream time
        engine._save_state({"last_dream_time": time.time(), "sessions_since_dream": 0})
        for _ in range(5):
            engine.record_session()

        # Recent dream → False
        assert not engine.should_dream()

        # Old dream → True
        state = engine._load_state()
        state["last_dream_time"] = time.time() - 25 * 3600
        engine._save_state(state)
        assert engine.should_dream()


def test_auto_dream_lock():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = AutoDreamEngine(Path(tmpdir))
        assert engine._acquire_lock()
        assert not engine._acquire_lock()
        engine._release_lock()
        assert engine._acquire_lock()
        engine._release_lock()


def test_auto_dream_record_session():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = AutoDreamEngine(Path(tmpdir))
        engine.record_session()
        engine.record_session()
        state = engine._load_state()
        assert state["sessions_since_dream"] == 2


# ── daily_log ──

def test_daily_log_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = DailyLogMemory(Path(tmpdir))
        path = log.get_log_path()
        assert path.name.endswith(".md")
        assert "/logs/" in str(path)


@pytest.mark.asyncio
async def test_daily_log_append():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = DailyLogMemory(Path(tmpdir))
        await log.append("First entry")
        await log.append("Second entry")

        content = log.read_today()
        assert "First entry" in content
        assert "Second entry" in content


@pytest.mark.asyncio
async def test_daily_log_build_prompt():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = DailyLogMemory(Path(tmpdir))
        await log.append("Today's work")
        prompt = await log.build_prompt()
        assert "Today's work" in prompt


# ── memdir ──

def test_memdir_parse_memory_file():
    from nanocc.memory.memdir import parse_memory_file

    content = """---
name: test_memory
description: A test memory
type: user
---

User prefers terse responses."""

    result = parse_memory_file(content, "test.md")
    assert result["name"] == "test_memory"
    assert result["type"] == "user"
    assert "terse responses" in result["body"]


def test_memdir_parse_no_frontmatter():
    from nanocc.memory.memdir import parse_memory_file

    content = "Just plain text content"
    result = parse_memory_file(content, "plain.md")
    assert result["body"] == content
    assert result["type"] == "project"  # default


# ── claude_md ──

def test_claude_md_load(tmp_path):
    from nanocc.memory.claude_md import load_claude_md

    # Create a CLAUDE.md in the test directory
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# Project Rules\nUse snake_case")

    content = load_claude_md(str(tmp_path))
    assert "snake_case" in content
