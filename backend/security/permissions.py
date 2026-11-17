"""Discord guild permission checks used by the dashboard allowlist."""

from __future__ import annotations

ADMINISTRATOR = 1 << 3
MANAGE_GUILD = 1 << 5


def can_manage_guild(guild: dict) -> bool:
    """Return whether the OAuth user owns or can manage a guild."""
    if guild.get("owner") is True:
        return True
    try:
        permissions = int(guild.get("permissions", "0"))
    except (TypeError, ValueError):
        return False
    return bool(permissions & (ADMINISTRATOR | MANAGE_GUILD))
