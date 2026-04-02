<p align="center">
  <h1 align="center">nanocc</h1>
  <p align="center">
    <b>Python Nano Claude Code</b> — a minimal reimplementation of <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a> in ~10,000 lines of Python.
  </p>
  <p align="center">
    CLI for daily use &nbsp;|&nbsp; Agent SDK for building AI agents &nbsp;|&nbsp; IM channel integration
  </p>
  <p align="center">
    <a href="https://github.com/ZJUFangzh/nanocc/stargazers"><img src="https://img.shields.io/github/stars/ZJUFangzh/nanocc?style=social" alt="GitHub Stars"></a>
    &nbsp;
    <a href="https://github.com/ZJUFangzh/nanocc/blob/main/LICENSE"><img src="https://img.shields.io/github/license/ZJUFangzh/nanocc" alt="License"></a>
    &nbsp;
    <img src="https://img.shields.io/badge/python-%3E%3D3.11-blue" alt="Python">
    &nbsp;
    <img src="https://img.shields.io/badge/tests-153%20passed-brightgreen" alt="Tests">
    &nbsp;
    <img src="https://img.shields.io/badge/lines-~7.6k%2F10k-orange" alt="Lines">
  </p>
  <p align="center">
    <a href="README_CN.md">中文文档</a>
  </p>
</p>

<p align="center">
  <img src="images/image1.png" alt="nanocc REPL demo" width="720">
</p>

---

## News

- **2026-04-03** — Phase 7 complete + integration fixes: 9 cross-module link-ups, 153 tests all passing. Hooks, Assistant/KAIROS mode, sub-agents, MCP all wired end-to-end.
- **2026-04-03** — Provider config overhaul: `settings.json` persistent config, `/model` hot-switch in REPL, AgentTool fixes.
- **2026-04-02** — Initial release: Phase 1-7 implemented in a single day. Core agent loop, 12 tools, 3-layer compaction, memory system, hooks, skills, MCP, sub-agents, and assistant mode.

---

## Features

- **Agent Loop** — async generator state machine faithfully replicating Claude Code's `query()` pattern
- **12 Built-in Tools** — Bash, Read, Write, Edit, Glob, Grep, Agent, AskUser, WebFetch, Skill, Brief, Sleep
- **Multi-Provider** — OpenRouter (default), Anthropic, OpenAI, Together, Groq, or any OpenAI-compatible API
- **3-Layer Context Compaction** — budget truncation → micro cleanup → LLM-summarized auto compact
- **Memory System** — persistent memories (4 types), session memory (10 fixed sections), auto-dream consolidation
- **Hook System** — 5 event types × 3 hook types, auto-triggered around tool execution
- **Skills** — file-based plugins with fork isolation support
- **MCP Integration** — stdio / HTTP / SSE transports, tools + resources
- **Sub-Agents** — fork with isolated context + coordinator for parallel/serial task orchestration
- **Assistant / KAIROS Mode** — long-running daemon with proactive ticks and structured Brief output

## Quick Start

### Install

```bash
# Requires Python >=3.11 and uv
uv sync
```

### Configure

Create `~/.nanocc/settings.json`:

```json
{
  "provider": "openrouter",
  "model": "qwen/qwen3.5-flash-02-23",
  "apiKey": "sk-or-v1-..."
}
```

### Run

```bash
# Single-turn
uv run nanocc -p "explain this codebase"

# Interactive REPL
uv run nanocc

# Override model via CLI flags
uv run nanocc -m anthropic/claude-sonnet-4 --api-key $KEY

# Switch model in REPL
> /model qwen/qwen3.5-flash-02-23
```

### Install globally (optional)

```bash
uv tool install -e .    # installs to ~/.local/bin/nanocc
# then use `nanocc` from anywhere
```

## Providers

| Provider | Env Variable | Model Format | Notes |
|---|---|---|---|
| `openrouter` (default) | `OPENROUTER_API_KEY` | `provider/model` | Widest model coverage |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | Native SDK |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` | |
| `together` | `TOGETHER_API_KEY` | `meta-llama/...` | |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | |
| `custom` | — | any | Set `apiBaseUrl` in settings |

Config priority: `/model` session override > CLI flags > env variables > `settings.json` > built-in defaults.

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Entry Points                           │
│   CLI (click+rich)  │  Channel (IM)  │  SDK (programmatic) │
└─────────┬───────────┴───────┬────────┴──────┬───────────┘
          │                   │               │
          ▼                   ▼               ▼
┌─────────────────────────────────────────────────────────┐
│              QueryEngine (engine.py)                     │
│  Stateful session container: messages, usage, abort,     │
│  memory extraction, session persistence (--continue)     │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              query() (query.py)                          │
│  Async generator state machine — the core agent loop     │
│                                                          │
│  ┌─ each iteration ──────────────────────────────────┐  │
│  │ 1. Context pipeline: budget → micro → auto compact │  │
│  │ 2. LLM stream: provider.stream() → ProviderEvents  │  │
│  │ 3. Abort check + synthetic tool_result backfill     │  │
│  │ 4. Tool execution (parallel read / serial write)    │  │
│  │    ├─ hook: tool_start                              │  │
│  │    ├─ run tool                                      │  │
│  │    └─ hook: tool_complete                           │  │
│  │ 5. End turn → hook: stop → Terminal                 │  │
│  └────────────────────────────────────────────────────┘  │
└────────┬──────────────────┬─────────────────────────────┘
         │                  │
         ▼                  ▼
┌────────────────┐  ┌────────────────────────────────────┐
│  LLM Providers │  │  Tool Orchestration                 │
│                │  │                                     │
│  ProviderEvent │  │  partition_tool_calls():             │
│  normalization │  │    read_only=True  → parallel (≤10) │
│                │  │    read_only=False → serial          │
│  • anthropic   │  │                                     │
│  • openai_compat│  │  12 built-in tools + MCP tools     │
│  • custom      │  │                                     │
└────────────────┘  └────────────────────────────────────┘
```

### Core Agent Loop (`query.py`)

The heart of nanocc — a faithful reimplementation of Claude Code's async generator state machine. **Not** a ReAct loop.

```python
async def query(params: QueryParams) -> AsyncGenerator[StreamEvent | Message, Terminal]:
    state = LoopState(messages, tool_use_context, turn_count=0, ...)
    while True:
        # 1. Context governance pipeline
        apply_tool_result_budget(state.messages)     # truncate >30K results
        micro_compact(state.messages)                 # clear old tool_results
        await auto_compact_if_needed(state.messages)  # LLM-summarize if over threshold

        # 2. Stream LLM response
        async for event in provider.stream(messages, system_prompt, tools):
            yield event  # text_delta, tool_use, usage, ...

        # 3. Tool execution with hooks
        if tool_use_blocks:
            await hook_engine.fire("tool_start", block)
            result = await run_tool(block, context)
            await hook_engine.fire("tool_complete", block, result)
            continue  # next loop iteration

        # 4. No tools → end turn
        await hook_engine.fire("stop", messages)
        return Terminal(reason="completed")
```

Terminal reasons: `completed`, `aborted_streaming`, `aborted_tools`, `prompt_too_long`, `max_turns`, `model_error`

### LLM Provider Abstraction

All providers implement the same protocol — the agent loop only sees normalized `ProviderEvent`s, never SDK-specific types:

```python
class LLMProvider(Protocol):
    async def stream(messages, system_prompt, tools, *, model, ...) -> AsyncGenerator[ProviderEvent]
    def count_tokens(messages, model) -> int
    def get_context_window(model) -> int
```

Adding a new provider = implement 3 methods (~300 lines).

### Tool System

```python
class Tool(Protocol):
    name: str
    input_schema: dict       # JSON Schema
    is_read_only: bool       # True → can run in parallel

    def check_permissions(input, context) -> allow | deny | ask
    async def execute(input, context) -> ToolResult
```

Concurrency model (replicating Claude Code):
- `is_read_only=True` tools run **in parallel** (up to 10 concurrent)
- Write tools run **serially**, one at a time

### 3-Layer Context Compaction

Claude Code uses 7 layers — nanocc distills them into 3 with the same effect:

```
Layer 1: tool_result_budget    ─── single result >30K chars → truncate + disk spill
                ↓
Layer 2: micro_compact         ─── old tool_results → [cleared], keep recent 5
                ↓
Layer 3: auto_compact          ─── over threshold → LLM summarizes entire conversation
                ↓
        post_compact           ─── re-inject last 5 files + active plan + loaded skills
```

Key thresholds (matching Claude Code): autocompact buffer 13K tokens, summary reserve 20K tokens, post-compact file recovery max 5 files / 50K tokens, circuit breaker after 3 consecutive failures.

### Memory System

```
┌─────────────────────────────────────────────────────────┐
│ Long-term Memory (memdir.py)                            │
│ MEMORY.md index (≤200 lines) + individual topic files    │
│ 4 types: user | feedback | project | reference           │
│ Retrieval: scan frontmatter → LLM ranks top 5 → inject  │
├─────────────────────────────────────────────────────────┤
│ Session Memory (session_memory.py)                       │
│ Structured working notes — 10 fixed sections:            │
│ Current State, Task, Files Modified, Errors, Worklog,    │
│ Open Questions, Dependencies, Decisions Made, ...        │
│ Trigger: 10K tokens init, 5K incremental, 3+ tool calls │
├─────────────────────────────────────────────────────────┤
│ Memory Extract (extract.py)                              │
│ Background fire-and-forget after each turn:              │
│ fork sub-agent → analyze conversation → write memories   │
├─────────────────────────────────────────────────────────┤
│ Auto Dream (auto_dream.py)                               │
│ Offline consolidation (24h + 5 sessions gate):           │
│ Phase 1: Orient — read existing memory structure          │
│ Phase 2: Scan — find signals in session transcripts       │
│ Phase 3: Consolidate — LLM merges, dedupes, date-fixes   │
└─────────────────────────────────────────────────────────┘
```

### Hook System

Declarative hooks auto-trigger at tool execution boundaries — infrastructure-level guarantees, not "suggestions to the AI":

| Event | Fires When | Example Use |
|---|---|---|
| `tool_start` | Before tool execution | Validate inputs, audit logging |
| `tool_complete` | After tool execution | Auto-lint, test runner |
| `tool_error` | Tool raises error | Error reporting |
| `stop` | Agent finishes turn | Security review, notifications |
| `subagent_stop` | Sub-agent completes | Result aggregation |

3 hook types: `command` (shell), `prompt` (LLM), `http` (webhook). Supports `if` condition matching, `once` auto-removal, and session-scoped registration.

### Sub-Agents

- **Fork** (`agents/fork.py`) — creates an isolated agent with its own message history but shared provider. Used for parallel research, skill fork mode, and memory extraction.
- **Coordinator** (`agents/coordinator.py`) — dispatches tasks to multiple fork agents. Parallel mode for read-only tasks, serial mode for sequential writes.
- **AgentTool** — exposed as a tool so the LLM can spawn sub-agents on demand.

### MCP Integration

Lightweight MCP client supporting 3 transports:

| Transport | Use Case |
|---|---|
| `stdio` | Local process (e.g., filesystem, database tools) |
| `http` | Remote HTTP server |
| `sse` | Server-Sent Events stream |

MCP tools are wrapped as native `Tool` objects (`mcp__{server}__{tool}`) and participate in the same orchestration pipeline. Resources are accessible via `list_resources` / `read_resource`.

### Harness Engineering

nanocc follows a **"harness engineering"** philosophy: instead of relying on prompt engineering alone, the system **designs the environment** around the AI agent to make correct behavior a structural property.

> **Prompt engineering** is like onboarding training — no matter how good it is, the employee forgets.
> **Harness engineering** is like designing the office and workflow — the coding standards are posted at the desk (CLAUDE.md injection), every commit auto-runs CI (hooks), past mistakes are on the wiki for everyone (feedback memory), and weekly reviews clean up stale decisions (auto dream).

| Module | Harness Mechanism | Problem Solved |
|---|---|---|
| `memory/claude_md.py` | Hierarchical CLAUDE.md injection | Style drift |
| `memory/memdir.py` | 4 memory types + exclusion rules | Cognitive pollution |
| `memory/session_memory.py` | Fixed 10-section template | State loss across compacts |
| `memory/extract.py` | Auto feedback extraction | Repeating past mistakes |
| `memory/auto_dream.py` | Gated consolidation + dedup | Memory decay over time |
| `compact/post_compact.py` | Precise file re-injection | Context continuity after compact |
| `hooks/engine.py` | Auto-trigger around tools | Quality drift |
| `context.py` | 3-segment system prompt + cache | Instruction amnesia |

## Project Structure

```
src/nanocc/
├── types.py              # Core types (Message, ContentBlock, QueryParams, LoopState)
├── constants.py          # Token thresholds (matching Claude Code)
├── messages.py           # Message creation / API format conversion
├── query.py              # Agent loop async generator state machine
├── context.py            # 3-segment system prompt assembly + cache_control
├── engine.py             # Stateful session container (get_state/restore_state)
├── providers/            # LLM backends (anthropic / openai_compat)
├── tools/                # 12 tools + orchestration with hook integration
├── compact/              # Context management (budget → micro → auto compact)
├── memory/               # Memory system (memdir, session, auto_dream, daily_log)
├── hooks/                # Hook system (5 events × 3 types)
├── skills/               # Skill loading & execution (with fork mode)
├── mcp/                  # MCP server integration (stdio/http/sse + resources)
├── agents/               # Sub-agents (fork + coordinator)
├── assistant/            # Assistant/KAIROS mode (proactive tick, Brief/Sleep)
├── cli/                  # CLI entry (click + rich)
└── utils/                # Utilities (abort, tokens, git, config, cost)

tests/                    # 153 tests, mock provider, no API key needed
```

## Development

```bash
# Run tests (no API key required)
uv run pytest tests/ -v

# Run single test module
uv run pytest tests/test_query.py -v

# Verify import
uv run python -c "import nanocc"
```

## Current Status

| Metric | Value |
|---|---|
| Source lines | ~7,600 |
| Target | ~10,000 |
| Phases completed | 7 / 10 + integration fixes |
| Built-in tools | 12 |
| Providers | 5 + custom |
| Compact layers | 3 |
| Memory modules | 6 |
| MCP transports | 3 |
| Tests | 153 |

See [docs/progress.md](docs/progress.md) for detailed phase-by-phase progress.

## Roadmap

| Phase | Content | Est. Lines |
|---|---|---|
| 8 | CLI terminal UI polish | ~1,000 |
| 9 | Channel / IM integration (Telegram, etc.) | ~700 |
| 10 | SDK public API + OpenAI provider + packaging | ~600 |

## Tech Stack

- **Python >=3.11**, managed with [uv](https://github.com/astral-sh/uv)
- **Build**: hatchling
- **CLI**: click + rich
- **LLM**: anthropic SDK (native) + openai SDK (compatibility layer)
- **Types**: dataclass (no Pydantic)

## Star History

<a href="https://star-history.com/#ZJUFangzh/nanocc&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ZJUFangzh/nanocc&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ZJUFangzh/nanocc&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ZJUFangzh/nanocc&type=Date" />
 </picture>
</a>

## License

MIT
