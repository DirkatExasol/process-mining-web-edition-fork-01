"""Display-timezone helpers shared by the log store and the admin server.

The admin can set a display timezone (an IANA name such as ``Europe/Berlin``, or
``UTC``); an empty value means "the server's own local zone" (the historical
behaviour). Server-rendered timestamps — the log viewer/export and backup times —
are formatted through :func:`resolve_zone`, and the backup scheduler matches its
cron against the same zone's wall clock.
"""

from __future__ import annotations

from datetime import tzinfo
from zoneinfo import ZoneInfo


def resolve_zone(name: str | None) -> tzinfo | None:
    """Return a ``ZoneInfo`` for ``name``, or ``None`` (= the server's local zone)
    when ``name`` is empty or cannot be resolved. Never raises."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 — unknown zone / missing tzdata → server-local
        return None


def is_valid_zone(name: str) -> bool:
    """True if ``name`` is empty (server-local) or a resolvable IANA zone."""
    if not name:
        return True
    try:
        ZoneInfo(name)
        return True
    except Exception:  # noqa: BLE001
        return False
