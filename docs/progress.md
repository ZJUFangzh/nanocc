# nanocc 开发进度

目标：基于 Claude Code 2.1.88 源码，用 Python 复刻核心架构，控制在 ~10,000 行。
完整规划见 `ARCHITECTURE.md`（10 个 Phase）。

---

## Phase 1: 基础 ✅ (2026-04-02)

**目标**: types + Provider + 最小 agent loop，能和 LLM 流式对话。

**新增文件 (~1,500 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `pyproject.toml` | 35 | 项目配置，hatch 构建，uv 兼容 |
| `src/nanocc/__init__.py` | 3 | 包标记 |
| `src/nanocc/__main__.py` | 5 | `python -m nanocc` 入口 |
| `src/nanocc/types.py` | 226 | 核心类型：Message, ContentBlock, StreamEvent, Terminal, Tool Protocol |
| `src/nanocc/constants.py` | 80 | token 阈值、模型窗口、工具限制（与 CC 一致） |
| `src/nanocc/messages.py` | 194 | 消息工厂、Anthropic API 格式转换、工具函数 |
| `src/nanocc/utils/abort.py` | 46 | AbortController（asyncio Event） |
| `src/nanocc/providers/base.py` | 85 | LLMProvider Protocol + ProviderEvent 归一化类型 |
| `src/nanocc/providers/anthropic.py` | 171 | Anthropic Claude 原生 SDK 流式 |
| `src/nanocc/providers/openai_compat.py` | 247 | OpenAI 兼容 API 适配层 |
| `src/nanocc/providers/registry.py` | 38 | Provider 工厂，自动匹配 base_url |
| `src/nanocc/cli/app.py` | 270 | Click CLI：`-p` 单轮 + REPL 多轮 |

**关键设计决策**:
- 默认 Provider 为 OpenAI 兼容（`openrouter`），非 Anthropic 原生——覆盖面更广
- 所有类型用 dataclass，不依赖 Pydantic
- AsyncGenerator 状态机忠实复刻 CC 的 `query()` 模式
- ProviderEvent 归一化层：agent loop 不接触任何 SDK 特定类型

**验证通过**:
```bash
uv run nanocc -p "hello" --api-key $KEY -m moonshotai/kimi-k2.5  # 流式输出
uv run nanocc  # REPL 多轮对话
```

---

## Phase 2: 工具系统 ✅ (2026-04-02)

**目标**: 6 个核心工具 + 并发编排 + 接入 agent loop。

**新增文件 (~900 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `src/nanocc/tools/base.py` | 46 | BaseTool 基类，默认权限/并发安全 |
| `src/nanocc/tools/registry.py` | 32 | 工具注册、按名查找 |
| `src/nanocc/tools/orchestration.py` | 152 | 并发/串行批执行，CC 的 partition 逻辑 |
| `src/nanocc/tools/bash.py` | 92 | BashTool — 子进程、超时、输出截断 |
| `src/nanocc/tools/file_read.py` | 74 | FileReadTool — offset/limit、行号 |
| `src/nanocc/tools/file_write.py` | 56 | FileWriteTool — 原子写入、auto mkdir |
| `src/nanocc/tools/file_edit.py` | 106 | FileEditTool — 唯一性检查、replace_all |
| `src/nanocc/tools/glob_tool.py` | 66 | GlobTool — glob 匹配、按 mtime 排序 |
| `src/nanocc/tools/grep_tool.py` | 211 | GrepTool — ripgrep 优先 + Python re fallback |

**关键设计决策**:
- 并发模型复刻 CC：`is_read_only=True` 的工具并行（最多 10 个），写工具串行
- `partition_tool_calls()` 把连续的并发安全工具合批，非并发的单独成批
- Grep 先尝试 `shutil.which("rg")`，找不到 rg 自动降级 Python re
- 权限模型保留 allow/deny/ask 三态，Phase 8 加 UI 确认

**验证通过**:
```bash
# 模型调用 Read 工具读文件
uv run nanocc -p "Read README.md" --api-key $KEY -m moonshotai/kimi-k2.5

# 模型多工具多轮循环：Glob + Bash
uv run nanocc -p "List all .py files and count lines" --api-key $KEY -m moonshotai/kimi-k2.5
```

---

## Phase 3: 上下文管理 ✅ (2026-04-02)

**目标**: compact 三层管线 + context 装配 + token 计数 + git 快照。

**新增文件 (~750 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `src/nanocc/utils/tokens.py` | 95 | token 计数：usage 优先 + 字符估算 fallback（padded 4/3） |
| `src/nanocc/utils/git.py` | 80 | git 状态快照（branch、changed files、recent commits） |
| `src/nanocc/context.py` | 85 | 三段式 system prompt 装配 + cache_control |
| `src/nanocc/compact/__init__.py` | 0 | 包标记 |
| `src/nanocc/compact/tool_result_budget.py` | 55 | Layer 1: 单结果 50K 截断 + 消息级 200K 上限 |
| `src/nanocc/compact/micro_compact.py` | 65 | Layer 2: 旧 tool_result → `[cleared]`，保留最近 5 个 |
| `src/nanocc/compact/auto_compact.py` | 220 | Layer 3: LLM 摘要压缩，阈值触发，3 次失败熔断 |
| `src/nanocc/compact/post_compact.py` | 100 | compact 后文件重注入（最多 5 文件，50K token 预算） |

**关键设计决策**:
- 三层管线按顺序执行：budget → micro → auto（每轮 LLM 调用前）
- auto compact 使用 `<analysis>` + `<summary>` 标签结构（CC 原版 prompt）
- compact 后消息替换为 `[boundary, summary_msg]`，post_compact 追加文件附件
- token 估算：有 usage 数据时用实际值 + 后续消息估算，无则全量字符估算
- 熔断机制：连续 3 次 compact 失败后停止尝试

**验证通过**:
```python
# tool_result_budget: 60K -> 50K 截断
# micro_compact: 10 个结果中清除 7 个，保留最近 3 个
# should_auto_compact: 阈值逻辑正确
# context.py: 三段拼装 + cache_control
# tokens.py: usage-based + estimation fallback
# 端到端 OpenRouter 调用正常
```

---

## Phase 4: Engine + 记忆系统 ✅ (2026-04-02)

**目标**: 有状态会话容器 + 记忆持久化（memdir, session_memory, auto_dream）。

**新增文件 (~950 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `src/nanocc/engine.py` | 203 | QueryEngine 有状态会话容器，suspend/resume |
| `src/nanocc/memory/memdir.py` | 109 | 记忆目录管理，文件级 CRUD |
| `src/nanocc/memory/session_memory.py` | 84 | 会话记忆，固定 section 模板 |
| `src/nanocc/memory/claude_md.py` | 59 | CLAUDE.md 层级注入 |
| `src/nanocc/memory/extract.py` | 101 | 记忆提取（从对话中抽取） |
| `src/nanocc/memory/auto_dream.py` | 129 | auto-dream 自动记忆归纳 |
| `src/nanocc/memory/daily_log.py` | 66 | 每日工作日志 |
| `src/nanocc/utils/config.py` | 73 | 配置加载 |
| `src/nanocc/utils/session_storage.py` | 95 | 会话存储（JSON 持久化） |
| `src/nanocc/utils/cost.py` | 35 | 费用计算 |

**关键设计决策**:
- Engine 是有状态会话容器，管理 messages、tools、provider 生命周期
- Memory 类型分类约束：代码能推导的不记、git 能查的不记、临时状态不记
- Session Memory 固定模板（10 个 section），保证 compact 消费时格式稳定
- CLAUDE.md 层级注入：走到哪规则跟到哪

---

## Phase 5: Hooks + Skills + MCP ✅ (2026-04-02)

**目标**: 插件系统 + skill 执行 + MCP server 集成。

**新增文件 (~720 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `src/nanocc/hooks/types.py` | 43 | Hook 类型定义 |
| `src/nanocc/hooks/engine.py` | 217 | Hook 引擎，事件触发 + 执行 |
| `src/nanocc/hooks/builtins.py` | 12 | 内置 hook |
| `src/nanocc/skills/loader.py` | 109 | Skill 发现与加载 |
| `src/nanocc/skills/executor.py` | 45 | Skill 执行器 |
| `src/nanocc/mcp/client.py` | 160 | MCP server 客户端 |
| `src/nanocc/mcp/config.py` | 36 | MCP 配置 |
| `src/nanocc/mcp/tool_wrapper.py` | 45 | MCP 工具包装为本地 Tool |
| `src/nanocc/tools/skill_tool.py` | 57 | SkillTool — skill 调用工具 |

**关键设计决策**:
- Hook 在 query loop 的关键点触发（tool 前/后、消息前/后）
- Skill 文件即插件，按约定目录加载
- MCP server 通过 tool_wrapper 映射为本地 BaseTool，统一调度

---

## Phase 6: 子 Agent ✅ (2026-04-02)

**目标**: 子 agent 派生 + 协调器，并行任务处理。

**新增文件 (~320 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `src/nanocc/agents/fork.py` | 72 | 子 agent fork（独立 messages/context） |
| `src/nanocc/agents/coordinator.py` | 75 | 多 agent 协调（任务分发/结果收集） |
| `src/nanocc/tools/agent_tool.py` | 66 | AgentTool — 派生子 agent |
| `src/nanocc/tools/ask_user.py` | 40 | AskUserTool — 子 agent 向用户提问 |
| `src/nanocc/tools/web_fetch.py` | 70 | WebFetchTool — URL 抓取 |

**关键设计决策**:
- fork 创建独立的 messages 副本和 context，共享 provider
- coordinator 管理多个并行 agent，汇总结果
- 子 agent 工具集可限制（如只读 agent）

---

## Phase 7: Assistant / KAIROS 模式 ✅ (2026-04-02)

**目标**: 长驻守护模式 + proactive 能力 + 结构化输出。

**新增文件 (~290 行)**:

| 文件 | 行数 | 功能 |
|---|---|---|
| `src/nanocc/assistant/mode.py` | 125 | 模式检测、会话持久化、--continue 恢复 |
| `src/nanocc/assistant/proactive.py` | 89 | tick 循环、Sleep 工具、焦点感知 |
| `src/nanocc/assistant/brief.py` | 73 | Brief 结构化消息工具 |

**关键设计决策**:
- `--assistant` 启用长驻模式，`--continue` 恢复会话
- 记忆切换为 append-only 日志模式
- 周期性 tick 唤醒，proactive 能力
- Brief 工具提供结构化输出

---

## 链路修复 ✅ (2026-04-03)

**目标**: 审查架构规划，修复所有已实现但未接通的跨模块链路，补全测试。

**修复项 (9 项)**:

| # | 修复 | 涉及文件 |
|---|---|---|
| 1 | Hooks 接入 query loop（tool_start/tool_complete/stop） | `query.py`, `tools/orchestration.py` |
| 2 | Assistant tick 分支（end_turn 后等 tick/user_message） | `query.py`, `types.py`, `messages.py` |
| 3 | Engine restore_state + extract_memories | `engine.py`, `messages.py` |
| 4 | BriefTool + SleepTool 注册到 registry | `tools/registry.py` |
| 5 | session_memory 补到 10 个 section | `memory/session_memory.py` |
| 6 | Skill fork 模式（execute_skill + fork_agent） | `skills/executor.py` |
| 7 | coordinator serial subtasks + TerminalReason 修复 | `agents/coordinator.py` |
| 8 | auto_dream Phase 2/3 填充（transcript 扫描 + LLM consolidate） | `memory/auto_dream.py` |
| 9 | MCP HTTP/SSE transport + list_resources/read_resource | `mcp/client.py` |

**测试套件新增**: 15 个测试文件，153 个测试用例，全部 PASS（0.34s），无需 API key。

---

## Provider 配置重构 ✅ (2026-04-03)

**目标**: settings.json 持久化配置 + /model 运行时切换 + AgentTool 修复。

**变更**:
- `utils/config.py` — 支持 `~/.nanocc/settings.json` 和 `.nanocc/settings.json` 层级配置
- `providers/registry.py` — 按 provider 名自动匹配 base_url
- `cli/app.py` — `/model` 命令运行时切换模型
- `tools/agent_tool.py` — 修复子 agent provider 继承

**关键设计决策**:
- 优先级：`/model` 会话覆盖 > CLI 标志 > 环境变量 > settings.json > 内置默认值
- 已知 provider 自动匹配 baseUrl，未知 provider 走 OpenAI 兼容（需配 `apiBaseUrl`）

---

## Session 持久化 ✅ (2026-04-03)

**目标**: 增量 transcript + compact 感知恢复 + `-c`/`--continue` + `/resume` 命令。

**变更**:
- `utils/session_storage.py` — 增量 append 模式写入 transcript（JSONL）
- `engine.py` — compact boundary 感知的 state 恢复
- `cli/app.py` — `-c`/`--continue` 恢复上次会话 + `/resume` 列出历史会话
- `tools/agent_tool.py` — 子 agent 超时处理
- `tools/orchestration.py` — 工具并发异常处理（单个工具失败不影响整批）
- `query.py` — engine 与 query loop 共享 message list

**新增测试**: 23 个测试用例，总计 176 个

---

## Provider 精简 ✅ (2026-04-03)

**目标**: 移除 together/groq 专用 provider，统一走 custom OpenAI 兼容。

**变更**:
- 移除 `providers/` 中 together/groq 相关代码
- `CLAUDE.md` 补充 custom provider 配置示例
- 已知 provider 收敛为 3 个：openrouter, anthropic, openai

---

## 架构分离 ✅ (2026-04-11)

**目标**: 把产品层逻辑（IM 接入、session 编排）从 nanocc 中剥离，移至独立的 cowork 项目。
nanocc 重新定位为纯 agent runtime。

**变更**:
- 删除 `src/nanocc/assistant/mode.py` — AssistantMode 生命周期编排器移至 cowork SessionManager
- 删除 `src/nanocc/channels/` — Channel/IM 实现移至 cowork（原计划的 Telegram/Webhook/WebSocket 通道）
- `tools/registry.py` 移除 BriefTool/SleepTool — assistant 模式专属工具，cowork 启用时手动追加
- `tests/test_assistant.py` 移除 6 个 AssistantMode 测试（保留 ProactiveEngine/Brief/Sleep 测试）
- `tests/test_tools.py` `tests/test_engine.py` 工具数断言 12 → 10
- `ARCHITECTURE.md` 重写 Section 12（Channel/IM）为 cowork 边界说明，Section 10 移除 AssistantMode 子节
- 新增 `docs/cowork-boundary.md` — cowork 项目消费 nanocc 的方式

**保留的机制（cowork 会用到）**:
- `assistant/proactive.py` — ProactiveEngine 事件队列
- `assistant/brief.py` — BriefTool / SleepTool（cowork 手动追加）
- `query.py:184-193` — tick 分支
- `engine.py` get_state/restore_state/save_session — 序列化接口
- `utils/session_storage.py` — 持久化实现

**测试**: 170 个全部通过

---

## 当前统计

| 指标 | 值 |
|---|---|
| 总代码行数 | ~6,500 |
| 目标行数 | ~9,800 |
| 完成 Phase | 7 / 10 + 链路修复 + 配置/持久化/精简 + 架构分离 |
| Python 文件数 | 84 (含 17 个测试) |
| 核心工具数 | 10 (Bash, Read, Write, Edit, Glob, Grep, Agent, AskUser, WebFetch, Skill) |
| 可选工具 | 2 (Brief, Sleep) — 由 cowork 在 assistant 模式启用时追加 |
| 支持的 Provider | 3 + custom (openrouter, anthropic, openai) |
| Compact 层数 | 3 (budget + micro + auto) |
| 记忆模块 | 6 (memdir, session_memory, claude_md, extract, auto_dream, daily_log) |
| MCP transport | 3 (stdio, http, sse) |
| 测试用例 | 170 |

---

## 后续 Phase

| Phase | 内容 | 预估行数 |
|---|---|---|
| 8 | CLI 终端 UI 完善 | ~1,000 |
| 9 | ~~Channel / IM 通道~~ | 移至 cowork |
| 10 | SDK + 打包 | ~600 |
