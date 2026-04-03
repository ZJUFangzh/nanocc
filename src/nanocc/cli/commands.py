"""Slash command handling for nanocc REPL (pure functions, no framework dependency)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from nanocc.engine import QueryEngine

COMMANDS = {
    "/exit": "Exit nanocc",
    "/quit": "Exit nanocc",
    "/clear": "Clear conversation history",
    "/compact": "Trigger manual compact",
    "/model": "Show or switch current model",
    "/cost": "Show token usage and cost",
    "/resume": "Resume a previous session",
    "/help": "Show available commands",
}

SLASH_NAMES = list(COMMANDS.keys())


def handle_command(
    cmd: str,
    *,
    console: Console,
    engine: QueryEngine,
    total_tokens: int,
    total_cost: float,
) -> str | None:
    """Handle a slash command.

    Returns:
        "exit" — caller should break the REPL loop
        "handled" — command was processed, continue loop
        "resumed" — session was restored, caller should show info
        None — not a recognized command
    """
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()

    if command in ("/exit", "/quit"):
        console.print("[dim]Goodbye.[/dim]")
        return "exit"

    if command == "/clear":
        engine.messages.clear()
        console.print("[dim]Conversation cleared.[/dim]\n")
        return "handled"

    if command == "/compact":
        console.print("[dim]Manual compact not yet implemented.[/dim]")
        return "handled"

    if command == "/model":
        arg = parts[1].strip() if len(parts) > 1 else ""
        if not arg:
            console.print(f"[dim]Model: {engine.config.model}[/dim]")
            console.print("[dim]Usage: /model <model-name> to switch[/dim]")
        else:
            engine.config.model = arg
            console.print(f"[dim]Switched to: {arg}[/dim]")
        return "handled"

    if command == "/cost":
        console.print(f"[dim]Tokens: {total_tokens:,} | Cost: ${total_cost:.4f}[/dim]")
        return "handled"

    if command == "/resume":
        return _handle_resume(console, engine)

    if command == "/help":
        console.print("[bold]Commands:[/bold]")
        for c, desc in COMMANDS.items():
            console.print(f"  [cyan]{c}[/cyan] — {desc}")
        return "handled"

    console.print(f"[yellow]Unknown command: {command}[/yellow]")
    return "handled"


def _handle_resume(console: Console, engine: QueryEngine) -> str:
    """List recent sessions and let the user pick one to resume."""
    from nanocc.utils.session_storage import (
        list_sessions,
        load_transcript_after_boundary,
        load_session_state,
    )

    sessions = list_sessions(cwd=engine.cwd)
    if not sessions:
        console.print("[dim]No previous sessions found.[/dim]")
        return "handled"

    # Show up to 10 recent sessions with last message preview
    console.print("[bold]Recent sessions:[/bold]")
    display = sessions[:10]
    for i, s in enumerate(display, 1):
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(s.get("timestamp", 0)))
        msgs = s.get("message_count", 0)
        model = s.get("model", "?")
        sid = s.get("session_id", "?")
        preview = s.get("last_message", "")
        if preview:
            preview = preview.replace("\n", " ")[:60]
            if len(s.get("last_message", "")) > 60:
                preview += "..."
        console.print(
            f"  [cyan]{i}[/cyan]. {ts} — {msgs} msgs — {model} [dim]({sid})[/dim]"
        )
        if preview:
            console.print(f"     [dim]{preview}[/dim]")

    console.print("[dim]Enter number to resume, or anything else to cancel:[/dim]")
    try:
        choice = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return "handled"

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(display):
            console.print("[dim]Cancelled.[/dim]")
            return "handled"
    except ValueError:
        console.print("[dim]Cancelled.[/dim]")
        return "handled"

    selected = display[idx]
    sid = selected["session_id"]

    # Load transcript after last compact boundary
    transcript_msgs = load_transcript_after_boundary(sid)
    if not transcript_msgs:
        console.print("[dim]Session transcript is empty.[/dim]")
        return "handled"

    saved_state = load_session_state(sid)

    state: dict[str, Any] = {
        "session_id": sid,
        "cwd": engine.cwd,
        "messages": transcript_msgs,
        "usage": saved_state.get("usage", {}) if saved_state else {},
        "session_memory": saved_state.get("session_memory", "") if saved_state else "",
    }
    engine.restore_state(state)

    # Show recent context
    print_recent_context(console, engine)
    return "resumed"


def print_recent_context(console: Console, engine: QueryEngine, max_lines: int = 6) -> None:
    """Print the last few messages so the user knows where they left off."""
    from nanocc.messages import get_text_content
    from nanocc.types import AssistantMessage, SystemMessage, UserMessage

    messages = engine.messages
    if not messages:
        return

    # Collect recent user/assistant pairs (skip system messages)
    recent: list[tuple[str, str]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        text = get_text_content(msg).replace("\n", " ").strip()
        if not text:
            continue
        if isinstance(msg, UserMessage):
            label = "You"
        elif isinstance(msg, AssistantMessage):
            label = "Assistant"
        else:
            continue
        # Truncate long messages
        if len(text) > 100:
            text = text[:100] + "..."
        recent.append((label, text))

    if not recent:
        return

    # Show last max_lines entries
    show = recent[-max_lines:]

    console.print("[dim]── Recent context ──[/dim]")
    for label, text in show:
        if label == "You":
            console.print(f"[dim][bold]You:[/bold] {text}[/dim]")
        else:
            console.print(f"[dim][bold]Assistant:[/bold] {text}[/dim]")
    console.print("[dim]────────────────────[/dim]\n")
