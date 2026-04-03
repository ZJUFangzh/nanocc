"""Configuration loading — settings.json + hook settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanocc.constants import DEFAULT_MODEL

# Config directories
GLOBAL_CONFIG_DIR = Path.home() / ".nanocc"
PROJECT_CONFIG_DIR_NAME = ".nanocc"


def get_global_config_dir() -> Path:
    d = GLOBAL_CONFIG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_config_dir(cwd: str) -> Path | None:
    p = Path(cwd) / PROJECT_CONFIG_DIR_NAME
    return p if p.is_dir() else None


def load_settings(cwd: str) -> dict[str, Any]:
    """Load merged settings from global + project settings.json."""
    settings: dict[str, Any] = {}

    # Global settings
    global_path = get_global_config_dir() / "settings.json"
    if global_path.is_file():
        try:
            with open(global_path) as f:
                settings.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass

    # Project settings (override global)
    proj_dir = get_project_config_dir(cwd)
    if proj_dir:
        proj_path = proj_dir / "settings.json"
        if proj_path.is_file():
            try:
                with open(proj_path) as f:
                    proj = json.load(f)
                    # Deep merge hooks
                    if "hooks" in proj and "hooks" in settings:
                        for event, hooks in proj["hooks"].items():
                            settings["hooks"].setdefault(event, []).extend(hooks)
                    else:
                        settings.update(proj)
            except (json.JSONDecodeError, OSError):
                pass

    return settings


def get_memory_dir(cwd: str) -> Path:
    """Get the memory directory path."""
    proj_dir = get_project_config_dir(cwd)
    if proj_dir:
        d = proj_dir / "memory"
    else:
        d = get_global_config_dir() / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_sessions_dir() -> Path:
    d = get_global_config_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Provider configuration resolution ─────────────────────────────────────

# Environment variable names for known providers
_ENV_KEYS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass
class ProviderConfig:
    """Resolved provider configuration."""

    model: str
    provider: str
    api_key: str | None
    api_base_url: str | None


def resolve_provider_config(
    cli_model: str | None = None,
    cli_provider: str | None = None,
    cli_api_key: str | None = None,
    cli_base_url: str | None = None,
    cwd: str = ".",
) -> ProviderConfig:
    """Resolve provider config with priority: CLI > env var > settings.json > default.

    Args:
        cli_model: Model from --model flag (None if not provided).
        cli_provider: Provider from --provider flag (None if not provided).
        cli_api_key: API key from --api-key flag (None if not provided).
        cli_base_url: Base URL from --base-url flag (None if not provided).
        cwd: Working directory for project-level settings.

    Returns:
        Resolved ProviderConfig.
    """
    settings = load_settings(cwd)

    model = cli_model or settings.get("model") or DEFAULT_MODEL
    provider = cli_provider or settings.get("provider") or "openrouter"
    api_base_url = cli_base_url or settings.get("apiBaseUrl") or None

    # API key: CLI > env var > settings
    api_key = cli_api_key
    if not api_key:
        env_var = _ENV_KEYS.get(provider, "OPENAI_API_KEY")
        api_key = os.environ.get(env_var)
    if not api_key:
        api_key = settings.get("apiKey")

    return ProviderConfig(
        model=model,
        provider=provider,
        api_key=api_key,
        api_base_url=api_base_url,
    )
