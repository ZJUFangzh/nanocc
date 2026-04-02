"""Configuration loading — settings.json + hook settings."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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
