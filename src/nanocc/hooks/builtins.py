"""Built-in hooks — pre-configured hooks for common patterns."""

from __future__ import annotations

from nanocc.hooks.types import Hook, HookEvent, HookRegistration


def get_builtin_hooks() -> list[HookRegistration]:
    """Return built-in hook registrations."""
    # Currently empty — users configure via settings.json
    # Phase 8 will add things like pre-commit checks
    return []
