# nanocc

Python Nano Claude Code — Agent SDK + CLI.

基于 Claude Code 2.1.88 源码的 Python 精简复刻，目标 ~10,000 行。

## 快速开始

```bash
# 安装
uv sync

# 单轮对话
uv run nanocc -p "hello" --api-key $OPENROUTER_API_KEY -m moonshotai/kimi-k2.5

# 交互式 REPL
uv run nanocc --api-key $OPENROUTER_API_KEY -m moonshotai/kimi-k2.5

# 指定 provider
uv run nanocc --provider anthropic --api-key $ANTHROPIC_API_KEY
```

## 支持的 Provider

| Provider | 环境变量 | 模型格式 |
|---|---|---|
| openrouter (默认) | `OPENROUTER_API_KEY` | `provider/model` |
| anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| openai | `OPENAI_API_KEY` | `gpt-4o` |
| together | `TOGETHER_API_KEY` | `meta-llama/...` |
| groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

## 内置工具

Bash, Read, Write, Edit, Glob, Grep — 读工具并行执行，写工具串行执行。

## 开发状态

Phase 1-2 已完成（基础 + 工具系统），详见 [docs/progress.md](docs/progress.md)。
