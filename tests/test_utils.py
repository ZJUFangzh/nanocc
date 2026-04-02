"""Tests for utils — abort, tokens, config, cost, session_storage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nanocc.utils.abort import AbortController
from nanocc.utils.cost import UsageTracker
from nanocc.utils.session_storage import (
    list_sessions,
    load_session_state,
    load_transcript,
    save_session_state,
    save_transcript,
)


# ── AbortController ──

def test_abort_controller_initial():
    ac = AbortController()
    assert not ac.is_aborted


def test_abort_controller_abort():
    ac = AbortController()
    ac.abort()
    assert ac.is_aborted


def test_abort_controller_callback():
    called = []
    ac = AbortController()
    ac.on_abort(lambda: called.append(True))
    ac.abort()
    assert len(called) == 1


def test_abort_controller_double_abort():
    called = []
    ac = AbortController()
    ac.on_abort(lambda: called.append(True))
    ac.abort()
    ac.abort()
    # Callback should only fire once
    assert len(called) == 1


# ── UsageTracker ──

def test_usage_tracker_init():
    ut = UsageTracker()
    assert ut.total_input_tokens == 0
    assert ut.total_output_tokens == 0
    assert ut.api_calls == 0


def test_usage_tracker_add():
    ut = UsageTracker()
    ut.add(input_tokens=100, output_tokens=50)
    ut.add(input_tokens=200, output_tokens=100)
    assert ut.total_input_tokens == 300
    assert ut.total_output_tokens == 150
    assert ut.api_calls == 2


# ── session_storage ──

def test_save_load_transcript(monkeypatch, tmp_path):
    monkeypatch.setattr("nanocc.utils.session_storage.get_sessions_dir", lambda: tmp_path)

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    path = save_transcript("test-session", messages)
    assert path.exists()

    loaded = load_transcript("test-session")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0]["content"] == "hello"


def test_load_transcript_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("nanocc.utils.session_storage.get_sessions_dir", lambda: tmp_path)
    loaded = load_transcript("nonexistent")
    assert loaded is None


def test_save_load_session_state(monkeypatch, tmp_path):
    monkeypatch.setattr("nanocc.utils.session_storage.get_sessions_dir", lambda: tmp_path)

    state = {"model": "test", "cwd": "/tmp"}
    save_session_state("test-session", state)
    loaded = load_session_state("test-session")
    assert loaded is not None
    assert loaded["model"] == "test"


def test_list_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr("nanocc.utils.session_storage.get_sessions_dir", lambda: tmp_path)

    save_transcript("s1", [{"role": "user", "content": "a"}])
    save_transcript("s2", [{"role": "user", "content": "b"}])

    sessions = list_sessions()
    assert len(sessions) == 2
    ids = [s["session_id"] for s in sessions]
    assert "s1" in ids
    assert "s2" in ids
