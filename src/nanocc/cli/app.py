"""CLI entry point — Rich REPL + one-shot mode via QueryEngine."""

from __future__ import annotations

import asyncio
import os
import sys
import time

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.status import Status

from nanocc.engine import QueryEngine, QueryEngineConfig
from nanocc.messages import get_text_content
from nanocc.providers.registry import create_provider
from nanocc.utils.config import resolve_provider_config
from nanocc.types import (
    AssistantMessage,
    StreamEvent,
    StreamEventType,
    Terminal,
    TerminalReason,
    ToolResultBlock,
    ToolUseBlock,
)

from .commands import SLASH_NAMES, handle_command

console = Console()


# ── Streaming UI renderer ─────────────────────────────────────────────────


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


async def _stream_response(
    engine: QueryEngine,
    prompt: str,
) -> tuple[int, int, float]:
    """Stream a single engine response to the terminal.

    Returns (input_tokens, output_tokens, elapsed_seconds).
    """
    start_time = time.monotonic()
    collected_text = ""
    live: Live | None = None
    spinner: Status | None = None
    spinner_task: asyncio.Task[None] | None = None
    spinner_label: str = ""
    total_in = 0
    total_out = 0

    def _stop_live() -> None:
        nonlocal live
        if live is not None:
            live.stop()
            live = None

    def _stop_spinner() -> None:
        nonlocal spinner, spinner_task
        if spinner_task is not None:
            spinner_task.cancel()
            spinner_task = None
        if spinner is not None:
            spinner.stop()
            spinner = None

    async def _tick_spinner() -> None:
        """Background task that updates spinner text with elapsed time every second."""
        try:
            while spinner is not None:
                elapsed = time.monotonic() - start_time
                spinner.update(f"{spinner_label} [dim]{_format_duration(elapsed)}[/dim]")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    def _start_spinner(msg: str) -> None:
        nonlocal spinner, spinner_task, spinner_label
        _stop_spinner()
        spinner_label = msg
        elapsed = time.monotonic() - start_time
        spinner = Status(f"{msg} [dim]{_format_duration(elapsed)}[/dim]", console=console, spinner="dots")
        spinner.start()
        spinner_task = asyncio.create_task(_tick_spinner())

    def _start_live() -> None:
        nonlocal live
        _stop_spinner()
        if live is None:
            live = Live(console=console, refresh_per_second=15)
            live.start()

    # Show spinner while waiting for first token
    _start_spinner("[cyan]Thinking…[/cyan]")

    try:
        async for event in engine.submit_message(prompt):
            if isinstance(event, Terminal):
                _stop_live()
                _stop_spinner()
                if event.reason == TerminalReason.MODEL_ERROR:
                    console.print(f"\n[red]Error: {event.error}[/red]")
                break

            if isinstance(event, StreamEvent):
                # Detect tool_use block start — show spinner during generation
                if (
                    event.type == StreamEventType.CONTENT_BLOCK_START
                    and event.block_type == "tool_use"
                ):
                    if live is not None and collected_text:
                        live.update(Markdown(collected_text))
                    _stop_live()
                    tool_label = event.tool_name or "tool"
                    _start_spinner(f"[yellow]Preparing {tool_label}…[/yellow]")

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
                    collected_text = ""

            elif isinstance(event, ToolResultBlock):
                _render_tool_result(event)

                # After tool result, show thinking spinner for next LLM turn
                _start_spinner("[cyan]Thinking…[/cyan]")
                collected_text = ""
    finally:
        _stop_live()
        _stop_spinner()

    elapsed = time.monotonic() - start_time
    return total_in, total_out, elapsed


def _format_duration(seconds: float) -> str:
    """Format elapsed seconds into a human-readable duration string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m {secs:.0f}s"


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


def _create_engine(
    model: str,
    system_prompt: str,
    provider_name: str,
    api_key: str | None,
    base_url: str | None = None,
) -> QueryEngine:
    """Create a QueryEngine from resolved config."""
    kwargs: dict[str, str] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    provider = create_provider(provider_name, **kwargs)
    cwd = os.getcwd()

    return QueryEngine(QueryEngineConfig(
        provider=provider,
        model=model,
        cwd=cwd,
        system_prompt=system_prompt,
    ))


async def run_query(
    model: str,
    system_prompt: str,
    provider_name: str,
    api_key: str | None,
    prompt: str,
    base_url: str | None = None,
) -> None:
    """Run a single query via QueryEngine and stream to terminal."""
    engine = _create_engine(model, system_prompt, provider_name, api_key, base_url)
    _, tok_out, elapsed = await _stream_response(engine, prompt)
    console.print(f"\n[dim]{tok_out:,} tokens | {_format_duration(elapsed)}[/dim]")


# ── REPL mode ──────────────────────────────────────────────────────────────


async def repl(
    model: str,
    system_prompt: str,
    provider_name: str,
    api_key: str | None,
    base_url: str | None = None,
) -> None:
    """Interactive REPL loop via QueryEngine."""
    engine = _create_engine(model, system_prompt, provider_name, api_key, base_url)

    # Welcome banner
    console.print(
        f"[bold cyan]nanocc[/bold cyan] [dim]({model})[/dim]",
        highlight=False,
    )
    tool_names = ", ".join(t.name for t in engine.tools)
    console.print(f"[dim]Tools: {tool_names}[/dim]")
    console.print("[dim]Type /help for commands, /exit to quit.[/dim]\n")

    # prompt_toolkit session with history + completion
    history_path = os.path.expanduser("~/.nanocc_history")
    session: PromptSession[str] = PromptSession(
        history=FileHistory(history_path),
        completer=WordCompleter(SLASH_NAMES, sentence=True),
    )

    total_tokens = 0

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
                engine=engine,
                total_tokens=total_tokens,
                total_cost=0.0,
            )
            if result == "exit":
                break
            continue

        try:
            tok_in, tok_out, elapsed = await _stream_response(engine, user_input)
            total_tokens += tok_in + tok_out
            console.print(f"\n[dim]{tok_out:,} tokens | {_format_duration(elapsed)}[/dim]\n")
        except KeyboardInterrupt:
            engine.abort()
            console.print("\n[dim]Interrupted.[/dim]")


# ── CLI entry point ────────────────────────────────────────────────────────


@click.command()
@click.option("-p", "--prompt", default=None, help="One-shot prompt (non-interactive).")
@click.option("-m", "--model", default=None, help="Model name (default: from settings or anthropic/claude-sonnet-4-20250514).")
@click.option("--system", default="", help="System prompt override.")
@click.option(
    "--provider",
    default=None,
    help="LLM provider (openrouter/anthropic/openai/together/groq/custom).",
)
@click.option(
    "--api-key", default=None, help="API key (default: env var or settings.json)."
)
@click.option(
    "--base-url", default=None, help="API base URL for custom OpenAI-compatible providers."
)
def main(
    prompt: str | None,
    model: str | None,
    system: str,
    provider: str | None,
    api_key: str | None,
    base_url: str | None,
) -> None:
    """nanocc — Python Nano Claude Code."""
    cwd = os.getcwd()
    cfg = resolve_provider_config(
        cli_model=model,
        cli_provider=provider,
        cli_api_key=api_key,
        cli_base_url=base_url,
        cwd=cwd,
    )

    if not cfg.api_key:
        console.print(
            "[red]Error: No API key found. Set it via --api-key, env var, or ~/.nanocc/settings.json.[/red]"
        )
        sys.exit(1)

    if prompt:
        asyncio.run(run_query(cfg.model, system, cfg.provider, cfg.api_key, prompt, cfg.api_base_url))
    else:
        asyncio.run(repl(cfg.model, system, cfg.provider, cfg.api_key, cfg.api_base_url))


if __name__ == "__main__":
    main()
