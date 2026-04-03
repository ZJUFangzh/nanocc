"""Provider factory — create LLM providers by name."""

from __future__ import annotations

from typing import Any

from nanocc.providers.base import LLMProvider

# Well-known OpenAI-compatible base URLs
_OPENAI_COMPAT_URLS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
}


def create_provider(name: str = "openai", **kwargs: Any) -> LLMProvider:
    """Create an LLM provider by name.

    Args:
        name: "anthropic", "openai", "openrouter",
              or any OpenAI-compatible provider with base_url.
        **kwargs: Provider-specific arguments (api_key, base_url, etc.).
    """
    if name == "anthropic":
        from nanocc.providers.anthropic import AnthropicProvider
        return AnthropicProvider(**kwargs)  # type: ignore[return-value]

    # All others go through OpenAI-compatible provider
    from nanocc.providers.openai_compat import OpenAICompatProvider

    if name in _OPENAI_COMPAT_URLS and "base_url" not in kwargs:
        kwargs["base_url"] = _OPENAI_COMPAT_URLS[name]

    if name == "openai" and "base_url" not in kwargs:
        kwargs["base_url"] = "https://api.openai.com/v1"

    return OpenAICompatProvider(**kwargs)  # type: ignore[return-value]
