"""Display-timezone helpers shared by the log store and the admin server.

The admin can set a display timezone (an IANA name such as ``Europe/Berlin``, or
``UTC``); an empty value means "the server's own local zone" (the historical
behaviour). Server-rendered timestamps — the log viewer/export and backup times —
are formatted through :func:`resolve_zone`, and the backup scheduler matches its
cron against the same zone's wall clock.
"""

from __future__ import annotations

from datetime import datetime, tzinfo
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


# ── wall-clock "now" and conversions in the admin's display zone ──────────────
#
# Timestamps the server *creates* (note created/edited dates, note comment stamps,
# sink events posted without an eventTime) are stored as naive wall-clock values in
# the display zone set in the Admin Console — the same zone the logs use — so every
# surface shows one consistent local time. Before this, a note's created date came
# from the browser as UTC while its edited date came from the database clock (local),
# so the two disagreed by the UTC offset.


def display_zone() -> tzinfo | None:
    """The Admin Console display zone, or ``None`` (= the server's local zone).
    Read on every call so an admin change takes effect without a restart."""
    try:
        from app.store.security import store  # lazy: keep this module dependency-free

        return resolve_zone(store.display_timezone)
    except Exception:  # noqa: BLE001 — store unavailable (tests, tooling) → server-local
        return None


def local_now() -> datetime:
    """Now, as a naive wall-clock datetime in the display zone (millisecond precision)."""
    zone = display_zone()
    now = datetime.now(zone) if zone is not None else datetime.now()
    return now.replace(tzinfo=None, microsecond=(now.microsecond // 1000) * 1000)


def to_local(dt: datetime) -> datetime:
    """An aware datetime → naive wall clock in the display zone. A naive datetime is
    assumed to already be display-zone wall clock and is returned unchanged."""
    if dt.tzinfo is None:
        return dt
    zone = display_zone()
    return (dt.astimezone(zone) if zone is not None else dt.astimezone()).replace(tzinfo=None)


def local_iso(dt: datetime | None) -> str | None:
    """A stored (naive, display-zone) timestamp → ISO-8601 *with* the zone's UTC offset,
    e.g. ``2026-09-23T12:34:45+02:00`` — unambiguous for API clients. ``None`` passes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        zone = display_zone()
        dt = dt.replace(tzinfo=zone) if zone is not None else dt.astimezone()
    return dt.isoformat(timespec="seconds")
