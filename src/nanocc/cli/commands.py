"""Slash command handling for nanocc REPL (pure functions, no framework dependency)."""

from __future__ import annotations

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

    if command == "/help":
        console.print("[bold]Commands:[/bold]")
        for c, desc in COMMANDS.items():
            console.print(f"  [cyan]{c}[/cyan] — {desc}")
        return "handled"

    console.print(f"[yellow]Unknown command: {command}[/yellow]")
    return "handled"
