"""Tests for messages — creation, API conversion, deserialization."""

from __future__ import annotations

from nanocc.messages import (
    content_block_to_api,
    count_content_blocks,
    create_assistant_message,
    create_tick_message,
    create_user_message,
    create_user_message_with_blocks,
    from_api_message,
    from_api_messages,
    get_text_content,
    get_tool_use_blocks,
    has_tool_use,
    message_to_api,
    to_api_messages,
)
from nanocc.types import (
    AssistantMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def test_create_user_message():
    msg = create_user_message("hello")
    assert isinstance(msg, UserMessage)
    assert msg.content == "hello"


def test_create_assistant_message():
    msg = create_assistant_message([TextBlock(text="hi")])
    assert isinstance(msg, AssistantMessage)
    assert len(msg.content) == 1


def test_create_tick_message():
    msg = create_tick_message()
    assert isinstance(msg, UserMessage)
    assert "<tick>" in msg.content


# ── API conversion ──

def test_content_block_to_api_text():
    result = content_block_to_api(TextBlock(text="hello"))
    assert result == {"type": "text", "text": "hello"}


def test_content_block_to_api_tool_use():
    result = content_block_to_api(ToolUseBlock(id="t1", name="Bash", input={"command": "ls"}))
    assert result["type"] == "tool_use"
    assert result["id"] == "t1"
    assert result["name"] == "Bash"


def test_content_block_to_api_tool_result():
    result = content_block_to_api(ToolResultBlock(tool_use_id="t1", content="ok"))
    assert result["type"] == "tool_result"
    assert not result.get("is_error")


def test_content_block_to_api_tool_result_error():
    result = content_block_to_api(ToolResultBlock(tool_use_id="t1", content="err", is_error=True))
    assert result["is_error"] is True


def test_message_to_api_user_string():
    msg = UserMessage(content="hello")
    api = message_to_api(msg)
    assert api == {"role": "user", "content": "hello"}


def test_message_to_api_user_blocks():
    msg = UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok")])
    api = message_to_api(msg)
    assert api["role"] == "user"
    assert isinstance(api["content"], list)


def test_message_to_api_assistant():
    msg = AssistantMessage(content=[TextBlock(text="hi")])
    api = message_to_api(msg)
    assert api["role"] == "assistant"


def test_to_api_messages():
    msgs = [create_user_message("a"), create_assistant_message([TextBlock(text="b")])]
    result = to_api_messages(msgs)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"


# ── Deserialization ──

def test_from_api_message_user_string():
    msg = from_api_message({"role": "user", "content": "hello"})
    assert isinstance(msg, UserMessage)
    assert msg.content == "hello"


def test_from_api_message_user_blocks():
    msg = from_api_message({
        "role": "user",
        "content": [
            {"type": "text", "text": "hi"},
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
        ],
    })
    assert isinstance(msg, UserMessage)
    assert len(msg.content) == 2


def test_from_api_message_assistant():
    msg = from_api_message({
        "role": "assistant",
        "content": [
            {"type": "text", "text": "reply"},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
        ],
    })
    assert isinstance(msg, AssistantMessage)
    assert len(msg.content) == 2
    assert isinstance(msg.content[0], TextBlock)
    assert isinstance(msg.content[1], ToolUseBlock)


def test_from_api_messages_round_trip():
    original = [
        create_user_message("hello"),
        create_assistant_message([
            TextBlock(text="hi"),
            ToolUseBlock(id="t1", name="Bash", input={"command": "ls"}),
        ]),
    ]
    api = to_api_messages(original)
    restored = from_api_messages(api)
    assert len(restored) == 2
    assert isinstance(restored[0], UserMessage)
    assert isinstance(restored[1], AssistantMessage)
    assert restored[0].content == "hello"
    assert len(restored[1].content) == 2


# ── Utilities ──

def test_get_text_content_user():
    msg = create_user_message("hello world")
    assert get_text_content(msg) == "hello world"


def test_get_text_content_assistant():
    msg = create_assistant_message([TextBlock(text="a"), TextBlock(text="b")])
    assert "a" in get_text_content(msg)
    assert "b" in get_text_content(msg)


def test_get_tool_use_blocks():
    msg = create_assistant_message([
        TextBlock(text="hi"),
        ToolUseBlock(id="t1", name="Bash", input={}),
    ])
    blocks = get_tool_use_blocks(msg)
    assert len(blocks) == 1
    assert blocks[0].name == "Bash"


def test_has_tool_use():
    msg1 = create_assistant_message([TextBlock(text="hi")])
    msg2 = create_assistant_message([ToolUseBlock(id="t1", name="X", input={})])
    assert not has_tool_use(msg1)
    assert has_tool_use(msg2)


def test_count_content_blocks():
    msg = create_assistant_message([TextBlock(text="a"), TextBlock(text="b")])
    assert count_content_blocks(msg) == 2
