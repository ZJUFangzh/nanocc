# CLAUDE.md — nanocc 项目指南

## 项目概述

nanocc 是 Claude Code 2.1.88 的 Python 精简复刻，目标 ~10,000 行。
既可作为 CLI 日常使用，也可作为 Agent SDK，还支持通过 Channel 对接 IM 平台。

## 关键文件

- `structure.md` — 完整架构规划（10 个 Phase），**任何设计决策都以此为准**
- `docs/progress.md` — 开发进度和已完成的 Phase 记录
- `../claude-code-main/` — Claude Code 源码参考

## 技术栈

- **Python >=3.11**，用 `uv` 管理依赖和运行
- **构建**: hatchling（`pyproject.toml`）
- **CLI**: click + rich
- **LLM**: anthropic SDK（原生）+ openai SDK（兼容层）
- **默认 Provider**: openrouter（OpenAI 兼容 API）
- **类型系统**: dataclass（不用 Pydantic）

## 常用命令

```bash
# 运行
uv run nanocc -p "prompt"                          # 单轮
uv run nanocc                                       # REPL
uv run nanocc -m moonshotai/kimi-k2.5 --api-key $KEY  # 指定模型

# 开发
uv run python -c "import nanocc"                    # 验证导入
uv run python -m nanocc --help                      # CLI 帮助
```

## 架构核心

```
CLI / Channel / SDK
       ↓
  QueryEngine (engine.py)      ← 有状态会话容器（Phase 4）
       ↓
  query() (query.py)           ← 异步 generator 状态机（核心循环）
       ↓
  LLMProvider.stream()         ← 归一化 ProviderEvent
       ↓
  Tool Orchestration           ← 读并行 / 写串行
```

## 编码规范

- **忠实复刻 CC 架构**：不自创模式，structure.md 里说用什么就用什么
- **不过度设计**：不加 structure.md 里没规划的功能
- **类型注解**：所有函数签名都要有 type hints
- **错误处理**：工具执行错误返回 `ToolResult(is_error=True)`，不要 raise 到 agent loop
- **import 规范**：`from __future__ import annotations` 写在每个文件开头
- **Provider 事件归一化**：query.py 只处理 ProviderEvent，不接触 SDK 特定类型
- **工具并发安全**：`is_read_only=True` 的工具才能并行，写工具必须串行
- **测试用 mock provider**：不需要真 API key 也能跑通 query loop

## 目录结构

```
src/nanocc/
├── types.py          # 核心类型定义
├── constants.py      # 常量阈值（与 CC 一致）
├── messages.py       # 消息创建/API 格式转换
├── query.py          # agent loop 异步 generator 状态机
├── context.py        # 三段式 system prompt 装配
├── providers/        # LLM 后端（anthropic / openai_compat）
├── tools/            # 工具系统（base / orchestration / 6 个核心工具）
├── compact/          # 上下文管理（budget → micro → auto compact）
├── engine.py         # 有状态会话容器（suspend/resume）
├── memory/           # 记忆系统（memdir, session_memory, auto_dream, daily_log）
├── hooks/            # Hook 系统（types, engine, builtins）
├── skills/           # Skill 加载与执行
├── mcp/              # MCP server 集成（client, config, tool_wrapper）
├── agents/           # 子 Agent（fork, coordinator）
├── assistant/        # Assistant/KAIROS 模式（mode, proactive, brief）
├── cli/              # CLI 入口（click + rich）
└── utils/            # 工具模块（abort, tokens, git, config, session_storage）
```

## 当前状态

- **Phase 1** ✅ 基础：types + Provider + 最小 loop + 流式对话
- **Phase 2** ✅ 工具系统：6 个核心工具 + 并发编排 + agent loop 集成
- **Phase 3** ✅ 上下文管理：三层 compact 管线 + context 装配 + token 计数
- **Phase 4** ✅ Engine + 记忆系统：memdir + session_memory + auto_dream + 会话持久化
- **Phase 5** ✅ Hooks + Skills + MCP：插件系统 + skill 执行 + MCP server 集成
- **Phase 6** ✅ 子 Agent：fork + coordinator + AgentTool 并行任务
- **Phase 7** ✅ Assistant / KAIROS 模式：长驻守护 + proactive tick + Brief 工具
- **Phase 8-10** 待实现（见 structure.md）

## 注意事项

- 默认 provider 是 `openrouter`（不是 anthropic），API key 环境变量是 `OPENROUTER_API_KEY`
- OpenRouter 模型名格式：`provider/model`（如 `moonshotai/kimi-k2.5`）
- `rg`（ripgrep）在某些环境下是 shell alias，GrepTool 用 `shutil.which("rg")` 查找真实路径
- query.py 中 `_BlockAccumulator` 类负责从流式事件积累 ContentBlock，不要用 locals() hack
