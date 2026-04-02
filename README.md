<p align="center">
  <h1 align="center">nanocc</h1>
  <p align="center">
    <b>Python Nano Claude Code</b> — a minimal reimplementation of <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a> in ~10,000 lines of Python.
  </p>
  <p align="center">
    CLI for daily use &nbsp;|&nbsp; Agent SDK for building AI agents &nbsp;|&nbsp; IM channel integration
  </p>
  <p align="center">
    <a href="https://github.com/fangzehua/nanocc/stargazers"><img src="https://img.shields.io/github/stars/fangzehua/nanocc?style=social" alt="GitHub Stars"></a>
    &nbsp;
    <a href="https://github.com/fangzehua/nanocc/blob/main/LICENSE"><img src="https://img.shields.io/github/license/fangzehua/nanocc" alt="License"></a>
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

```
CLI / Channel / SDK
       ↓
  QueryEngine (engine.py)      ← stateful session container
       ↓
  query() (query.py)           ← async generator state machine (core loop)
       ↓
  LLMProvider.stream()         ← normalized ProviderEvent
       ↓
  Tool Orchestration            ← read-tools parallel / write-tools serial
```

### Harness Engineering

nanocc follows a **"harness engineering"** philosophy: instead of relying on prompt engineering alone, the system **designs the environment** around the AI agent to make correct behavior a structural property.

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

## License

MIT
