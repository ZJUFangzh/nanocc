"""Usage and cost tracking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UsageTracker:
    """Tracks cumulative API usage across turns."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    api_calls: int = 0

    def add(self, input_tokens: int = 0, output_tokens: int = 0,
            cache_creation: int = 0, cache_read: int = 0) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cache_creation_tokens += cache_creation
        self.total_cache_read_tokens += cache_read
        self.api_calls += 1

    @property
    def total_tokens(self) -> int:
        return (self.total_input_tokens + self.total_output_tokens
                + self.total_cache_creation_tokens + self.total_cache_read_tokens)

    def summary(self) -> str:
        return (f"Tokens: {self.total_tokens:,} "
                f"(in={self.total_input_tokens:,} out={self.total_output_tokens:,} "
                f"cache_create={self.total_cache_creation_tokens:,} "
                f"cache_read={self.total_cache_read_tokens:,}) "
                f"API calls: {self.api_calls}")
