"""CLI entry point — Rich REPL + one-shot mode with tool support."""

from __future__ import annotations

import asyncio
import os
import sys

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.status import Status

from nanocc.constants import DEFAULT_MODEL
from nanocc.context import build_system_prompt, system_prompt_to_text
from nanocc.messages import create_user_message, get_text_content
from nanocc.memory.claude_md import load_claude_md
from nanocc.providers.registry import create_provider
from nanocc.query import query
from nanocc.tools.registry import get_all_tools
from nanocc.types import (
    AssistantMessage,
    QueryParams,
    StreamEvent,
    StreamEventType,
    Terminal,
    TerminalReason,
    ToolResultBlock,
    ToolUseBlock,
    ToolUseContext,
)
from nanocc.utils.abort import AbortController

from .commands import SLASH_NAMES, handle_command

console = Console()


# ── Streaming loop ─────────────────────────────────────────────────────────


def _render_tool_result(block: ToolResultBlock) -> None:
    """Render a tool result block to the console."""
    content = block.content if isinstance(block.content, str) else str(block.content)
    if block.is_error:
        console.print(f"  [red]Error:[/red] {content[:200]}")
    else:
        preview = content[:300]
        if len(content) > 300:
            preview += "..."
        console.print(f"  [dim]{preview}[/dim]")


async def _stream_loop(
    params: QueryParams,
    *,
    all_messages: list | None = None,
) -> tuple[int, int]:
    """Run the agent loop, streaming text and handling tool calls.

    Returns (input_tokens, output_tokens) accumulated during the loop.
    """
    collected_text = ""
    live: Live | None = None
    spinner: Status | None = None
    total_in = 0
    total_out = 0

    def _stop_live() -> None:
        nonlocal live
        if live is not None:
            live.stop()
            live = None

    def _stop_spinner() -> None:
        nonlocal spinner
        if spinner is not None:
            spinner.stop()
            spinner = None

    def _start_spinner(msg: str) -> None:
        nonlocal spinner
        _stop_spinner()
        spinner = Status(msg, console=console, spinner="dots")
        spinner.start()

    def _start_live() -> None:
        nonlocal live
        _stop_spinner()
        if live is None:
            live = Live(console=console, refresh_per_second=15)
            live.start()

    # Show spinner while waiting for first token
    _start_spinner("[cyan]Thinking…[/cyan]")

    try:
        async for event in query(params):
            if isinstance(event, Terminal):
                _stop_live()
                _stop_spinner()
                if event.reason == TerminalReason.MODEL_ERROR:
                    console.print(f"\n[red]Error: {event.error}[/red]")
                break

            if isinstance(event, StreamEvent):
                if (
                    event.type == StreamEventType.CONTENT_BLOCK_DELTA
                    and event.delta
                    and "text" in event.delta
                ):
                    # First text token — switch from spinner to live markdown
                    if live is None:
                        _stop_spinner()
                        _start_live()
                    collected_text += event.delta["text"]
                    if live is not None:
                        live.update(Markdown(collected_text))

                # Track usage
                if event.usage:
                    total_in += event.usage.input_tokens or 0
                    total_out += event.usage.output_tokens or 0

            elif isinstance(event, AssistantMessage):
                # Flush live rendering for this text segment
                final_text = get_text_content(event)
                if final_text:
                    collected_text = final_text
                    if live is not None:
                        live.update(Markdown(collected_text))

                _stop_live()

                # Track usage
                if event.usage:
                    total_in += event.usage.input_tokens or 0
                    total_out += event.usage.output_tokens or 0

                # Check if model called tools — print BEFORE execution starts
                tool_uses = [b for b in event.content if isinstance(b, ToolUseBlock)]
                if tool_uses:
                    for tu in tool_uses:
                        console.print(
                            f"[bold yellow]Tool:[/bold yellow] {tu.name}({_summarize_input(tu.input)})"
                        )
                    # Force flush so tool info is visible before execution
                    console.file.flush()
                    # Spinner while tools execute
                    _start_spinner("[yellow]Running tools…[/yellow]")
                    collected_text = ""

                # Track in conversation history
                if all_messages is not None:
                    all_messages.append(event)

            elif isinstance(event, ToolResultBlock):
                _render_tool_result(event)

                # After last tool result, spinner while waiting for next LLM turn
                _stop_spinner()
                _start_spinner("[cyan]Thinking…[/cyan]")
                collected_text = ""
    finally:
        _stop_live()
        _stop_spinner()

    return total_in, total_out


def _summarize_input(input: dict) -> str:
    """Short summary of tool input for display."""
    if "command" in input:
        cmd = input["command"]
        return cmd[:60] + "..." if len(cmd) > 60 else cmd
    if "file_path" in input:
        return input["file_path"]
    if "pattern" in input:
        return input["pattern"]
    return ", ".join(f"{k}=..." for k in list(input)[:3])


# ── One-shot mode ──────────────────────────────────────────────────────────


async def run_query(
    prompt: str,
    model: str,
    system_prompt: str = "",
    provider_name: str = "openrouter",
    api_key: str | None = None,
) -> None:
    """Run a single query and stream the response to the terminal."""
    provider = create_provider(provider_name, api_key=api_key)
    abort = AbortController()
    tools = get_all_tools()
    cwd = os.getcwd()

    messages = [create_user_message(prompt)]

    # Build three-segment system prompt with environment context
    user_context: dict[str, str] = {"Project Instructions": load_claude_md(cwd) or ""}
    system_blocks = build_system_prompt(
        base_prompt=system_prompt or "",
        user_context=user_context if any(user_context.values()) else None,
        cwd=cwd,
    )
    # OpenAI-compat providers need plain text
    system_text = system_prompt_to_text(system_blocks)

    tool_context = ToolUseContext(cwd=cwd, tools=tools, abort_controller=abort, model=model)

    params = QueryParams(
        messages=messages,
        system_prompt=system_text,
        provider=provider,
        model=model,
        tools=tools,
        abort_controller=abort,
        tool_use_context=tool_context,
    )

    await _stream_loop(params)


# ── REPL mode ──────────────────────────────────────────────────────────────


async def repl(
    model: str,
    system_prompt: str = "",
    provider_name: str = "openrouter",
    api_key: str | None = None,
) -> None:
    """Interactive REPL loop with prompt_toolkit input + Rich output."""
    provider = create_provider(provider_name, api_key=api_key)
    tools = get_all_tools()
    cwd = os.getcwd()
    all_messages: list = []
    total_tokens = 0
    total_cost = 0.0

    # Build three-segment system prompt with CLAUDE.md loaded
    user_context: dict[str, str] = {"Project Instructions": load_claude_md(cwd) or ""}
    system_blocks = build_system_prompt(
        base_prompt=system_prompt or "",
        user_context=user_context if any(user_context.values()) else None,
        cwd=cwd,
    )
    system_prompt = system_prompt_to_text(system_blocks)

    # Welcome banner
    console.print(
        f"[bold cyan]nanocc[/bold cyan] [dim]({model})[/dim]",
        highlight=False,
    )
    tool_names = ", ".join(t.name for t in tools)
    console.print(f"[dim]Tools: {tool_names}[/dim]")
    console.print("[dim]Type /help for commands, /exit to quit.[/dim]\n")

    # prompt_toolkit session with history + completion
    history_path = os.path.expanduser("~/.nanocc_history")
    session: PromptSession[str] = PromptSession(
        history=FileHistory(history_path),
        completer=WordCompleter(SLASH_NAMES, sentence=True),
    )

    while True:
        try:
            user_input = (await session.prompt_async("❯ ")).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            result = handle_command(
                user_input,
                console=console,
                all_messages=all_messages,
                model=model,
                total_tokens=total_tokens,
                total_cost=total_cost,
            )
            if result == "exit":
                break
            continue

        all_messages.append(create_user_message(user_input))
        abort = AbortController()

        tool_context = ToolUseContext(
            cwd=cwd, tools=tools, abort_controller=abort, model=model
        )

        params = QueryParams(
            messages=all_messages,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            tools=tools,
            abort_controller=abort,
            tool_use_context=tool_context,
        )

        try:
            tok_in, tok_out = await _stream_loop(params, all_messages=all_messages)
            total_tokens += tok_in + tok_out
            console.print(f"\n[dim]{tok_in + tok_out:,} tokens[/dim]\n")
        except KeyboardInterrupt:
            abort.abort()
            console.print("\n[dim]Interrupted.[/dim]")


# ── CLI entry point ────────────────────────────────────────────────────────


@click.command()
@click.option("-p", "--prompt", default=None, help="One-shot prompt (non-interactive).")
@click.option("-m", "--model", default=DEFAULT_MODEL, help="Model name.", show_default=True)
@click.option("--system", default="", help="System prompt override.")
@click.option(
    "--provider",
    default="openrouter",
    help="LLM provider (openrouter/anthropic/openai/together/groq).",
    show_default=True,
)
@click.option(
    "--api-key", default=None, help="API key (default: $OPENROUTER_API_KEY or $ANTHROPIC_API_KEY)."
)
def main(
    prompt: str | None,
    model: str,
    system: str,
    provider: str,
    api_key: str | None,
) -> None:
    """nanocc — Python Nano Claude Code."""
    env_keys = {
        "openrouter": "OPENROUTER_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "together": "TOGETHER_API_KEY",
        "groq": "GROQ_API_KEY",
    }

    if not api_key:
        env_var = env_keys.get(provider, "OPENAI_API_KEY")
        api_key = os.environ.get(env_var)

    if not api_key:
        console.print(
            f"[red]Error: Set {env_keys.get(provider, 'OPENAI_API_KEY')} or pass --api-key.[/red]"
        )
        sys.exit(1)

    if prompt:
        asyncio.run(run_query(prompt, model, system, provider, api_key))
    else:
        asyncio.run(repl(model, system, provider, api_key))


if __name__ == "__main__":
    main()
