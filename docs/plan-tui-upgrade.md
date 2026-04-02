# Plan: Phase 8 TUI 升级 — Rich REPL → Textual Chat UI

## 目标

把当前的 Rich readline REPL 替换为 Textual 驱动的现代 chat-style TUI：
- 输入框固定底部，消息区往上滚动（like OpenCode / modern chat）
- 流式 Markdown 渲染
- 工具调用/结果结构化展示
- 键盘快捷键 + slash 命令

## 技术选型变更

```
Before: click + rich (Console.input + Live)
After:  click + textual (App + widgets)
```

Textual 是 Rich 同一团队（Textualize）出品，底层复用 Rich 渲染，不冲突。
click 仍然负责参数解析和 one-shot 模式，Textual 只接管 REPL 交互模式。

## 依赖变更

```toml
# pyproject.toml
dependencies = [
    # 新增
    "textual>=1.0.0",
    # rich 保留（textual 依赖它，且 one-shot 模式继续用）
]
```

---

## 文件规划

```
src/nanocc/cli/
├── app.py              (150)  -- click CLI 入口（保留），启动 TUI 或 one-shot
├── tui.py              (350)  -- Textual App 主体 + 布局 + 事件循环
├── widgets.py          (250)  -- 自定义 widget：UserMessage, AssistantMessage, ToolCall, ToolResult
├── commands.py         (150)  -- slash 命令处理 (/exit, /clear, /compact, /model, /help, /cost)
└── permissions_ui.py   (100)  -- 权限确认（Textual modal dialog）
```

总计 ~1,000 行，与 structure.md Phase 8 预估一致。

---

## 架构设计

### 整体布局

```
┌─────────────────────────────────────────────┐
│  Header: nanocc (model_name) [$cost]        │  ← Textual Header
├─────────────────────────────────────────────┤
│                                             │
│  [User] 读取 README.md 并总结                │  ← UserMessage widget
│                                             │
│  [Tool] FileRead(README.md)                 │  ← ToolCallWidget
│  │ # nanocc                                 │
│  │ Python Nano Claude Code...               │  ← ToolResultWidget (折叠)
│                                             │
│  [Assistant]                                │  ← AssistantMessage widget
│  这是一个 Python 精简复刻项目，主要功能...    │    (Markdown 渲染，流式更新)
│                                             │
│  ▼ 消息区 VerticalScroll (往上滚)            │
├─────────────────────────────────────────────┤
│  > 输入你的消息...                    [Enter] │  ← Input widget (dock: bottom)
├─────────────────────────────────────────────┤
│  ^C Abort  ^L Clear  /help Commands         │  ← Textual Footer
└─────────────────────────────────────────────┘
```

### 数据流

```
Input.Submitted
    ↓
NanoccApp.on_input_submitted()
    ├── slash command → commands.py 处理
    └── user message →
        ├── mount UserMessage widget
        ├── mount AssistantMessage widget (空)
        └── @work() async worker:
              ├── 构建 QueryParams
              ├── async for event in query(params):
              │   ├── StreamEvent(text_delta) → response.update(accumulated_text)
              │   ├── AssistantMessage(tool_use) → mount ToolCallWidget
              │   ├── ToolResultBlock → mount ToolResultWidget
              │   └── Terminal → 结束
              └── response.anchor() 保持滚动到底部
```

### 与现有 query loop 的集成

**不改 query.py**。TUI 层只是 `async for event in query(params)` 的另一个消费者：

```python
# tui.py 核心循环
@work()
async def _run_query(self, user_input: str) -> None:
    chat = self.query_one("#chat-view", VerticalScroll)

    # 1. 挂载用户消息
    await chat.mount(UserMessage(user_input))

    # 2. 创建空的 assistant 响应 widget
    response = AssistantResponse()
    await chat.mount(response)
    response.anchor()

    # 3. 构建 QueryParams（与现有 _stream_loop 相同）
    self.all_messages.append(create_user_message(user_input))
    params = self._build_params()

    # 4. 消费 query() 事件流
    collected_text = ""
    async for event in query(params):
        if isinstance(event, StreamEvent) and event.type == CONTENT_BLOCK_DELTA:
            collected_text += event.delta.get("text", "")
            response.update(collected_text)          # Markdown 实时更新

        elif isinstance(event, AssistantMessage):
            # 处理 tool_use blocks
            for block in event.content:
                if isinstance(block, ToolUseBlock):
                    tool_widget = ToolCallWidget(block.name, block.input)
                    await chat.mount(tool_widget)
            # 重置 collected_text，准备下一段文本
            collected_text = ""
            response = AssistantResponse()
            await chat.mount(response)
            response.anchor()

        elif isinstance(event, ToolResultBlock):
            result_widget = ToolResultWidget(block=event)
            await chat.mount(result_widget)

        elif isinstance(event, Terminal):
            if event.reason == TerminalReason.MODEL_ERROR:
                self.notify(f"Error: {event.error}", severity="error")
            break

    # 5. 聚焦输入框
    self.query_one("#input", Input).focus()
```

---

## 自定义 Widgets 设计

### widgets.py

```python
class UserMessage(Static):
    """用户输入消息。"""
    DEFAULT_CSS = """
    UserMessage {
        background: $surface;
        padding: 0 1;
        margin: 0 0 1 0;
        border-left: thick $success;
    }
    """

class AssistantResponse(Markdown):
    """AI 回复，支持流式 Markdown 更新。"""
    DEFAULT_CSS = """
    AssistantResponse {
        padding: 0 1;
        margin: 0 0 1 0;
        border-left: thick $primary;
    }
    """

class ToolCallWidget(Static):
    """工具调用摘要行。如：Tool: FileRead(README.md)"""
    DEFAULT_CSS = """
    ToolCallWidget {
        color: $warning;
        padding: 0 1;
    }
    """

class ToolResultWidget(Static):
    """工具结果，默认折叠，点击展开。"""
    # 默认只显示前 3 行 + "... (click to expand)"
    DEFAULT_CSS = """
    ToolResultWidget {
        color: $text-muted;
        padding: 0 1 0 3;
        margin: 0 0 1 0;
    }
    """
```

---

## Slash 命令

### commands.py

```python
COMMANDS = {
    "/exit":    "退出",
    "/quit":    "退出",
    "/clear":   "清空对话",
    "/compact": "手动触发 compact",
    "/model":   "显示/切换模型",
    "/cost":    "显示 token 用量",
    "/help":    "显示帮助",
}

async def handle_command(app: NanoccApp, cmd: str) -> bool:
    """处理 slash 命令，返回 True 表示已处理。"""
    ...
```

---

## 键盘快捷键

```python
class NanoccApp(App):
    BINDINGS = [
        Binding("ctrl+c",      "abort",       "Abort",     show=True),
        Binding("ctrl+l",      "clear_chat",  "Clear",     show=True),
        Binding("ctrl+d",      "quit",        "Quit",      show=True),
        Binding("escape",      "cancel",      "Cancel",    show=False),
    ]
```

- `Ctrl+C` — 中断当前请求（调用 `abort_controller.abort()` + 取消 worker）
- `Ctrl+L` — 清空消息区
- `Ctrl+D` — 退出
- `Escape` — 取消当前输入

---

## 权限确认

### permissions_ui.py

工具执行前如果需要确认（write/bash），弹出 Textual modal：

```
┌─── Permission Required ────────────┐
│                                    │
│  BashTool wants to run:            │
│  > rm -rf node_modules             │
│                                    │
│  [Y] Allow  [N] Deny  [A] Always  │
└────────────────────────────────────┘
```

用 Textual 的 `Screen.push_screen()` + `ModalScreen` 实现。

---

## app.py 改造

```python
@click.command()
@click.option("-p", "--prompt", ...)
@click.option("-m", "--model", ...)
# ... 其他参数不变
def main(prompt, model, system, provider, api_key):
    if prompt:
        # one-shot 模式：保持 Rich Console 输出（不启动 TUI）
        asyncio.run(run_query(prompt, model, system, provider, api_key))
    else:
        # REPL 模式：启动 Textual App
        app = NanoccApp(model=model, system=system, provider=provider, api_key=api_key)
        app.run()
```

**关键**：one-shot (`-p`) 模式不用 Textual，保持当前 Rich 输出即可。只有交互模式才启动 TUI。

---

## 实现步骤

### Step 1: 基础骨架
1. `pyproject.toml` 添加 `textual` 依赖
2. 创建 `tui.py`：NanoccApp 类 + 基本布局（Header + VerticalScroll + Input + Footer）
3. `app.py` 改造：REPL 分支启动 `NanoccApp.run()`
4. **验证**：`uv run nanocc` 能启动 TUI，输入回显

### Step 2: 消息 Widget + 流式渲染
1. 创建 `widgets.py`：UserMessage, AssistantResponse, ToolCallWidget, ToolResultWidget
2. `tui.py` 实现 `_run_query()` worker：消费 `query()` 事件流，挂载 widget
3. 流式文本：`AssistantResponse.update(accumulated_text)` 实时更新 Markdown
4. **验证**：输入消息能流式渲染 AI 回复 + 工具调用展示

### Step 3: Slash 命令 + 快捷键
1. 创建 `commands.py`：`/exit`, `/clear`, `/compact`, `/model`, `/cost`, `/help`
2. `tui.py` 绑定快捷键：Ctrl+C abort, Ctrl+L clear, Ctrl+D quit
3. **验证**：`/clear` 清空，Ctrl+C 中断请求

### Step 4: 权限确认 + 打磨
1. 创建 `permissions_ui.py`：ModalScreen 权限确认框
2. ToolResultWidget 折叠/展开
3. Header 显示模型名 + token cost
4. CSS 细调：间距、颜色、边框
5. **验证**：Bash 工具触发权限确认弹窗

---

## structure.md 需要更新的部分

Phase 8 描述改为：

```
### Phase 8: CLI / 终端 UI ~1,000 行
- `cli/app.py` — click 入口，one-shot 保持 Rich，REPL 启动 Textual App
- `cli/tui.py` — Textual App 主体：chat 布局 + query() 事件消费 + worker
- `cli/widgets.py` — 自定义 widget（UserMessage, AssistantResponse, ToolCall, ToolResult）
- `cli/commands.py` — slash 命令处理
- `cli/permissions_ui.py` — Textual ModalScreen 权限确认
- 依赖新增：textual>=1.0.0
- **里程碑**: 现代 chat-style TUI，输入框固定底部，消息往上滚动
```

依赖列表新增 `textual>=1.0.0`。

---

## 风险 & 注意

1. **Textual 与 asyncio**：Textual 有自己的 event loop，`query()` 的 async generator 需要在 `@work()` async worker 中运行，通过 widget 方法更新 UI — 不需要 `call_from_thread`（async worker 直接在 event loop 中）
2. **one-shot 模式不受影响**：`-p` 参数走现有 Rich 路径，不启动 Textual
3. **query.py 零改动**：TUI 只是事件流的消费端
4. **Textual 版本**：锁定 `>=1.0.0`，API 已稳定
5. **终端兼容性**：Textual 需要现代终端（iTerm2, kitty, Windows Terminal 等），基本都支持
