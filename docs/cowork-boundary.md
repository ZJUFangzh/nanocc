# nanocc ↔ cowork 边界文档

本文档说明 nanocc（agent runtime）与 cowork（桌面 AI 助理产品）之间的职责边界，
以及 cowork 如何作为消费者使用 nanocc 提供的接口。

---

## 一句话边界

- **nanocc**：单个 agent 怎么运行（query loop、tools、memory、context、单 session 状态）
- **cowork**：多个 agent 怎么管（多 session 编排、IM 接入、用户认证、远程控制、桌面 UI）

---

## nanocc 暴露给 cowork 的 API

### 1. QueryEngine — 单个有状态会话

```python
from nanocc import QueryEngine
from nanocc.engine import QueryEngineConfig
from nanocc.providers.registry import create_provider

config = QueryEngineConfig(
    provider=create_provider("openrouter", api_key="sk-..."),
    model="qwen/qwen3.5-flash-02-23",
    cwd="/Users/x/projects/my-project",
    assistant_mode=False,  # cowork 启用时设为 True
)
engine = QueryEngine(config)

# 提交消息，流式接收事件
async for event in engine.submit_message("帮我跑测试"):
    # event 可能是 StreamEvent / Message / Terminal
    yield_to_client(event)

# 持久化
state = engine.get_state()       # 序列化为 dict
engine.save_session()              # 增量写 transcript + state.json + meta.json

# 恢复
engine.restore_state(state)
```

### 2. ProactiveEngine — Assistant 模式的 tick 机制

```python
from nanocc.assistant.proactive import ProactiveEngine, WakeReason

proactive = ProactiveEngine(tick_interval=120)
await proactive.start()

# cowork 注入到 engine
engine.proactive_engine = proactive
engine.config.assistant_mode = True

# query loop 在 end_turn 后会调 wait_for_next() 阻塞等待
# cowork 可以从外部注入消息
proactive.send_user_message(user_msg)

# 或请求关闭
proactive.request_shutdown()
```

### 3. BriefTool / SleepTool — Assistant 模式工具

这两个工具不在默认 registry 中。cowork 启用 assistant 模式时手动追加：

```python
from nanocc.assistant.brief import BriefTool, SleepTool

engine.tools.extend([BriefTool(), SleepTool()])
```

BriefTool 通过 `tool_use_context.options["brief_handler"]` 注入回调：

```python
async def brief_handler(message: str, status: str) -> None:
    """status: 'normal' | 'proactive'"""
    if status == "proactive":
        # 主动通知，cowork 推送到 IM 或桌面通知
        await telegram.send_notification(message)
    else:
        await telegram.send_message(message)

# 注入到 engine 的 tool_use_context.options
# (cowork 自己 wrap engine.submit_message 时设置)
```

### 4. session_storage — 持久化实现

```python
from nanocc.utils.session_storage import (
    list_sessions,
    load_session_state,
    load_transcript_after_boundary,
    save_session_state,
    save_meta,
)

# cowork SessionManager 直接调用这些函数
sessions = list_sessions(cwd="/path/to/project")
state = load_session_state(session_id)
```

### 5. 配置和工具

```python
from nanocc.tools.registry import get_all_tools  # 10 个核心工具
from nanocc.utils.config import load_settings    # settings.json 加载
```

---

## cowork 需要自己实现的部分

### 1. SessionManager — 替代 nanocc 已删除的 AssistantMode

```python
class SessionManager:
    """管理多个 nanocc QueryEngine 实例"""
    
    engines: dict[str, QueryEngine]        # name → engine
    proactives: dict[str, ProactiveEngine] # name → proactive
    bindings: dict[str, str]               # channel_id → session_name
    
    def create_session(name, cwd, assistant_mode=False) -> QueryEngine:
        """新建一个 engine 实例，可选启用 assistant 模式"""
    
    def get_session(name) -> QueryEngine: ...
    def delete_session(name): ...
    def list_sessions() -> list[SessionInfo]: ...
    
    def suspend(name):
        """engine.save_session() + 停止 proactive"""
    
    def resume(name) -> QueryEngine:
        """从 session_storage 恢复 engine.restore_state()"""
    
    def bind(channel_id, session_name):
        """把 IM channel 绑定到 session"""
    
    def switch(channel_id, session_name):
        """切换 channel 当前活跃 session"""
    
    async def route_message(channel_id, message):
        """消息路由：channel_id → session → engine.submit_message()"""
```

### 2. Channel Protocol — IM/Web 通道抽象

```python
from typing import Protocol, Callable, Awaitable

class Channel(Protocol):
    """所有消息收发通道的抽象接口"""
    
    async def start(self): ...
    async def stop(self): ...
    
    async def send_message(self, channel_id: str, content: str,
                           attachments: list[str] | None = None): ...
    
    async def send_permission_request(self, channel_id: str,
                                       tool_name: str, description: str) -> bool: ...
    
    def on_message(self, callback: Callable[[str, str], Awaitable[None]]):
        """注册消息回调 (channel_id, message)"""
```

### 3. Channel 实现

- `TelegramChannel`：python-telegram-bot，handle 长消息分段、inline keyboard 权限确认
- `SlackChannel`：slack_sdk，处理 Block Kit 格式
- `FeishuChannel`：飞书卡片
- `WebSocketChannel`：给桌面 React 前端用

### 4. 桌面应用（Tauri + React）

```
desktop/
├── src-tauri/                  # Rust 壳
│   ├── main.rs                 # 启动 cowork-server (Python subprocess)
│   ├── tray.rs                 # 系统托盘
│   └── tauri.conf.json
│
└── src/                        # React 前端
    ├── App.tsx
    ├── components/
    │   ├── ChatPanel.tsx       # 对话界面
    │   ├── SessionSidebar.tsx  # 项目切换
    │   ├── TerminalPanel.tsx   # xterm.js
    │   ├── ToolCallCard.tsx    # 工具调用展示
    │   ├── PermissionDialog.tsx# 权限确认弹窗
    │   └── SettingsPanel.tsx
    ├── hooks/
    │   └── useWebSocket.ts     # WS 连接 + 重连
    └── stores/
        └── sessionStore.ts     # Zustand 全局状态
```

### 5. cowork-server (FastAPI)

```
cowork/
├── pyproject.toml              # 依赖 nanocc
├── src/cowork/
│   ├── server.py               # FastAPI 入口 + uvicorn
│   ├── session_manager.py      # 上文 SessionManager
│   ├── ws_handler.py           # WebSocket 协议处理
│   ├── api/
│   │   ├── sessions.py         # REST: list/create/switch/delete
│   │   ├── skills.py           # REST: install/list/remove
│   │   └── settings.py
│   ├── channels/
│   │   ├── base.py
│   │   ├── telegram.py
│   │   ├── slack.py
│   │   └── router.py
│   └── auth.py
```

---

## WebSocket 协议（参考）

cowork 在 server 层定义统一的 WebSocket 协议，Tauri 前端、移动 PWA、Telegram 适配器都按这个协议交互。

```typescript
// 客户端 → 服务端
{ type: "message",  session: "proj-a", content: "..." }
{ type: "switch",   session: "proj-b" }
{ type: "create",   session: "proj-c", cwd: "/path/to/project" }
{ type: "abort" }
{ type: "permission_response", request_id: "...", allow: true }

// 服务端 → 客户端
{ type: "text_delta",   session: "proj-a", content: "..." }
{ type: "tool_use",     session: "proj-a", tool: "Bash", input: {...} }
{ type: "tool_result",  session: "proj-a", tool: "Bash", output: "..." }
{ type: "terminal",     session: "proj-a", reason: "completed" }
{ type: "permission_request", request_id: "...", tool: "FileWrite", description: "..." }
{ type: "session_list", sessions: [...] }
```

---

## 完整调用链：手机 → 桌面 nanocc

```
手机 Telegram
  │  "帮我在 nanocc 项目里跑测试"
  ▼
Telegram Bot (cowork channels/telegram.py)
  │  on_message(chat_id="tg:12345", text)
  ▼
SessionManager.route_message("tg:12345", text)
  │  active_session["tg:12345"] = "proj-nanocc"
  │  engine = engines["proj-nanocc"]
  ▼
nanocc QueryEngine (cwd=/Users/x/projects/nanocc)
  │  engine.submit_message(text)
  ▼
nanocc query() agent loop
  │  → BashTool: "uv run pytest tests/ -v"
  │  → 流式输出
  ▼
SessionManager 收集回复
  ▼
TelegramChannel.send_message("tg:12345", reply)
  │  分段、Markdown 转换
  ▼
手机收到测试结果
```

---

## 不变契约

cowork 依赖以下 nanocc API 的稳定性：

| API | 用途 |
|---|---|
| `QueryEngine(config)` | 实例化引擎 |
| `engine.submit_message(prompt)` | 提交消息，返回事件流 |
| `engine.get_state()` / `restore_state(state)` | 序列化 / 反序列化 |
| `engine.save_session()` | 持久化到磁盘 |
| `engine.abort()` | 中止当前轮 |
| `ProactiveEngine` 类（start/stop/wait_for_next/send_user_message/request_shutdown） | tick 机制 |
| `BriefTool`, `SleepTool` 类 | assistant 模式工具 |
| `session_storage` 模块 | 持久化辅助函数 |
| `tool_use_context.options["brief_handler"]` | 消息路由回调点 |

修改这些 API 需要同步更新 cowork。
