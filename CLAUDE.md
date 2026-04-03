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

## 配置

Provider/Model/API Key 通过 `~/.nanocc/settings.json`（全局）或 `.nanocc/settings.json`（项目级）配置：

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

优先级：`/model` 会话覆盖 > CLI 标志 > 环境变量 > settings.json > 内置默认值

已知 provider：`openrouter`、`anthropic`、`openai`、`together`、`groq`（自动匹配 baseUrl）。
其他名字走 OpenAI 兼容，需配 `apiBaseUrl`。

## 常用命令

```bash
# 运行（配好 settings.json 后无需额外参数）
uv run nanocc -p "prompt"                          # 单轮
uv run nanocc                                       # REPL
uv run nanocc -c                                    # 恢复上次会话
uv run nanocc -m qwen/qwen3.5-flash --api-key $KEY # CLI 标志覆盖 settings

# REPL 中切换模型 / 恢复会话
> /model                                            # 查看当前模型
> /model qwen/qwen3.5-flash-02-23                   # 切换模型
> /resume                                           # 列出并恢复历史会话

# 安装为全局 CLI（editable 模式，改代码立即生效）
uv tool install -e .                                # 推荐：装到 ~/.local/bin/nanocc
pip install -e .                                    # 备选：装到当前 Python 环境
# 装完后任意目录直接运行 nanocc，无需 uv run

# 开发
uv run python -c "import nanocc"                    # 验证导入
uv run python -m nanocc --help                      # CLI 帮助

# 测试
uv run pytest tests/ -v                             # 全量测试（176 个）
uv run pytest tests/test_query.py -v                # 单模块测试
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
├── types.py          # 核心类型定义（Message, ContentBlock, QueryParams, LoopState）
├── constants.py      # 常量阈值（与 CC 一致）
├── messages.py       # 消息创建/API 格式转换/反序列化（from_api_messages）
├── query.py          # agent loop 异步 generator 状态机 + hook 触发 + assistant tick
├── context.py        # 三段式 system prompt 装配 + cache_control
├── providers/        # LLM 后端（anthropic / openai_compat）
├── tools/            # 工具系统（12 个工具 + orchestration 含 hook 集成）
├── compact/          # 上下文管理（budget → micro → auto compact）
├── engine.py         # 有状态会话容器（get_state/restore_state + extract_memories）
├── memory/           # 记忆系统（memdir, session_memory[10 sections], auto_dream[3 phases], daily_log）
├── hooks/            # Hook 系统（5 事件 × 3 类型，已接入 query loop）
├── skills/           # Skill 加载与执行（含 fork 模式）
├── mcp/              # MCP server 集成（stdio/http/sse + resources）
├── agents/           # 子 Agent（fork + coordinator[parallel+serial]）
├── assistant/        # Assistant/KAIROS 模式（mode, proactive tick, Brief/Sleep 工具）
├── cli/              # CLI 入口（click + rich）
└── utils/            # 工具模块（abort, tokens, git, config, session_storage, cost）

tests/                # 176 个测试，mock provider 不需要 API key，uv run pytest tests/ -v
```

## 当前状态

- **Phase 1** ✅ 基础：types + Provider + 最小 loop + 流式对话
- **Phase 2** ✅ 工具系统：6 个核心工具 + 并发编排 + agent loop 集成
- **Phase 3** ✅ 上下文管理：三层 compact 管线 + context 装配 + token 计数
- **Phase 4** ✅ Engine + 记忆系统：memdir + session_memory + auto_dream + 会话持久化
- **Phase 5** ✅ Hooks + Skills + MCP：插件系统 + skill 执行 + MCP server 集成
- **Phase 6** ✅ 子 Agent：fork + coordinator + AgentTool 并行任务
- **Phase 7** ✅ Assistant / KAIROS 模式：长驻守护 + proactive tick + Brief 工具
- **链路修复** ✅ (2026-04-03) 9 项跨模块集成修复 + 153 个测试用例
- **Provider 配置重构** ✅ (2026-04-03) settings.json 持久化配置 + /model 切换 + AgentTool 修复
- **Session 持久化** ✅ (2026-04-03) 增量 transcript append + compact boundary 感知恢复 + `-c`/`--continue` + `/resume` 命令 + AgentTool 超时 + 工具并发异常处理
- **Phase 8-10** 待实现（见 structure.md）

### 链路修复详情 (2026-04-03)

审查 structure.md 后发现多个模块已实现但未接通，已全部修复：

1. **Hooks 接入 query loop** — orchestration.py 每个工具执行前后 fire tool_start/tool_complete，query.py end_turn 时 fire stop
2. **Assistant tick 分支** — query.py end_turn 后等待 proactive_engine.wait_for_next()（tick/user_message/shutdown）
3. **Engine restore_state** — 反序列化 messages/usage/session_memory，--continue 链路打通
4. **Engine extract_memories** — 每轮结束后后台 fire-and-forget LLM side-query 抽取 memory
5. **BriefTool + SleepTool 注册** — tools/registry.py 12 个工具
6. **session_memory 10 sections** — 补了 Open Questions/Dependencies/Decisions Made/Next Steps
7. **Skill fork 模式** — execute_skill() 支持 context="fork" 在隔离子 agent 运行
8. **coordinator serial subtasks** — run_serial_subtasks() 顺序执行写任务
9. **auto_dream Phase 2/3** — transcript 扫描信号 + LLM consolidate 更新 memory files
10. **MCP HTTP/SSE transport** — 三种 transport + list_resources/read_resource

## 注意事项

- 默认 provider 是 `openrouter`（不是 anthropic），可通过 `~/.nanocc/settings.json` 配置
- API key 解析顺序：`--api-key` > 环境变量（如 `OPENROUTER_API_KEY`）> `settings.json` 的 `apiKey`
- OpenRouter 模型名格式：`provider/model`（如 `qwen/qwen3.5-flash-02-23`）
- `rg`（ripgrep）在某些环境下是 shell alias，GrepTool 用 `shutil.which("rg")` 查找真实路径
- query.py 中 `_BlockAccumulator` 类负责从流式事件积累 ContentBlock，不要用 locals() hack
