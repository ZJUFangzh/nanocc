"""Constants and thresholds — kept consistent with Claude Code 2.1.88."""

# ── Token Thresholds ────────────────────────────────────────────────────────

# Auto compact triggers when remaining tokens < buffer
AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000

# Post-compact file recovery
POST_COMPACT_MAX_FILES = 5
POST_COMPACT_MAX_TOKENS = 50_000

# Compact circuit breaker
COMPACT_MAX_CONSECUTIVE_FAILURES = 3

# ── Tool Limits ─────────────────────────────────────────────────────────────

DEFAULT_MAX_RESULT_SIZE_CHARS = 50_000
MAX_TOOL_RESULT_TOKENS = 100_000
BYTES_PER_TOKEN = 4
MAX_TOOL_RESULT_BYTES = 400_000
MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 200_000
TOOL_SUMMARY_MAX_LENGTH = 50
TOOL_TOKEN_COUNT_OVERHEAD = 500

# Concurrency
MAX_TOOL_CONCURRENCY = 10
SUBAGENT_TIMEOUT_SECONDS = 300  # 5 minutes per sub-agent turn

# Bash tool
BASH_MAX_OUTPUT_UPPER_LIMIT = 150_000
BASH_DEFAULT_TIMEOUT_MS = 120_000  # 2 minutes

# ── Context Window ──────────────────────────────────────────────────────────

CAPPED_DEFAULT_MAX_TOKENS = 8_000
ESCALATED_MAX_TOKENS = 64_000
COMPACT_MAX_OUTPUT_TOKENS = 20_000

# Context windows by model family
CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-haiku-4": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000

# ── Default Models ──────────────────────────────────────────────────────────

DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"
DEFAULT_SMALL_MODEL = "anthropic/claude-haiku-4-5-20251001"

# ── Session / Memory ───────────────────────────────────────────────────────

MEMORY_INDEX_MAX_LINES = 200
MEMORY_INDEX_MAX_BYTES = 25_000
SESSION_MEMORY_INIT_THRESHOLD_TOKENS = 10_000
SESSION_MEMORY_UPDATE_THRESHOLD_TOKENS = 5_000
SESSION_MEMORY_MIN_TOOL_CALLS = 3

# Auto Dream
AUTO_DREAM_MIN_HOURS_BETWEEN = 24
AUTO_DREAM_MIN_SESSIONS_TRIGGER = 5

# ── MCP ─────────────────────────────────────────────────────────────────────

MCP_TOKEN_COUNT_THRESHOLD_FACTOR = 0.5
MCP_MAX_RESULT_CHARS = 100_000

# ── Image ───────────────────────────────────────────────────────────────────

IMAGE_TOKEN_ESTIMATE = 1_600

# ── Hook Events ─────────────────────────────────────────────────────────────

HOOK_DEFAULT_TIMEOUT = 30
