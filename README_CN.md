<p align="center">
  <h1 align="center">nanocc</h1>
  <p align="center">
    <b>Python Nano Claude Code</b> — 基于 <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a> 2.1.88 的 Python 精简复刻（~10,000 行）
  </p>
  <p align="center">
    CLI 日常使用 &nbsp;|&nbsp; Agent SDK 构建代理 &nbsp;|&nbsp; IM 通道对接
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
    <a href="README.md">English</a>
  </p>
</p>

<p align="center">
  <img src="images/image1.png" alt="nanocc REPL 演示" width="720">
</p>

---

## News

- **2026-04-03** — Phase 7 全部完成 + 链路修复：9 项跨模块集成修复，153 个测试全部通过。Hooks、Assistant/KAIROS 模式、子 Agent、MCP 全链路打通。
- **2026-04-03** — Provider 配置重构：`settings.json` 持久化配置、REPL 内 `/model` 热切换、AgentTool 修复。
- **2026-04-02** — 首次发布：一天内完成 Phase 1-7。核心 agent loop、12 个工具、三层压缩、记忆系统、hooks、skills、MCP、子 agent、assistant 模式全部就位。

---

## 特性

- **Agent Loop** — 异步 generator 状态机，忠实复刻 Claude Code 的 `query()` 模式
- **12 个内置工具** — Bash、Read、Write、Edit、Glob、Grep、Agent、AskUser、WebFetch、Skill、Brief、Sleep
- **多 Provider 支持** — OpenRouter（默认）、Anthropic、OpenAI、Together、Groq，或任意 OpenAI 兼容 API
- **三层上下文压缩** — 预算截断 → 微压缩 → LLM 摘要自动压缩
- **记忆系统** — 持久记忆（4 种类型）、会话记忆（10 个固定 section）、auto-dream 自动归纳
- **Hook 系统** — 5 种事件 × 3 种 hook 类型，工具执行前后自动触发
- **Skill 插件** — 文件即插件，支持 fork 隔离执行
- **MCP 集成** — stdio / HTTP / SSE 三种传输协议，工具 + 资源
- **子 Agent** — fork 隔离上下文 + coordinator 并行/串行任务协调
- **Assistant / KAIROS 模式** — 长驻守护，周期性 tick 唤醒，结构化 Brief 输出

## 快速开始

### 安装

```bash
# 需要 Python >=3.11 和 uv
uv sync
```

### 配置

创建 `~/.nanocc/settings.json`：

```json
{
  "provider": "openrouter",
  "model": "qwen/qwen3.5-flash-02-23",
  "apiKey": "sk-or-v1-..."
}
```

自定义 OpenAI 兼容 API：

```json
{
  "provider": "custom",
  "apiBaseUrl": "https://my-api.com/v1",
  "model": "my-model",
  "apiKey": "..."
}
```

### 运行

```bash
# 单轮对话
uv run nanocc -p "解释这个代码库"

# 交互式 REPL
uv run nanocc

# CLI 标志覆盖
uv run nanocc -m anthropic/claude-sonnet-4 --api-key $KEY

# REPL 中切换模型
> /model qwen/qwen3.5-flash-02-23
```

### 全局安装（可选）

```bash
uv tool install -e .    # 安装到 ~/.local/bin/nanocc
# 之后在任意目录直接运行 nanocc
```

## Provider 配置

| Provider | 环境变量 | 模型格式 | 说明 |
|---|---|---|---|
| `openrouter`（默认）| `OPENROUTER_API_KEY` | `provider/model` | 模型覆盖最广 |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` | 原生 SDK |
| `openai` | `OPENAI_API_KEY` | `gpt-4o` | |
| `together` | `TOGETHER_API_KEY` | `meta-llama/...` | |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | |
| `custom` | — | 任意 | 需配 `apiBaseUrl` |

优先级：`/model` 会话覆盖 > CLI 标志 > 环境变量 > `settings.json` > 内置默认值

## 架构

```
CLI / Channel / SDK
       ↓
  QueryEngine (engine.py)      ← 有状态会话容器
       ↓
  query() (query.py)           ← 异步 generator 状态机（核心循环）
       ↓
  LLMProvider.stream()         ← 归一化 ProviderEvent
       ↓
  Tool Orchestration            ← 读工具并行 / 写工具串行
```

### Harness Engineering 设计理念

nanocc 遵循「**Harness Engineering**」理念：不依赖 prompt engineering 控制 AI 怎么想，而是**设计 AI 工作的环境和反馈机制**，让正确行为成为系统属性。

| 模块 | Harness 机制 | 解决的问题 |
|---|---|---|
| `memory/claude_md.py` | CLAUDE.md 层级注入 | 风格漂移 |
| `memory/memdir.py` | 4 类 memory + 排除规则 | 认知污染 |
| `memory/session_memory.py` | 固定 10-section 模板 | compact 后状态丢失 |
| `memory/extract.py` | 自动 feedback 抽取 | 同样错误反复犯 |
| `memory/auto_dream.py` | 门控蒸馏 + 去重 | 记忆随时间腐烂 |
| `compact/post_compact.py` | 精确文件重注入 | compact 后上下文断裂 |
| `hooks/engine.py` | 工具执行自动触发 | 质量漂移 |
| `context.py` | 三段式 system prompt + 缓存 | 指令遗忘 |

## 目录结构

```
src/nanocc/
├── types.py              # 核心类型（Message, ContentBlock, QueryParams, LoopState）
├── constants.py          # 常量阈值（与 Claude Code 一致）
├── messages.py           # 消息创建 / API 格式转换
├── query.py              # agent loop 异步 generator 状态机
├── context.py            # 三段式 system prompt 装配 + cache_control
├── engine.py             # 有状态会话容器（get_state/restore_state）
├── providers/            # LLM 后端（anthropic / openai_compat）
├── tools/                # 12 个工具 + 编排（含 hook 集成）
├── compact/              # 上下文管理（budget → micro → auto compact）
├── memory/               # 记忆系统（memdir、session、auto_dream、daily_log）
├── hooks/                # Hook 系统（5 事件 × 3 类型）
├── skills/               # Skill 加载与执行（含 fork 模式）
├── mcp/                  # MCP server 集成（stdio/http/sse + 资源）
├── agents/               # 子 Agent（fork + coordinator）
├── assistant/            # Assistant/KAIROS 模式（proactive tick、Brief/Sleep）
├── cli/                  # CLI 入口（click + rich）
└── utils/                # 工具模块（abort、tokens、git、config、cost）

tests/                    # 153 个测试，mock provider，无需 API key
```

## 开发

```bash
# 运行全量测试（无需 API key）
uv run pytest tests/ -v

# 单模块测试
uv run pytest tests/test_query.py -v

# 验证导入
uv run python -c "import nanocc"
```

## 当前状态

| 指标 | 值 |
|---|---|
| 源码行数 | ~7,600 |
| 目标行数 | ~10,000 |
| 已完成 Phase | 7 / 10 + 链路修复 |
| 内置工具 | 12 |
| Provider | 5 + custom |
| Compact 层数 | 3 |
| 记忆模块 | 6 |
| MCP 传输协议 | 3 |
| 测试用例 | 153 |

详细的阶段进度见 [docs/progress.md](docs/progress.md)，完整架构规划见 [structure.md](structure.md)。

## 路线图

| Phase | 内容 | 预估行数 |
|---|---|---|
| 8 | CLI 终端 UI 完善 | ~1,000 |
| 9 | Channel / IM 通道（Telegram 等）| ~700 |
| 10 | SDK 公开 API + OpenAI Provider + 打包 | ~600 |

## 技术栈

- **Python >=3.11**，用 [uv](https://github.com/astral-sh/uv) 管理依赖
- **构建**: hatchling
- **CLI**: click + rich
- **LLM**: anthropic SDK（原生）+ openai SDK（兼容层）
- **类型系统**: dataclass（不用 Pydantic）

## 许可证

MIT
