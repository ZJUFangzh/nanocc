"""Tests for context.py — system prompt assembly."""

from __future__ import annotations

from nanocc.context import build_system_prompt


def test_build_system_prompt_basic():
    result = build_system_prompt(base_prompt="You are helpful.", cwd=".")
    assert isinstance(result, list)
    assert len(result) >= 1
    # First block should contain the base prompt
    assert "You are helpful" in result[0]["text"]


def test_build_system_prompt_with_user_context():
    result = build_system_prompt(
        base_prompt="Base.",
        user_context={"Project Instructions": "Use snake_case"},
        cwd=".",
    )
    texts = [b["text"] for b in result]
    full = "\n".join(texts)
    assert "snake_case" in full


def test_build_system_prompt_with_system_context():
    result = build_system_prompt(
        base_prompt="Base.",
        system_context={"Custom": "extra info"},
        cwd=".",
    )
    texts = [b["text"] for b in result]
    full = "\n".join(texts)
    assert "extra info" in full


def test_build_system_prompt_cache_control():
    result = build_system_prompt(base_prompt="Base.", cwd=".")
    # At least the first segment should have cache_control
    has_cache = any(b.get("cache_control") for b in result)
    assert has_cache


def test_build_system_prompt_includes_cwd():
    result = build_system_prompt(base_prompt="Base.", cwd="/test/path")
    texts = [b["text"] for b in result]
    full = "\n".join(texts)
    assert "/test/path" in full
