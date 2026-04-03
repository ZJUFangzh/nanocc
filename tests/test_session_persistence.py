"""Tests for session persistence — transcript append, compact boundary, resume."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from nanocc.engine import QueryEngine, QueryEngineConfig
from nanocc.messages import (
    create_assistant_message,
    create_system_message,
    create_user_message,
    create_user_message_with_blocks,
    from_api_message,
    from_api_messages,
    message_to_transcript,
    to_transcript_messages,
)
from nanocc.types import (
    AssistantMessage,
    SystemMessage,
    SystemMessageSubtype,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from nanocc.utils.session_storage import (
    append_messages,
    list_sessions,
    load_session_state,
    load_transcript,
    load_transcript_after_boundary,
    save_meta,
    save_session_state,
)

from tests.conftest import MockProvider, text_events


# ── Helpers ───────────────────────────────────────────────────────────────


@pytest.fixture
def sessions_dir(tmp_path):
    """Redirect sessions dir to a temp directory."""
    d = tmp_path / "sessions"
    d.mkdir()
    with patch("nanocc.utils.session_storage.get_sessions_dir", return_value=d):
        yield d


@pytest.fixture
def engine_with_sessions(sessions_dir):
    """Engine that saves to temp sessions dir."""
    provider = MockProvider([text_events("ok")])
    config = QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/test-project")
    eng = QueryEngine(config)
    # Also patch get_sessions_dir in engine's save_session imports
    with patch("nanocc.utils.session_storage.get_sessions_dir", return_value=sessions_dir):
        yield eng


# ── 1. SystemMessage round-trip ───────────────────────────────────────────


def test_system_message_to_transcript():
    """SystemMessage serializes to transcript format with role/subtype/content."""
    msg = create_system_message(
        SystemMessageSubtype.COMPACT_BOUNDARY,
        "Conversation compacted. Original messages: 10",
    )
    result = message_to_transcript(msg)
    assert result["role"] == "system"
    assert result["subtype"] == "compact_boundary"
    assert result["content"] == "Conversation compacted. Original messages: 10"


def test_system_message_deserialize():
    """SystemMessage deserializes from transcript format."""
    api_msg = {
        "role": "system",
        "subtype": "compact_boundary",
        "content": "Conversation compacted. Original messages: 10",
    }
    msg = from_api_message(api_msg)
    assert isinstance(msg, SystemMessage)
    assert msg.subtype == SystemMessageSubtype.COMPACT_BOUNDARY
    assert msg.text == "Conversation compacted. Original messages: 10"


def test_system_message_round_trip():
    """SystemMessage survives serialize → deserialize."""
    original = create_system_message(
        SystemMessageSubtype.COMPACT_BOUNDARY,
        "Compacted 20 messages",
    )
    serialized = message_to_transcript(original)
    restored = from_api_message(serialized)

    assert isinstance(restored, SystemMessage)
    assert restored.subtype == original.subtype
    assert restored.text == original.text


def test_to_transcript_messages_includes_system():
    """to_transcript_messages includes SystemMessage (unlike to_api_messages)."""
    messages = [
        create_user_message("hello"),
        create_system_message(SystemMessageSubtype.COMPACT_BOUNDARY, "compacted"),
        create_assistant_message([TextBlock(text="hi")]),
    ]
    result = to_transcript_messages(messages)
    assert len(result) == 3
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "system"
    assert result[2]["role"] == "assistant"


def test_from_api_messages_handles_system():
    """from_api_messages correctly restores SystemMessage."""
    api_msgs = [
        {"role": "user", "content": "hello"},
        {"role": "system", "subtype": "compact_boundary", "content": "compacted"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]
    messages = from_api_messages(api_msgs)
    assert len(messages) == 3
    assert isinstance(messages[0], UserMessage)
    assert isinstance(messages[1], SystemMessage)
    assert isinstance(messages[2], AssistantMessage)


# ── 2. Incremental append ─────────────────────────────────────────────────


def test_append_messages_incremental(sessions_dir):
    """Append only new messages to transcript JSONL."""
    sid = "test-append"

    msgs = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": [{"type": "text", "text": "reply1"}]},
        {"role": "user", "content": "msg2"},
    ]

    # First save: all 3 messages
    new_idx = append_messages(sid, msgs, 0)
    assert new_idx == 3

    # Verify JSONL has 3 lines
    transcript_path = sessions_dir / sid / "transcript.jsonl"
    lines = transcript_path.read_text().strip().split("\n")
    assert len(lines) == 3

    # Second save: 2 more messages
    msgs.append({"role": "assistant", "content": [{"type": "text", "text": "reply2"}]})
    msgs.append({"role": "user", "content": "msg3"})
    new_idx = append_messages(sid, msgs, new_idx)
    assert new_idx == 5

    # Verify JSONL now has 5 lines
    lines = transcript_path.read_text().strip().split("\n")
    assert len(lines) == 5


def test_append_messages_noop_when_caught_up(sessions_dir):
    """No-op when all messages are already saved."""
    sid = "test-noop"
    msgs = [{"role": "user", "content": "hello"}]
    idx = append_messages(sid, msgs, 0)
    assert idx == 1

    # Call again with same index
    idx2 = append_messages(sid, msgs, idx)
    assert idx2 == 1

    # File should still have 1 line
    transcript_path = sessions_dir / sid / "transcript.jsonl"
    lines = transcript_path.read_text().strip().split("\n")
    assert len(lines) == 1


# ── 3. Load after compact boundary ───────────────────────────────────────


def test_load_after_boundary_no_boundary(sessions_dir):
    """Without a boundary, returns full transcript."""
    sid = "test-no-boundary"
    msgs = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": [{"type": "text", "text": "reply1"}]},
    ]
    append_messages(sid, msgs, 0)

    result = load_transcript_after_boundary(sid)
    assert result is not None
    assert len(result) == 2


def test_load_after_boundary_with_boundary(sessions_dir):
    """With a compact boundary, returns boundary + messages after it."""
    sid = "test-with-boundary"
    msgs = [
        {"role": "user", "content": "old msg 1"},
        {"role": "assistant", "content": [{"type": "text", "text": "old reply 1"}]},
        {"role": "user", "content": "old msg 2"},
        {"role": "assistant", "content": [{"type": "text", "text": "old reply 2"}]},
        # Compact boundary
        {"role": "system", "subtype": "compact_boundary", "content": "Compacted 4 messages"},
        # Summary + new messages
        {"role": "user", "content": "[Previous conversation summary]\n\nSummary here"},
        {"role": "user", "content": "new msg after compact"},
        {"role": "assistant", "content": [{"type": "text", "text": "new reply"}]},
    ]
    append_messages(sid, msgs, 0)

    result = load_transcript_after_boundary(sid)
    assert result is not None
    # Should get: boundary + summary + new msg + new reply = 4
    assert len(result) == 4
    assert result[0]["role"] == "system"
    assert result[0]["subtype"] == "compact_boundary"
    assert result[1]["content"] == "[Previous conversation summary]\n\nSummary here"


# ── 4. Multiple compact boundaries ───────────────────────────────────────


def test_load_after_multiple_boundaries(sessions_dir):
    """With multiple boundaries, loads from the LAST one."""
    sid = "test-multi-boundary"
    msgs = [
        {"role": "user", "content": "era 1"},
        {"role": "system", "subtype": "compact_boundary", "content": "First compact"},
        {"role": "user", "content": "era 2 summary"},
        {"role": "user", "content": "era 2 msg"},
        {"role": "system", "subtype": "compact_boundary", "content": "Second compact"},
        {"role": "user", "content": "era 3 summary"},
        {"role": "user", "content": "era 3 msg"},
        {"role": "assistant", "content": [{"type": "text", "text": "era 3 reply"}]},
    ]
    append_messages(sid, msgs, 0)

    result = load_transcript_after_boundary(sid)
    assert result is not None
    # Should get: second boundary + era 3 summary + era 3 msg + era 3 reply = 4
    assert len(result) == 4
    assert result[0]["subtype"] == "compact_boundary"
    assert result[0]["content"] == "Second compact"


# ── 5. Engine save/restore round-trip ─────────────────────────────────────


def test_engine_save_restore_round_trip(sessions_dir):
    """Engine save_session → restore_state preserves messages/usage/memory."""
    provider = MockProvider()
    config = QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project")
    eng = QueryEngine(config)

    # Populate state
    eng.messages.append(create_user_message("hello"))
    eng.messages.append(create_assistant_message([TextBlock(text="hi")]))
    eng.usage.total_input_tokens = 500
    eng.usage.total_output_tokens = 200
    eng.usage.api_calls = 2
    eng.session_memory.content = "## Current Task\nworking on tests"
    eng.session_memory.initialized = True

    # Save
    eng.save_session()

    # Restore into new engine
    eng2 = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project"))
    state = load_session_state(eng.session_id)
    assert state is not None

    # Use transcript-aware restore
    transcript_msgs = load_transcript_after_boundary(eng.session_id)
    assert transcript_msgs is not None
    state["messages"] = transcript_msgs
    eng2.restore_state(state)

    assert len(eng2.messages) == 2
    assert eng2.messages[0].role == "user"
    assert eng2.messages[1].role == "assistant"
    assert eng2.usage.total_input_tokens == 500
    assert eng2.usage.total_output_tokens == 200
    assert eng2.session_memory.content == "## Current Task\nworking on tests"


# ── 6. Resume after compact ──────────────────────────────────────────────


def test_resume_after_compact(sessions_dir):
    """Full flow: messages → compact → more messages → save → load after boundary → restore."""
    provider = MockProvider()
    eng = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project"))

    # Pre-compact messages
    eng.messages.append(create_user_message("old question 1"))
    eng.messages.append(create_assistant_message([TextBlock(text="old answer 1")]))
    eng.messages.append(create_user_message("old question 2"))
    eng.messages.append(create_assistant_message([TextBlock(text="old answer 2")]))

    # Simulate compact: replace messages with boundary + summary
    eng.messages.clear()
    eng.messages.append(create_system_message(
        SystemMessageSubtype.COMPACT_BOUNDARY,
        "Conversation compacted. Original messages: 4",
    ))
    eng.messages.append(create_user_message(
        "[Previous conversation summary]\n\nUser asked two questions about testing."
    ))

    # Save mid-compact state (this writes boundary to transcript)
    eng.save_session()

    # Post-compact: new messages
    eng.messages.append(create_user_message("new question"))
    eng.messages.append(create_assistant_message([TextBlock(text="new answer")]))
    eng.save_session()

    # Now resume in a new engine
    eng2 = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project"))
    transcript_msgs = load_transcript_after_boundary(eng.session_id)
    assert transcript_msgs is not None

    state = load_session_state(eng.session_id)
    state["messages"] = transcript_msgs
    eng2.restore_state(state)

    # Should have: boundary + summary + new question + new answer = 4
    assert len(eng2.messages) == 4
    assert isinstance(eng2.messages[0], SystemMessage)
    assert eng2.messages[0].subtype == SystemMessageSubtype.COMPACT_BOUNDARY
    assert isinstance(eng2.messages[1], UserMessage)
    assert isinstance(eng2.messages[2], UserMessage)
    assert isinstance(eng2.messages[3], AssistantMessage)


# ── 7. Micro compact after resume ────────────────────────────────────────


def test_micro_compact_after_resume(sessions_dir):
    """After resume, micro_compact naturally clears old tool results."""
    from nanocc.compact.micro_compact import micro_compact

    provider = MockProvider()
    eng = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project"))

    # Create many tool result messages
    for i in range(10):
        eng.messages.append(create_assistant_message([
            ToolUseBlock(id=f"t{i}", name="Bash", input={"command": f"echo {i}"}),
        ]))
        eng.messages.append(create_user_message_with_blocks([
            ToolResultBlock(tool_use_id=f"t{i}", content=f"output_{i}" * 100),
        ]))

    # Save
    eng.save_session()

    # Resume
    eng2 = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project"))
    transcript_msgs = load_transcript_after_boundary(eng.session_id)
    state = load_session_state(eng.session_id)
    state["messages"] = transcript_msgs
    eng2.restore_state(state)

    assert len(eng2.messages) == 20  # 10 assistant + 10 user

    # Run micro compact — should clear old tool results
    cleared = micro_compact(eng2.messages, keep_recent=5)
    assert cleared > 0

    # Recent results should still have content
    last_result = eng2.messages[-1]
    assert isinstance(last_result, UserMessage)
    assert isinstance(last_result.content, list)
    block = last_result.content[0]
    assert isinstance(block, ToolResultBlock)
    assert "output_9" in block.content


# ── 8. Edge cases ────────────────────────────────────────────────────────


def test_load_nonexistent_session(sessions_dir):
    """Loading a non-existent session returns None."""
    assert load_transcript("nonexistent") is None
    assert load_transcript_after_boundary("nonexistent") is None
    assert load_session_state("nonexistent") is None


def test_empty_transcript(sessions_dir):
    """Empty transcript returns empty list."""
    sid = "empty-session"
    # Create empty transcript file
    session_dir = sessions_dir / sid
    session_dir.mkdir()
    (session_dir / "transcript.jsonl").write_text("")

    result = load_transcript(sid)
    assert result == []

    result2 = load_transcript_after_boundary(sid)
    assert result2 == []


def test_save_session_creates_all_files(sessions_dir):
    """save_session creates transcript.jsonl, state.json, and meta.json."""
    provider = MockProvider()
    eng = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp/project"))
    eng.messages.append(create_user_message("hello"))

    eng.save_session()

    session_dir = sessions_dir / eng.session_id
    assert (session_dir / "transcript.jsonl").is_file()
    assert (session_dir / "state.json").is_file()
    assert (session_dir / "meta.json").is_file()

    # Verify meta content
    meta = json.loads((session_dir / "meta.json").read_text())
    assert meta["session_id"] == eng.session_id
    assert meta["message_count"] == 1
    assert meta["cwd"] == "/tmp/project"
    assert meta["model"] == "test-model"


# ── 9. list_sessions with cwd filter ─────────────────────────────────────


def test_list_sessions_filter_cwd(sessions_dir):
    """list_sessions filters by cwd when provided."""
    # Save sessions with different cwds
    save_meta("s1", message_count=5, cwd="/project/a", model="m1")
    save_meta("s2", message_count=3, cwd="/project/b", model="m2")
    save_meta("s3", message_count=8, cwd="/project/a", model="m3")

    # Filter by cwd
    result_a = list_sessions(cwd="/project/a")
    assert len(result_a) == 2
    sids = {s["session_id"] for s in result_a}
    assert sids == {"s1", "s3"}

    result_b = list_sessions(cwd="/project/b")
    assert len(result_b) == 1
    assert result_b[0]["session_id"] == "s2"

    # No filter returns all
    result_all = list_sessions()
    assert len(result_all) == 3


def test_list_sessions_sorted_by_time(sessions_dir):
    """list_sessions returns newest first."""
    import time

    save_meta("old", message_count=1, cwd="/tmp")
    time.sleep(0.05)
    save_meta("new", message_count=2, cwd="/tmp")

    result = list_sessions()
    assert result[0]["session_id"] == "new"
    assert result[1]["session_id"] == "old"


# ── 10. Engine _last_saved_index tracking ─────────────────────────────────


def test_last_saved_index_incremental(sessions_dir):
    """_last_saved_index tracks what's been saved to avoid duplicate writes."""
    provider = MockProvider()
    eng = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp"))

    assert eng._last_saved_index == 0

    eng.messages.append(create_user_message("msg1"))
    eng.messages.append(create_assistant_message([TextBlock(text="reply1")]))
    eng.save_session()
    assert eng._last_saved_index == 2

    eng.messages.append(create_user_message("msg2"))
    eng.save_session()
    assert eng._last_saved_index == 3

    # Verify transcript has exactly 3 lines
    transcript_path = sessions_dir / eng.session_id / "transcript.jsonl"
    lines = transcript_path.read_text().strip().split("\n")
    assert len(lines) == 3


def test_restore_sets_last_saved_index(sessions_dir):
    """restore_state sets _last_saved_index to avoid re-saving existing messages."""
    provider = MockProvider()
    eng = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp"))

    eng.messages.append(create_user_message("hello"))
    eng.messages.append(create_assistant_message([TextBlock(text="hi")]))
    eng.save_session()

    # Restore into new engine
    eng2 = QueryEngine(QueryEngineConfig(provider=provider, model="test-model", cwd="/tmp"))
    state = load_session_state(eng.session_id)
    transcript_msgs = load_transcript_after_boundary(eng.session_id)
    state["messages"] = transcript_msgs
    eng2.restore_state(state)

    # Should be caught up — no new messages to save
    assert eng2._last_saved_index == 2

    # Saving again should not duplicate
    eng2.save_session()
    transcript_path = sessions_dir / eng.session_id / "transcript.jsonl"
    lines = transcript_path.read_text().strip().split("\n")
    assert len(lines) == 2  # Still 2, not 4
