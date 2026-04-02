# nanocc: Python Nano Claude Code 实现规划

## Context

基于 Claude Code 2.1.88 源码的深度分析，用 Python 复刻其核心架构，控制在 1 万行以内。目标：既可作为 CLI 日常使用，也可作为可扩展的 Agent SDK，同时支持通过 Channel 对接 Telegram 等 IM 平台。

---

## Harness Engineering 设计理念

### 问题：AI Agent 的代码漂移

AI agent 在长期开发中面临一个根本性问题：**越改越偏**。不是因为 AI 不够聪明，而是因为：
- 上下文会丢失（compact 压掉了关键决策背景）
- 记忆会腐烂（半年前记的"用 v2 API"，现在已经是 v4）
- 风格会漂移（每次对话的 AI 状态不同，产出的代码风格逐渐偏离）
- 错误会重犯（上次踩的坑没记住，下次换个 session 又踩）

Prompt engineering 试图通过"教 AI 怎么想"来解决这个问题。但这不够——AI 每次对话都是从零开始的，你没法靠一个 prompt 把所有历史教训塞进去。

**Harness engineering 的思路完全不同：不控制 AI 怎么想，而是设计 AI 工作的环境和反馈机制，让正确行为成为系统属性而非 AI 的个人判断。**

### 核心框架：环境设计 + 反馈闭环

```
┌─────────────────────────────────────────────────────────────┐
│                    环境设计（前馈约束）                       │
│                                                             │
│  "不是命令 AI 遵守规范，而是让 AI 在工作时自然看到规范"       │
│                                                             │
│  ① CLAUDE.md 层级注入                                       │
│     走到哪规则跟到哪——AI 读某个目录的代码时，                │
│     那个目录的 CLAUDE.md 才被注入上下文                      │
│                                                             │
│  ② Memory 类型分类约束                                      │
│     限制什么能记、什么不能记——                               │
│     代码能推导的不记、git 能查的不记、临时状态不记            │
│     防止 memory 膨胀和污染                                   │
│                                                             │
│  ③ Session Memory 固定模板                                  │
│     强制结构化输出——10 个固定 section，                      │
│     AI 不能自由发挥，只能填充内容                            │
│     保证 compact 消费时格式稳定                              │
│                                                             │
│  ④ Tool Schema 能力边界                                     │
│     限制 AI 能做什么动作——                                   │
│     不是什么工具都给，而是按场景精确授予                     │
│                                                             │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
                 AI Agent 执行任务
                          ↓
┌─────────────────────────┴───────────────────────────────────┐
│                    反馈闭环（后馈修正）                       │
│                                                             │
│  "AI 走偏了怎么自动拉回来"                                   │
│                                                             │
│  ⑤ Memory 引用前验证                                        │
│     记忆不是事实——引用前必须 grep/check 确认还存在           │
│     "memory 说 utils.py 有个 parse() 函数"                  │
│      → 先 grep 确认 parse() 还在，再推荐                    │
│                                                             │
│  ⑥ Feedback Memory 持久化纠正                               │
│     用户纠正行为 → 自动存为 feedback 类型 memory             │
│     下次不同 session 也能读到，同样的错不犯第二次            │
│     记录的不只是"不要做 X"，还有 **为什么** 不要做           │
│                                                             │
│  ⑦ Auto Dream 定期蒸馏                                      │
│     24h + 5session 门控 → 三阶段归并                        │
│     清理过期 memory、合并碎片、转绝对日期                    │
│     防止记忆随时间腐烂                                       │
│                                                             │
│  ⑧ Compact 后精确恢复                                       │
│     压缩不是丢弃——补回最近 5 个文件、当前 plan、             │
│     已加载 skill、MCP 工具列表增量                           │
│     保证压缩前后 AI 的工作状态不会断裂                       │
│                                                             │
│  ⑨ Hook 触发点                                              │
│     工具执行前后自动触发验证/审计/通知                       │
│     不依赖 AI 主动调用，是基础设施层面的保证                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 在 nanocc 中的具体落地

每个模块如何体现 harness 思想：

| 模块 | Harness 机制 | 解决什么漂移问题 |
|---|---|---|
| `memory/claude_md.py` | CLAUDE.md 层级 + lazy 注入 | 风格漂移：AI 每次都看到当前目录的编码规范 |
| `memory/memdir.py` | 4 类 memory + 排除规则 + 容量限制 | 认知漂移：防止 memory 膨胀污染后续行为 |
| `memory/session_memory.py` | 固定 section 模板 | 状态漂移：结构化笔记让 compact 恢复时不丢关键状态 |
| `memory/extract.py` | 自动 feedback memory 抽取 | 错误重犯：用户纠正自动持久化，跨 session 生效 |
| `memory/auto_dream.py` | 门控蒸馏 + 日期绝对化 + 去重 | 记忆腐烂：定期清理过期和冗余 memory |
| `compact/post_compact.py` | 精确恢复最近文件/plan/skill | 上下文断裂：compact 后 AI 不会忘记正在做什么 |
| `hooks/engine.py` | 工具执行前后自动触发 | 质量漂移：自动 lint/test/审计不依赖 AI 主动想起 |
| `skills/executor.py` | `allowed_tools` 临时授权 | 能力泄漏：skill 结束后临时权限自动撤销 |
| `context.py` | system prompt 三段拼装 + cache 分割 | 指令遗忘：静态指令缓存不被动态内容冲掉 |

### 类比：Harness 像什么

**Prompt engineering** 像给新员工做入职培训——你教得再好，他也会忘。

**Harness engineering** 像设计办公环境和工作流程：
- 编码规范贴在工位旁边（CLAUDE.md lazy injection）
- 每次提交代码自动跑 CI（hooks）
- 犯过的错误记录在 wiki 里，新人也能看到（feedback memory）
- 每周 review 会议清理过期的决策（auto dream）
- 离开工位时自动锁屏（skill 临时权限自动撤销）

**好的 harness 设计让"做对的事"成为最自然的路径，让"做错的事"需要额外的努力才能绕过。**

### 核心原则

1. **不依赖 AI 的记忆力** — memory 有引用前验证、有定期蒸馏、有容量限制
2. **不依赖 AI 的自律性** — hooks 在执行层强制触发，不是"建议 AI 去做"
3. **不依赖 AI 的一致性** — CLAUDE.md 按路径注入，每次都重新看到规范
4. **错误必须持久化** — feedback memory 跨 session 传递，不会因为换对话而遗忘
5. **压缩不等于遗忘** — compact 后精确恢复工作状态，而不是只留模糊摘要

---

## 项目结构 (~9,800 行)

```
nanocc/
├── pyproject.toml
├── src/nanocc/
│   ├── __init__.py              (30)   -- 公共 API 导出
│   ├── __main__.py              (10)   -- python -m nanocc
│   ├── types.py                 (280)  -- Message, ContentBlock, StreamEvent, Terminal, AssistantMode
│   ├── constants.py             (100)  -- token 阈值、限制常量、hook 事件枚举
│   │
│   ├── # ── 核心引擎 ──
│   ├── query.py                 (600)  -- 异步 generator 状态机 + hook 触发点 + tick 机制
│   ├── engine.py                (500)  -- QueryEngine 有状态会话容器 + session 挂起/恢复
│   │
│   ├── # ── LLM 后端 ──
│   ├── providers/
│   │   ├── base.py              (150)  -- LLMProvider 协议 + ProviderEvent 归一化
│   │   ├── anthropic.py         (300)  -- Claude API (流式、thinking、cache)
│   │   ├── openai_compat.py     (250)  -- OpenAI 兼容接口
│   │   └── registry.py          (60)   -- provider 工厂/注册
│   │
│   ├── # ── 工具系统 ──
│   ├── tools/
│   │   ├── base.py              (200)  -- Tool 协议、ToolUseContext、权限模型
│   │   ├── registry.py          (80)   -- 工具注册与发现
│   │   ├── orchestration.py     (200)  -- 并发/串行分批执行
│   │   ├── bash.py              (250)  -- BashTool
│   │   ├── file_read.py         (120)  -- FileReadTool
│   │   ├── file_write.py        (100)  -- FileWriteTool
│   │   ├── file_edit.py         (180)  -- FileEditTool
│   │   ├── glob_tool.py         (80)   -- GlobTool
│   │   ├── grep_tool.py         (100)  -- GrepTool
│   │   ├── web_fetch.py         (100)  -- WebFetchTool
│   │   ├── ask_user.py          (60)   -- AskUserQuestionTool
│   │   ├── agent_tool.py        (150)  -- AgentTool
│   │   └── skill_tool.py        (100)  -- SkillTool (skill 展开器)
│   │
│   ├── # ── Skill 系统 ──
│   ├── skills/
│   │   ├── loader.py            (200)  -- skill 发现、加载、frontmatter 解析
│   │   ├── executor.py          (150)  -- skill 展开、参数替换、权限临时授予
│   │   └── bundled/             (100)  -- 内置 skill (commit, review-pr 等 .md 文件)
│   │
│   ├── # ── MCP 集成 ──
│   ├── mcp/
│   │   ├── client.py            (300)  -- MCP server 连接、工具/资源发现
│   │   ├── config.py            (100)  -- MCP server 配置加载
│   │   └── tool_wrapper.py      (100)  -- MCP 工具包装为 nanocc Tool
│   │
│   ├── # ── Hooks / Harness Engineering ──
│   ├── hooks/
│   │   ├── types.py             (80)   -- HookEvent 枚举、Hook 类型定义
│   │   ├── engine.py            (200)  -- hook 注册、匹配、执行引擎
│   │   └── builtins.py          (80)   -- 内置 hook (pre-commit check 等)
│   │
│   ├── # ── 上下文管理 ──
│   ├── compact/
│   │   ├── auto_compact.py      (200)  -- 超阈值自动摘要
│   │   ├── micro_compact.py     (120)  -- 旧 tool_result 裁剪
│   │   ├── tool_result_budget.py(100)  -- 大结果截断/落盘
│   │   └── post_compact.py      (100)  -- compact 后附件重建
│   │
│   ├── # ── 记忆系统 ──
│   ├── memory/
│   │   ├── memdir.py            (200)  -- MEMORY.md 索引 + topic files
│   │   ├── session_memory.py    (150)  -- 会话结构化笔记
│   │   ├── claude_md.py         (120)  -- CLAUDE.md 层级加载
│   │   ├── extract.py           (120)  -- 每轮后台 memory 抽取
│   │   ├── auto_dream.py        (200)  -- 离线 memory 蒸馏 (跨 session transcript 归并)
│   │   └── daily_log.py         (120)  -- Assistant 模式日志制 memory (append-only)
│   │
│   ├── # ── Assistant / Daemon 模式 (KAIROS) ──
│   ├── assistant/
│   │   ├── mode.py              (150)  -- 模式检测、初始化、session 持久化
│   │   ├── proactive.py         (150)  -- tick 循环、Sleep 工具、焦点感知
│   │   └── brief.py             (100)  -- Brief 结构化消息通道
│   │
│   ├── # ── 子 Agent ──
│   ├── agents/
│   │   ├── fork.py              (200)  -- forked agent + CacheSafeParams
│   │   └── coordinator.py       (150)  -- dispatcher + workers 模式
│   │
│   ├── # ── 上下文装配 ──
│   ├── context.py               (200)  -- system prompt + user/system context
│   ├── messages.py              (250)  -- 消息创建/归一化/辅助
│   │
│   ├── # ── Channel / IM 通道 ──
│   ├── channels/
│   │   ├── base.py              (150)  -- Channel 协议 (消息收发抽象)
│   │   ├── telegram.py          (250)  -- Telegram Bot 通道
│   │   ├── webhook.py           (150)  -- 通用 Webhook 通道 (Slack/Discord/飞书)
│   │   └── websocket.py         (150)  -- WebSocket 通道 (Web UI / 自定义前端)
│   │
│   ├── # ── CLI / 终端 UI ──
│   ├── cli/
│   │   ├── app.py               (300)  -- REPL 主循环 + click CLI
│   │   ├── ui.py                (300)  -- Rich 渲染 (markdown/syntax/diff)
│   │   ├── permissions_ui.py    (100)  -- 权限确认对话框
│   │   └── commands.py          (150)  -- slash 命令
│   │
│   ├── # ── SDK 层 ──
│   ├── sdk.py                   (200)  -- nanoccSession + query() 便捷函数
│   │
│   └── # ── 工具模块 ──
│       └── utils/
│           ├── tokens.py        (80)   -- token 计数/估算
│           ├── abort.py         (60)   -- AbortController
│           ├── config.py        (120)  -- 配置文件 + hook settings 加载
│           ├── git.py           (80)   -- git 状态快照
│           ├── session_storage.py(100) -- transcript 持久化
│           └── cost.py          (60)   -- usage 追踪
```

---

## 核心模块设计

### 1. Agent Loop (`query.py`) -- 核心中的核心

**忠实复刻 Claude Code 的异步 generator 状态机**，不是 ReAct。
在原有基础上增加 **hook 触发点**：

```python
@dataclass
class LoopState:
    messages: list[Message]
    tool_use_context: ToolUseContext
    auto_compact_tracking: AutoCompactTracking | None
    turn_count: int
    transition: Continue | None
    hook_engine: HookEngine | None       # 新增

async def query(params: QueryParams) -> AsyncGenerator[StreamEvent | Message, Terminal]:
    state = LoopState(...)
    while True:
        # 1. 上下文治理管线
        apply_tool_result_budget(state.messages)
        micro_compact(state.messages, ...)
        compaction = await auto_compact_if_needed(state.messages, state, params)

        # 2. 调用 LLM (流式)
        async for event in params.provider.stream(...):
            yield event

        # 3. abort 检查 + synthetic tool_result 补齐
        if state.tool_use_context.abort_controller.is_aborted:
            yield from synthesize_missing_tool_results(...)
            return Terminal(reason="aborted_streaming")

        # 4. 工具执行 (并发读/串行写) + hook 触发
        if tool_use_blocks:
            for block in tool_use_blocks:
                await state.hook_engine.fire("tool_start", block)   # harness hook
                result = await run_tool(block, ...)
                await state.hook_engine.fire("tool_complete", block, result)
                yield result.message
            state.turn_count += 1
            continue

        # 5. end_turn -> 完成
        await state.hook_engine.fire("stop", state.messages)        # harness hook
        return Terminal(reason="completed")
```

**终止状态**: completed, aborted_streaming, aborted_tools, prompt_too_long, max_turns, model_error

### 2. QueryEngine (`engine.py`)

有状态会话容器，`mutableMessages` 跨轮次持久化：

- `submit_message()` -> 组装上下文 -> 调用 `query()` -> yield 事件
- 管理 abort controller 生命周期
- 追踪 usage/cost
- SDK、CLI 和 Channel 共用同一个 Engine
- 每轮结束后触发 `extract_memories()` 和 `session_memory.maybe_update()`

### 3. LLM Provider 抽象 (`providers/`)

```python
class LLMProvider(Protocol):
    async def stream(messages, system_prompt, tools, *, model, ...) -> AsyncGenerator[ProviderEvent]
    def count_tokens(messages, model) -> int
    def get_context_window(model) -> int
```

- `ProviderEvent` 是归一化的流式事件类型
- agent loop 只处理 `ProviderEvent`，不接触 provider 特定类型
- 新增后端 = 实现 3 个方法，通常 < 300 行

### 4. 工具系统 (`tools/`)

```python
class Tool(Protocol):
    name: str
    input_schema: dict          # JSON Schema
    is_read_only: bool          # 决定能否并发

    def check_permissions(input, context) -> allow | deny | ask
    async def execute(input, context) -> ToolResult
```

**10 个核心工具**：Bash, FileRead, FileWrite, FileEdit, Glob, Grep, WebFetch, AskUser, Agent, Skill

**并发模型**（复刻 Claude Code）：
- `is_read_only=True` 的工具并行执行（最多 10 个）
- 写工具串行执行

### 5. Skill 系统 (`skills/`) -- 新增

**复刻 Claude Code 的 skill 架构**：skill 是 YAML frontmatter + Markdown 正文的 prompt 展开器。

```python
# loader.py
@dataclass
class SkillDefinition:
    name: str
    description: str
    allowed_tools: list[str]        # 临时授予的工具权限
    context: Literal["inline", "fork"]  # 执行上下文
    paths: list[str] | None        # 条件激活路径 (gitignore-style)
    model: str | None              # 模型覆盖
    hooks: dict | None             # skill 级 hooks
    content: str                   # Markdown prompt 正文

def load_skills(dirs: list[Path]) -> list[SkillDefinition]:
    """
    加载顺序（复刻 CC）：
    1. ~/.nanocc/skills/
    2. .nanocc/skills/ (项目级)
    3. 内置 bundled skills
    后加载的同名 skill 不覆盖先加载的
    """

# executor.py
async def execute_skill(skill: SkillDefinition, args: str, context: ToolUseContext):
    """
    1. 替换 $ARGUMENTS 占位符
    2. 通过 contextModifier 临时 grant allowed_tools 权限
    3. 展开为 user message 注入当前轮次
    4. fork 模式则在隔离子 agent 运行
    """
```

**内置 skill**：`commit.md`, `review-pr.md` 等放在 `skills/bundled/` 目录。

**关键设计**：skill 不是直接执行代码，而是把 prompt + 权限注入 agent loop，让模型按指令走。这与 Claude Code 完全一致。

### 6. MCP 集成 (`mcp/`) -- 新增

**精简但功能完整的 MCP 客户端**：

```python
# client.py
class MCPClient:
    """连接单个 MCP server，发现工具和资源"""

    async def connect(self, config: MCPServerConfig):
        """支持 stdio / http / sse 三种 transport"""

    async def list_tools(self) -> list[MCPToolSchema]:
        """获取 server 暴露的工具列表"""

    async def call_tool(self, name: str, args: dict) -> str:
        """调用 MCP 工具"""

    async def list_resources(self) -> list[MCPResource]:
        """列出可用资源"""

    async def read_resource(self, uri: str) -> str:
        """读取资源内容"""

# config.py
def load_mcp_config(cwd: str) -> dict[str, MCPServerConfig]:
    """
    加载 MCP 配置（复刻 CC 的多层级）：
    1. ~/.nanocc/settings.json -> mcpServers
    2. .nanocc/settings.json -> mcpServers
    """

# tool_wrapper.py
def wrap_mcp_tools(client: MCPClient, server_name: str) -> list[Tool]:
    """
    把 MCP server 的每个工具包装成 nanocc Tool：
    - name: mcp__{server}__{tool}
    - input_schema: passthrough
    - execute: 代理到 client.call_tool()
    - 结果超 100K 字符截断
    """
```

**支持的 transport**：stdio（本地进程）、http、sse。与 Claude Code 兼容但去掉了 ws-ide、sdk、claudeai-proxy 等 IDE 专用 transport。

### 7. Hooks / Harness Engineering (`hooks/`) -- 新增

**这是 Claude Code "harness engineering" 的核心**：通过声明式 hooks 在工具执行的关键节点注入自定义行为。

```python
# types.py
class HookEvent(str, Enum):
    TOOL_START = "tool_start"       # 工具执行前
    TOOL_COMPLETE = "tool_complete" # 工具执行后
    TOOL_ERROR = "tool_error"       # 工具出错时
    STOP = "stop"                   # agent 完成时
    SUBAGENT_STOP = "subagent_stop" # 子 agent 完成时

@dataclass
class Hook:
    type: Literal["command", "prompt", "http"]
    # command type: shell 命令
    command: str | None = None
    # prompt type: LLM prompt
    prompt: str | None = None
    # http type: webhook URL
    url: str | None = None
    headers: dict[str, str] | None = None
    # 通用字段
    if_condition: str | None = None   # "Bash(git *)" 匹配条件
    timeout: int = 30
    once: bool = False                # 执行一次后自动移除
    async_: bool = False              # 后台执行不阻塞

# engine.py
class HookEngine:
    """Hook 注册、匹配和执行引擎"""

    def register(self, event: HookEvent, matcher: str | None, hooks: list[Hook],
                 source: str = "settings", session_scoped: bool = False):
        """
        注册 hooks。来源：
        - settings.json 配置
        - skill frontmatter 的 hooks 字段
        - 代码内置 hooks
        """

    async def fire(self, event: HookEvent, tool_name: str = None,
                   tool_input: dict = None, result: ToolResult = None):
        """
        触发 hook：
        1. 按 event 类型过滤
        2. 按 if_condition 匹配工具名/输入
        3. 执行匹配到的 hooks（command/prompt/http）
        4. once=True 的 hook 执行后自动移除
        """

    def unregister_session(self, session_id: str):
        """清理 session 级 hooks（skill hooks 等）"""
```

**Harness Engineering 典型用法**：

```json
// .nanocc/settings.json
{
  "hooks": {
    "tool_complete": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "echo 'Tool completed: $TOOL_NAME'",
          "if": "Bash(npm test *)"
        }]
      }
    ],
    "stop": [
      {
        "hooks": [{
          "type": "prompt",
          "prompt": "Review all changes and ensure no security vulnerabilities"
        }]
      }
    ]
  }
}
```

**与 Claude Code 的对应**：
- 保留 `command`、`prompt`、`http` 三种 hook 类型
- 保留 `if` 条件匹配
- 保留 `once` 一次性 hook
- 保留 session-scoped 注册（skill hooks）
- 去掉 `agent` hook 类型（用 `prompt` 替代）

### 8. 上下文管理 (`compact/`)

Claude Code 7 层 -> nanocc 3 层：

| 层 | 功能 | 来源 |
|---|---|---|
| `tool_result_budget` | 超 30K 字符的工具结果截断/落盘 | CC Layer 1 |
| `micro_compact` | 旧 tool_result 替换为 `[trimmed]` | CC Layer 3 |
| `auto_compact` | 超阈值时 LLM 摘要整段对话 | CC Layer 5 |

**关键常量**（保持与 Claude Code 一致）：
- autocompact buffer: 13,000 tokens
- 摘要输出预留: 20,000 tokens
- post-compact 文件恢复: 最多 5 文件，50K tokens
- 连续失败熔断: 3 次

### 9. 记忆系统 (`memory/`) -- 增强

**长期记忆** (`memdir.py`)：
- `MEMORY.md` 索引（最多 200 行/25KB）+ 单独 topic 文件
- 4 种 memory 类型：user, feedback, project, reference
- 相关记忆检索：扫描 frontmatter -> LLM side-query 选 top 5 -> 注入上下文

**会话记忆** (`session_memory.py`)：
- 结构化工作笔记（Current State, Task, Files, Errors, Worklog）
- 触发阈值：10K token 初始化，5K token 增量，3+ tool calls

**Memory 抽取** (`extract.py`) -- 新增：
```python
async def extract_memories(messages: list[Message], provider: LLMProvider,
                           model: str, memory_dir: Path):
    """
    每轮结束后后台运行：
    1. fork 子 agent 分析当前轮的对话
    2. 识别值得长期保留的信息（user/feedback/project/reference）
    3. 写入对应 topic file 并更新 MEMORY.md 索引
    只允许使用 FileEdit + FileWrite 工具
    """
```

**Auto Dream** (`auto_dream.py`) -- 新增：
```python
class AutoDreamEngine:
    """离线 memory 蒸馏，复刻 Claude Code 的 autoDream"""

    MIN_HOURS_BETWEEN = 24       # 最少间隔
    MIN_SESSIONS_TRIGGER = 5     # 最少新 session 数

    async def maybe_consolidate(self):
        """
        门控检查 -> 获取 lock -> 执行三阶段蒸馏：
        Phase 1 (Orient): 读取现有 memory 结构
        Phase 2 (Gather): 从 transcript 日志中 grep 关键信号
        Phase 3 (Consolidate): LLM 归并、去重、更新 memory files

        关键约束：
        - transcript 是大 JSONL，只做窄搜索不全量读取
        - 相对日期必须转为绝对日期
        - 使用 file lock 防止多进程并发
        """

    async def _acquire_lock(self) -> bool:
        """文件锁，防止多个 session 同时 dream"""
```

**Daily Log Memory** (`daily_log.py`) -- 新增，Assistant 模式专用：
```python
class DailyLogMemory:
    """
    Assistant 模式下的 append-only 日志制 memory。
    复刻 Claude Code KAIROS 的 buildAssistantDailyLogPrompt()。

    普通模式：实时维护 MEMORY.md 索引 + topic files
    Assistant 模式：追加写入每日日志 → /dream 定期蒸馏

    路径结构：
      ~/.nanocc/memory/logs/
        2026/
          04/
            2026-04-01.md
            2026-04-02.md   ← 日期自动滚动
    """

    def get_log_path(self, date: date | None = None) -> Path:
        """logs/YYYY/MM/YYYY-MM-DD.md"""

    async def append(self, content: str):
        """追加写入今天的日志文件，不覆盖"""

    async def build_prompt(self) -> str:
        """
        构建 assistant 模式的 memory prompt：
        - 加载 MEMORY.md 作为蒸馏后的索引（只读，由 /dream 维护）
        - 加载今天的日志作为当前会话的记忆
        - 不直接编辑 MEMORY.md
        """
```

**Memory 模式切换逻辑**（在 `memdir.py` 中）：
```python
def get_memory_prompt(assistant_mode: bool) -> str:
    if assistant_mode:
        return daily_log.build_prompt()    # 日志制
    else:
        return memdir.build_memory_prompt() # 索引制
```

**CLAUDE.md** (`claude_md.py`)：
- 层级加载：~/.nanocc/CLAUDE.md -> 项目根 -> 当前目录

### 10. Assistant / Daemon 模式 (`assistant/`) -- 新增

**复刻 Claude Code KAIROS 的核心机制**：把 nanocc 从"你问我答"的 REPL 变成长驻后台的主动式助手。

#### 10.1 模式检测与 Session 持久化 (`mode.py`)

```python
class AssistantMode:
    """Assistant 模式的生命周期管理"""

    def __init__(self, state_dir: Path):
        self._state_dir = state_dir       # ~/.nanocc/sessions/
        self._active = False
        self._session_id: str | None = None

    def activate(self, session_id: str | None = None):
        """
        激活 assistant 模式：
        - 分配或恢复 session_id
        - 切换 memory 到日志制
        - 启动 proactive tick 循环
        - 注册 Brief 工具
        """
        self._active = True
        self._session_id = session_id or generate_session_id()
        self._save_pointer()  # 写入 bridge-pointer 以便 --continue 恢复

    def suspend(self):
        """
        挂起 session（不销毁）：
        - 序列化 mutableMessages 到 transcript 文件
        - 保存 session state (usage, memory path, cwd)
        - 停止 tick 循环
        """

    async def resume(self, session_id: str | None = None) -> SessionState:
        """
        恢复 session：
        - session_id=None 时从 bridge-pointer 读取最近 session
        - 反序列化 mutableMessages
        - 恢复 memory 状态
        - 重启 tick 循环
        """

    def _save_pointer(self):
        """写入 ~/.nanocc/bridge-pointer 记录当前 session"""

    def _load_pointer(self) -> str | None:
        """读取最近 session id"""
```

**启动方式**：
```bash
# 普通 REPL 模式（默认）
nanocc

# 进入 Assistant 模式
nanocc --assistant

# 恢复上次 session
nanocc --continue

# 恢复指定 session
nanocc --session-id abc123

# Assistant + Telegram 通道
nanocc --assistant --channel telegram --bot-token $TG_TOKEN
```

#### 10.2 Proactive 主动式工作 (`proactive.py`)

```python
class ProactiveEngine:
    """
    主动式工作引擎。复刻 KAIROS 的 tick 机制。

    核心思想：AI 不是被动等待用户输入，而是周期性被唤醒，
    自己判断是否有有用的事可做。
    """

    TICK_INTERVAL = 60  # 秒，可配置

    def __init__(self, engine: QueryEngine):
        self._engine = engine
        self._tick_task: asyncio.Task | None = None
        self._user_focused = True    # 用户是否在看终端

    async def start(self):
        """启动 tick 循环"""
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self):
        """停止 tick 循环"""
        if self._tick_task:
            self._tick_task.cancel()

    async def _tick_loop(self):
        """
        周期性发送 <tick> 信号给 agent：

        while True:
            await asyncio.sleep(TICK_INTERVAL)
            if engine 空闲:
                注入 <tick> 系统消息
                agent 决定是否有事可做：
                  - 有事 → 执行（检查任务、review PR、整理代码...）
                  - 没事 → 调用 Sleep 工具（不能空转）

        焦点感知：
          - 用户在看终端 → 协作模式，可以问问题
          - 用户不看 → 自主模式，只做低风险操作
        """

    def set_user_focus(self, focused: bool):
        """终端焦点状态变更"""
        self._user_focused = focused

# Sleep 工具
class SleepTool(Tool):
    """
    Proactive 模式专用。当 agent 被 tick 唤醒但没有有用的事可做时，
    必须调用此工具显式声明"我现在没事做"。

    防止 agent 空转消耗 token。
    """
    name = "Sleep"
    input_schema = {"duration": {"type": "integer", "description": "睡眠秒数"}}
    is_read_only = True

    async def execute(self, input, context):
        await asyncio.sleep(input["duration"])
        return ToolResult(content="Woke up")
```

#### 10.3 Brief 结构化消息 (`brief.py`)

```python
class BriefTool(Tool):
    """
    Assistant 模式的主要输出通道。
    不是直接流式输出文本，而是发送结构化消息。

    复刻 KAIROS 的 SendUserMessage。
    """
    name = "Brief"
    input_schema = {
        "message": {"type": "string", "description": "消息内容 (markdown)"},
        "attachments": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["normal", "proactive"]},
    }

    async def execute(self, input, context):
        """
        发送结构化消息：
        - CLI 模式：Rich 渲染到终端
        - Channel 模式：通过 channel.send_message() 发送
        - SDK 模式：yield 为 BriefEvent

        status="proactive" 时标记为主动通知，
        Channel 适配器可据此决定是否静默或加 badge。
        """
```

#### 10.4 Assistant 模式与现有模块的交互

```
普通 REPL 模式                     Assistant 模式
─────────────                     ──────────────
用户输入驱动                       用户输入 + tick 驱动
Memory: 索引制                     Memory: 日志制 + /dream 蒸馏
输出: 直接文本流                   输出: Brief 结构化消息
Session: 一次性                    Session: 可挂起/恢复
Auto Dream: 自动后台               Auto Dream: /dream skill 手动触发
query.py: 等 end_turn 结束         query.py: end_turn 后等待 tick 或用户

Engine 的区别：
  普通: submit_message() → query() → Terminal → 等用户
  Assistant: submit_message() → query() → Terminal → tick 唤醒 → query() → ...
```

**query.py 的变化**：
```python
# query.py 主循环增加 tick 处理
async def query(params: QueryParams) -> AsyncGenerator[...]:
    # ... 原有循环 ...

    # 新增：end_turn 后检查是否 assistant 模式
    if params.assistant_mode and terminal.reason == "completed":
        # 不直接 return，而是等待 tick 或新的用户输入
        next_input = await params.proactive_engine.wait_for_next()
        if next_input.type == "tick":
            state.messages.append(create_tick_message())
            continue  # 继续循环
        elif next_input.type == "user_message":
            state.messages.append(next_input.message)
            continue
        elif next_input.type == "shutdown":
            return Terminal(reason="completed")
```

### 11. 子 Agent (`agents/`)

**Fork 机制** (`fork.py`)：
- `CacheSafeParams`: 继承父 agent 的 system prompt/context/tool schema
- `create_subagent_context()`: 克隆 file state，新建 abort controller，隔离状态
- 同步子 agent（阻塞等待）和异步子 agent（`asyncio.Task`）

**Coordinator** (`coordinator.py`)：
- Dispatcher 分解任务，Workers 并发执行
- 读任务并行，写任务串行

### 12. Channel / IM 通道 (`channels/`) -- 新增，替代 Remote/Bridge

**设计理念**：Claude Code 的 Bridge/Remote 是为了远程控制 agent session。nanocc 把这个概念泛化为 **Channel**——任何消息收发通道都可以驱动 agent。

```python
# base.py
class Channel(Protocol):
    """消息通道抽象——任何能收发消息的东西"""

    async def start(self):
        """启动通道（监听消息）"""

    async def stop(self):
        """停止通道"""

    async def send_message(self, session_id: str, content: str,
                           attachments: list[str] | None = None):
        """向用户发送消息（支持 markdown、代码块）"""

    async def send_permission_request(self, session_id: str,
                                       tool_name: str, description: str) -> bool:
        """发送权限确认请求，等待用户回复"""

    def on_message(self, callback: Callable[[str, str], Awaitable[None]]):
        """注册消息回调 (session_id, message) -> None"""

# telegram.py
class TelegramChannel(Channel):
    """Telegram Bot 通道"""

    def __init__(self, bot_token: str, allowed_users: list[int] | None = None):
        self._bot = ...  # python-telegram-bot
        self._sessions: dict[int, QueryEngine] = {}  # chat_id -> engine

    async def start(self):
        """启动 polling / webhook"""

    async def _handle_message(self, update):
        """
        1. 从 update 获取 chat_id 和 text
        2. 获取或创建 QueryEngine session
        3. 调用 engine.submit_message(text)
        4. 流式发送回复（长消息分段、代码块格式化）
        """

    async def send_message(self, session_id, content, attachments=None):
        """
        发送消息到 Telegram：
        - Markdown 转 Telegram MarkdownV2
        - 长消息自动分段（4096 字符限制）
        - 代码块保持格式
        """

    async def send_permission_request(self, session_id, tool_name, description) -> bool:
        """
        发送 inline keyboard 请求确认：
        [✅ Allow] [❌ Deny] [🔓 Always Allow]
        等待用户点击回调
        """

# webhook.py
class WebhookChannel(Channel):
    """通用 Webhook 通道（Slack / Discord / 飞书 / 钉钉）"""

    def __init__(self, incoming_url: str, outgoing_secret: str,
                 adapter: str = "slack"):
        """
        adapter 决定消息格式转换：
        - "slack": Slack Block Kit
        - "discord": Discord embed
        - "feishu": 飞书卡片
        """

# websocket.py
class WebSocketChannel(Channel):
    """WebSocket 通道，用于 Web UI 或自定义前端"""

    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        协议格式（JSON）：
        -> { type: "message", session_id: "...", content: "..." }
        <- { type: "response", session_id: "...", content: "...", stream: true }
        <- { type: "permission_request", ... }
        -> { type: "permission_response", ... }
        """
```

**Channel vs Claude Code Bridge 的对比**：

| Claude Code Bridge | nanocc Channel |
|---|---|
| 专用 API endpoint + WebSocket | 泛化消息通道协议 |
| 只能通过 anthropic.com 中转 | 直接对接任意 IM |
| 复杂的 environment/work/secret 协议 | 简单的 message/permission 协议 |
| 固定 SDKMessage 格式 | 每个 channel adapter 自行转换 |

**Channel 启动方式**：
```bash
# 终端 CLI（默认）
nanocc

# Telegram Bot
nanocc --channel telegram --bot-token $TG_TOKEN

# WebSocket server
nanocc --channel websocket --port 8765

# 组合模式：CLI + Telegram 同时运行
nanocc --channel cli+telegram --bot-token $TG_TOKEN
```

### 13. CLI (`cli/`)

- `click` 做参数解析，增加 `--assistant`、`--continue`、`--session-id` 标志
- `rich` 做终端渲染：Markdown、语法高亮、diff、进度条
- REPL 模式 + 一次性模式 (`-p`) + Assistant 模式 (`--assistant`)
- 权限确认框 (y/n/always)
- Slash 命令：`/compact`, `/clear`, `/history`, `/cost`, `/model`, `/help`, `/dream`, `/brief`

### 14. SDK (`sdk.py`)

```python
# 有状态多轮
session = nanoccSession(config)
async for event in session.send("修复这个 bug"):
    print(event)

# 无状态一次性
result = await nanocc.query("解释这段代码", provider="anthropic")

# Assistant 模式（长驻后台）
session = nanoccSession(config, assistant=True)
await session.run_forever()  # tick 循环 + 等待消息

# Channel 驱动 + Assistant
channel = TelegramChannel(bot_token="...")
server = nanoccServer(config, channel, assistant=True)
await server.run()  # TG bot + proactive tick
```

---

## 功能取舍矩阵

| Claude Code 功能 | nanocc | 说明 |
|---|---|---|
| 异步 generator agent loop | **保留** | 核心架构 |
| QueryEngine 有状态会话 | **保留** | |
| 工具系统 (45+ 工具) | **精简** 为 12 个 | 核心工具 + Skill + Brief + Sleep + MCP 动态扩展 |
| 权限模型 (allow/deny/ask) | **保留** | |
| 并发工具执行 | **保留** | 读并行/写串行 |
| 7 层 compact 管线 | **精简** 为 3 层 | budget + micro + auto |
| MEMORY.md + topic files | **保留** | 同样的限制参数 |
| Session memory | **保留** | |
| Memory 抽取 | **保留** | 每轮后台 fork 子 agent 抽取 |
| Auto Dream | **保留** | 离线 memory 蒸馏，24h/5session 门控 |
| CLAUDE.md 层级 | **精简** | 启动时全量加载 |
| 子 agent fork | **保留** | CacheSafeParams |
| Coordinator 模式 | **保留** | |
| Git context 快照 | **保留** | |
| **Skill 系统** | **保留** | frontmatter + markdown prompt 展开器 |
| **MCP 集成** | **保留** | stdio/http/sse transport，工具/资源发现 |
| **Hooks / Harness** | **保留** | command/prompt/http 三种 hook，5 种事件 |
| **KAIROS / Assistant 模式** | **保留** | session 持久化、proactive tick、日志制 memory |
| **Brief / 结构化消息** | **保留** | Assistant 模式主输出通道 |
| **Proactive / tick 机制** | **保留** | 周期唤醒 + Sleep 工具 + 焦点感知 |
| **Daily Log Memory** | **保留** | append-only 日志 + /dream 蒸馏 |
| **Session 挂起/恢复** | **保留** | --continue / --session-id |
| **Remote/Bridge** | **替换** 为 Channel | Telegram/Webhook/WebSocket 通道 |
| 多级 abort | **精简** | 单 AbortController |
| StreamingToolExecutor | **去掉** | 等完整消息再执行 |
| Reactive compact | **去掉** | 返回 prompt_too_long |
| Context collapse | **去掉** | |
| Team memory | **去掉** | |
| 插件系统 | **去掉** | MCP + Skill + Hook 覆盖 |
| GitHub Webhooks | **去掉** | 通过 Channel webhook 替代 |
| SendUserFile | **去掉** | Brief attachments 覆盖 |

---

## 依赖

```toml
dependencies = [
    "anthropic>=0.40.0",         # Claude API
    "openai>=1.50.0",            # OpenAI 兼容
    "rich>=13.0",                # 终端 UI
    "click>=8.0",                # CLI 参数
    "tiktoken>=0.7.0",           # OpenAI token 计数
    "httpx>=0.27.0",             # Web fetch + MCP HTTP
    "pyyaml>=6.0",               # frontmatter/config 解析
    "mcp>=1.0.0",                # MCP SDK (stdio/sse transport)
]

[project.optional-dependencies]
telegram = ["python-telegram-bot>=21.0"]
websocket = ["websockets>=12.0"]
all = ["python-telegram-bot>=21.0", "websockets>=12.0"]
```

---

## 实现顺序 (10 个阶段)

### Phase 1: 基础 (types + Provider + 最小 loop) ~1,500 行
- `types.py`, `constants.py`, `messages.py`
- `providers/base.py`, `providers/anthropic.py`, `providers/registry.py`
- `utils/abort.py`
- 最小 `query.py`（无工具，只处理流式文本）
- **里程碑**: 能和 Claude API 流式对话

### Phase 2: 工具系统 ~1,200 行
- `tools/base.py`, `tools/orchestration.py`, `tools/registry.py`
- 6 个基础工具: bash, file_read, file_write, file_edit, glob, grep
- 工具执行接入 `query.py`
- **里程碑**: 完整 agent loop 能调用工具

### Phase 3: 上下文管理 ~800 行
- `compact/` 全部 4 个模块
- `context.py`, `utils/git.py`, `utils/tokens.py`
- compact 管线接入 `query.py`
- **里程碑**: 长对话自动 compact

### Phase 4: Engine + 记忆 ~1,400 行
- `engine.py`（含 session 挂起/恢复）
- `memory/` 6 个模块 (memdir, session_memory, claude_md, extract, auto_dream, daily_log)
- `utils/config.py`, `utils/session_storage.py`
- **里程碑**: 有状态多轮会话 + 记忆持久化 + auto dream + daily log

### Phase 5: Hooks + Skills + MCP ~1,300 行
- `hooks/` 3 个模块 (types, engine, builtins)
- `skills/` 3 个模块 (loader, executor, bundled/)
- `mcp/` 3 个模块 (client, config, tool_wrapper)
- `tools/skill_tool.py`
- Hook 触发点接入 `query.py`
- **里程碑**: skill 可用，MCP server 工具可调用，hooks 能触发

### Phase 6: 子 Agent ~500 行
- `agents/fork.py`, `agents/coordinator.py`
- `tools/agent_tool.py`, `tools/ask_user.py`, `tools/web_fetch.py`
- **里程碑**: 能启动子 agent 并行工作

### Phase 7: Assistant / KAIROS 模式 ~520 行
- `assistant/mode.py`（模式检测、session 持久化、--continue 恢复）
- `assistant/proactive.py`（tick 循环、Sleep 工具、焦点感知）
- `assistant/brief.py`（Brief 结构化消息工具）
- `query.py` 增加 tick 处理分支
- `engine.py` 增加 `suspend()` / `resume()` 方法
- memory 模块增加日志制/索引制模式切换
- **里程碑**: `nanocc --assistant` 能启动长驻模式；`nanocc --continue` 能恢复 session

### Phase 8: CLI / 终端 UI ~1,000 行
- `cli/` 全部 4 个模块
- CLI 参数增加 `--assistant`, `--continue`, `--session-id`
- **里程碑**: 完整交互式 CLI + Assistant 模式 UI

### Phase 9: Channel / IM 通道 ~700 行
- `channels/base.py`, `channels/telegram.py`
- `channels/webhook.py`, `channels/websocket.py`
- CLI 增加 `--channel` 参数
- Channel + Assistant 组合模式
- **里程碑**: `nanocc --assistant --channel telegram` 可运行主动式 TG bot

### Phase 10: SDK + OpenAI Provider + 打包 ~600 行
- `sdk.py`（含 `run_forever()` assistant API）
- `providers/openai_compat.py`
- `__init__.py`, `__main__.py`, `pyproject.toml`
- `utils/cost.py`
- **里程碑**: pip install 可用

---

## 验证方式

1. **Phase 1**: `python -m nanocc -p "你好"` 能流式输出
2. **Phase 2**: `python -m nanocc -p "读取 README.md 并总结"` 能调用 FileRead
3. **Phase 3**: 超长对话验证 autocompact 触发
4. **Phase 4**: 连续两次启动验证 memory 持久化；auto_dream 门控检查；daily_log 追加写入
5. **Phase 5**: `/commit` skill 可用；MCP server 工具能调用；settings.json hooks 触发
6. **Phase 6**: "并行搜索三个目录的 TODO" 能启动子 agent
7. **Phase 7**: `nanocc --assistant` 启动后 tick 唤醒；Brief 消息输出；`--continue` 恢复上次 session；memory 自动切换为日志制
8. **Phase 8**: 交互式 REPL 全功能
9. **Phase 9**: `nanocc --assistant --channel telegram` TG bot 主动通知 + 权限确认
10. **Phase 10**: `pip install .` + `nanocc` 命令 + `import nanocc` SDK + `session.run_forever()`

---

## 架构图

```
                    ┌───────────────────────────────────────┐
                    │           入口层 (Entrypoints)         │
                    │  CLI(REPL) │ Channel(TG/WS) │ SDK     │
                    │            │                │         │
                    │  --assistant / --continue 切换模式     │
                    └──────┬─────┴───────┬────────┴────┬───┘
                           │             │             │
                    ┌──────▼─────────────▼─────────────▼───┐
                    │        QueryEngine (engine.py)         │
                    │   mutableMessages / abort / usage      │
                    │   suspend() / resume() session 持久化  │
                    └──────────────┬────────────────────────┘
                                   │
         ┌─────────────────────────▼─────────────────────────────┐
         │              Agent Loop (query.py)                     │
         │           AsyncGenerator 状态机                       │
         │                                                       │
         │  ┌─────────────────────────────────────────────┐      │
         │  │ 上下文治理管线                               │      │
         │  │ budget → micro → auto_compact               │      │
         │  └─────────────────────────────────────────────┘      │
         │                    ↓                                   │
         │  ┌─────────────────────────────────────────────┐      │
         │  │ LLM Provider.stream()                       │      │
         │  │ (Anthropic / OpenAI / ...)                   │      │
         │  └─────────────────────────────────────────────┘      │
         │                    ↓                                   │
         │  ┌─────────────────────────────────────────────┐      │
         │  │ Tool Orchestration                          │      │
         │  │ ┌── hook:tool_start ──┐                     │      │
         │  │ │  execute_tools()    │                     │      │
         │  │ └── hook:tool_complete ┘                    │      │
         │  └─────────────────────────────────────────────┘      │
         │                    ↓                                   │
         │  hook:stop → memory_extract                           │
         │                    ↓                                   │
         │  ┌─────────────────────────────────────────────┐      │
         │  │ Assistant 模式分支                           │      │
         │  │ end_turn 后不退出，等待：                    │      │
         │  │   ← tick (ProactiveEngine 周期唤醒)         │      │
         │  │   ← 用户新消息                              │      │
         │  │   ← shutdown 信号                           │      │
         │  │ 输出通过 Brief 工具结构化发送                │      │
         │  └─────────────────────────────────────────────┘      │
         └───────────────────────────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
    ┌─────────▼──────┐  ┌────────▼────────┐   ┌───────▼───────┐
    │ Tools (12个)    │  │  Skills (.md)   │   │  MCP Servers  │
    │ Bash/File/Grep  │  │ commit/review   │   │ 外部工具/资源  │
    │ Brief/Sleep/... │  │ dream/...       │   │               │
    └────────────────┘  └─────────────────┘   └───────────────┘
              │
    ┌─────────▼──────────────────────────────────────────────┐
    │                   Memory 系统                           │
    │                                                        │
    │  ┌──────────────────┐    ┌──────────────────────┐      │
    │  │  REPL 模式        │    │  Assistant 模式       │      │
    │  │  (索引制)         │    │  (日志制)             │      │
    │  │                  │    │                      │      │
    │  │  MEMORY.md 索引   │    │  logs/YYYY/MM/DD.md  │      │
    │  │  ↕ 实时维护      │    │  ↓ append-only       │      │
    │  │  topic files     │    │  /dream 定期蒸馏      │      │
    │  │                  │    │  → MEMORY.md + topics │      │
    │  └──────────────────┘    └──────────────────────┘      │
    │                                                        │
    │  Session Memory → 结构化笔记 (两种模式共用)             │
    │  Extract → 每轮后台抽取 (两种模式共用)                  │
    │  Auto Dream → 离线蒸馏 (REPL 自动 / Assistant /dream)  │
    └────────────────────────────────────────────────────────┘
```

---

## 两种运行模式对比

```
┌─────────────────────────────────────────────────────────────┐
│                    REPL 模式（默认）                          │
│                                                             │
│  nanocc                                                   │
│  ├── 用户输入驱动                                            │
│  ├── Memory: 索引制（实时维护 MEMORY.md）                    │
│  ├── Auto Dream: 后台自动（24h + 5session 门控）             │
│  ├── 输出: 直接流式文本                                      │
│  └── Session: 一次性，退出即结束                             │
│                                                             │
│  适合：日常编码、调试、问答                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Assistant 模式                            │
│                                                             │
│  nanocc --assistant [--channel telegram]                   │
│  ├── 用户输入 + tick 周期唤醒 双驱动                         │
│  ├── Memory: 日志制（append-only → /dream 蒸馏）             │
│  ├── Auto Dream: 手动 /dream（日志量大，不适合全自动）        │
│  ├── 输出: Brief 结构化消息（可推送到 IM）                   │
│  ├── Session: 可挂起/恢复（--continue / --session-id）       │
│  └── Proactive: 空闲时自主检查任务、review 代码             │
│                                                             │
│  适合：长驻后台助手、IM bot、CI/CD 集成、团队 agent          │
└─────────────────────────────────────────────────────────────┘
```
