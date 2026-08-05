"""Structured, shared application log.

One SQLite store (``data/logs.sqlite3``) is written by all three processes (compute
backend, GUI server, admin) and read by the admin "Logging" tab. Entries carry a
severity, the client IP, the acting user, an operation, an optional **tag** and a
message, and are always shown/exported **newest-first**.

The *operation* says which code path emitted the entry (``login``, ``db-sql``, …).
The *tag* is a coarser, user-facing category that groups a whole activity across
operations and severities — e.g. every step of a data import carries ``DATA``,
whether it ends at USAGE (imported) or ERROR (failed).

Severity is a cumulative ladder (the order the user chose): INFO < USAGE < WARN <
ERROR < DEBUG. A configurable *maximum level* records everything up to and including
it — e.g. ERROR records INFO+USAGE+WARN+ERROR (DEBUG only when the level is DEBUG).

When the live log passes the configured maximum size it is rotated: the current
entries are flushed to a timestamped ``.log`` file (the DATE -- TIME -- SEVERITY --
CLIENT-IP -- USER -- text format, newest-first) and the store is emptied.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from datetime import datetime, timezone, tzinfo

try:  # optional — enables a ReDoS-safe per-match timeout for the log search
    import regex as _regex
except ImportError:  # pragma: no cover - falls back to stdlib re
    _regex = None

from ..config import LOGS_DB_PATH, LOGS_DIR

# Cumulative severity ladder — index is the rank; a max level records ranks <= it.
LEVELS: list[str] = ["INFO", "USAGE", "WARN", "ERROR", "DEBUG"]
_RANK: dict[str, int] = {name: i for i, name in enumerate(LEVELS)}

DEFAULT_LEVEL = "ERROR"  # INFO + USAGE + WARN + ERROR (everything but DEBUG)
DEFAULT_MAX_BYTES = 5_000_000
_MIN_MAX_BYTES = 50_000
# Keep only the newest N rotated archives so the log directory can't grow without
# bound (the DB itself is capped by max_bytes; the archive dir was not).
_MAX_ARCHIVES = 10

# Control chars (esp. CR/LF) are replaced before storing, so no field — even one
# built from user-influenced text — can forge extra lines in the exported .log file.
_CTRL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _clean_field(value: str) -> str:
    return _CTRL_CHARS.sub(" ", value or "")


# A short, uppercase category stamped on an entry so related events can be found
# across operations and severities — e.g. every event of a data import is TAG=DATA,
# whether it ends at USAGE (success) or ERROR (failure).
TAG_DATA = "DATA"
_MAX_TAG_CHARS = 24


def normalize_tag(value: str | None) -> str:
    """Fold a tag to the stored form: uppercase, no spaces, length-capped."""
    return _clean_field(str(value or "").strip().upper().replace(" ", "_"))[:_MAX_TAG_CHARS]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS log_entries (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    severity  TEXT NOT NULL,
    client_ip TEXT NOT NULL DEFAULT '',
    username  TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT '',
    tag       TEXT NOT NULL DEFAULT '',
    message   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_log_severity ON log_entries(severity);
-- The tag index is created in _migrate(), AFTER the column is guaranteed to exist:
-- on an existing database CREATE TABLE IF NOT EXISTS is a no-op, so indexing a
-- column added later would fail here.
CREATE TABLE IF NOT EXISTS log_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> float:
    return time.time()


def normalize_level(value: str | None, fallback: str) -> str:
    v = (value or "").strip().upper()
    return v if v in _RANK else fallback


class LogStore:
    def __init__(self, path=LOGS_DB_PATH) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # A regexp() SQL function powers wildcard/regex search in the viewer.
        self._conn.create_function("regexp", 2, _sql_regexp)
        # WAL so the three processes can write/read concurrently; busy_timeout so a
        # cross-process writer retries instead of failing a log write with SQLITE_BUSY.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the initial release to an existing log DB."""
        cols = {
            r["name"]
            for r in self._conn.execute("PRAGMA table_info(log_entries)").fetchall()
        }
        if "tag" not in cols:
            self._conn.execute(
                "ALTER TABLE log_entries ADD COLUMN tag TEXT NOT NULL DEFAULT ''"
            )
        # Safe for both a fresh table and one just migrated.
        self._conn.execute("CREATE INDEX IF NOT EXISTS ix_log_tag ON log_entries(tag)")

    # ── config ────────────────────────────────────────────────────────────────

    def _get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM log_config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def _set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO log_config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    @property
    def level(self) -> str:
        with self._lock:
            return normalize_level(self._get("level"), DEFAULT_LEVEL)

    def set_level(self, level: str) -> None:
        with self._lock:
            self._set("level", normalize_level(level, DEFAULT_LEVEL))

    @property
    def max_bytes(self) -> int:
        with self._lock:
            try:
                return max(_MIN_MAX_BYTES, int(self._get("max_bytes") or DEFAULT_MAX_BYTES))
            except (TypeError, ValueError):
                return DEFAULT_MAX_BYTES

    def set_max_bytes(self, value: int) -> None:
        with self._lock:
            self._set("max_bytes", str(max(_MIN_MAX_BYTES, int(value))))

    def config(self) -> dict:
        return {
            "level": self.level,
            "maxBytes": self.max_bytes,
            "levels": list(LEVELS),
        }

    # ── recording ───────────────────────────────────────────────────────────────

    def is_enabled(self, severity: str) -> bool:
        sev = normalize_level(severity, "")
        return bool(sev) and _RANK[sev] <= _RANK[self.level]

    def record(
        self,
        severity: str,
        message: str,
        *,
        client_ip: str = "",
        username: str = "",
        operation: str = "",
        tag: str = "",
    ) -> None:
        sev = normalize_level(severity, "")
        if not sev:
            return
        with self._lock:
            if _RANK[sev] > _RANK[normalize_level(self._get("level"), DEFAULT_LEVEL)]:
                return
            self._conn.execute(
                "INSERT INTO log_entries "
                "(ts, severity, client_ip, username, operation, tag, message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    _now(),
                    sev,
                    _clean_field(client_ip),
                    _clean_field(username),
                    _clean_field(operation),
                    normalize_tag(tag),
                    _clean_field(message),
                ),
            )
            self._conn.commit()
            self._maybe_rotate()

    # ── rotation ─────────────────────────────────────────────────────────────────

    def _total_bytes(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(LENGTH(message) + LENGTH(client_ip) + LENGTH(username) "
            "+ LENGTH(operation) + LENGTH(tag) + 40), 0) AS n FROM log_entries"
        ).fetchone()
        return int(row["n"])

    def _maybe_rotate(self) -> None:
        try:
            limit = max(_MIN_MAX_BYTES, int(self._get("max_bytes") or DEFAULT_MAX_BYTES))
        except (TypeError, ValueError):
            limit = DEFAULT_MAX_BYTES
        if self._total_bytes() <= limit:
            return
        rows = self._conn.execute(
            "SELECT ts, severity, client_ip, username, operation, tag, message "
            "FROM log_entries ORDER BY id DESC"
        ).fetchall()
        if not rows:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = LOGS_DIR / f"pmw-{stamp}.log"
        try:
            path.write_text(
                "\n".join(format_line(r) for r in rows) + "\n", encoding="utf-8"
            )
            self._prune_archives()
        except OSError:
            pass  # never let a rotation IO error break request handling
        self._conn.execute("DELETE FROM log_entries")
        self._conn.commit()

    def _prune_archives(self) -> None:
        """Delete all but the newest `_MAX_ARCHIVES` rotated `pmw-*.log` files.
        Names are timestamped (`pmw-YYYYmmdd-HHMMSS.log`), so a lexical sort is
        chronological — no reliance on filesystem mtimes."""
        archives = sorted(LOGS_DIR.glob("pmw-*.log"))
        for stale in archives[:-_MAX_ARCHIVES]:
            try:
                stale.unlink()
            except OSError:
                pass  # best effort; a locked/removed file must not break rotation

    # ── query / export ────────────────────────────────────────────────────────

    def _build_where(
        self,
        *,
        level: str | None,
        severities: list[str] | None,
        client_ip: str,
        operation: str,
        tag: str,
        search: str,
    ) -> tuple[str, list[object]]:
        """Shared filter for query()/count() so both see the same result set."""
        clauses: list[str] = []
        params: list[object] = []
        # Severity: an explicit set, or everything up to a max level.
        picked = [s for s in (severities or []) if s in _RANK]
        if not picked and level:
            lvl = normalize_level(level, DEFAULT_LEVEL)
            picked = [s for s in LEVELS if _RANK[s] <= _RANK[lvl]]
        if picked:
            clauses.append("severity IN (%s)" % ",".join("?" * len(picked)))
            params.extend(picked)
        if client_ip.strip():
            clauses.append("client_ip LIKE ?")
            params.append(f"%{client_ip.strip()}%")
        if operation.strip():
            clauses.append("operation = ?")
            params.append(operation.strip())
        if tag.strip():
            clauses.append("tag = ?")
            params.append(normalize_tag(tag))
        if search.strip():
            clauses.append("message REGEXP ?")
            params.append(search.strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    def query(
        self,
        *,
        level: str | None = None,
        severities: list[str] | None = None,
        client_ip: str = "",
        operation: str = "",
        tag: str = "",
        search: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        where, params = self._build_where(
            level=level,
            severities=severities,
            client_ip=client_ip,
            operation=operation,
            tag=tag,
            search=search,
        )
        limit = max(1, min(int(limit), 5000))
        offset = max(0, int(offset))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT ts, severity, client_ip, username, operation, tag, message "
                f"FROM log_entries {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def count(
        self,
        *,
        level: str | None = None,
        severities: list[str] | None = None,
        client_ip: str = "",
        operation: str = "",
        tag: str = "",
        search: str = "",
    ) -> int:
        """Total rows matching the same filter query() uses — for pagination."""
        where, params = self._build_where(
            level=level,
            severities=severities,
            client_ip=client_ip,
            operation=operation,
            tag=tag,
            search=search,
        )
        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) AS n FROM log_entries {where}", tuple(params)
            ).fetchone()
        return int(row["n"]) if row else 0

    def operations(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT operation FROM log_entries "
                "WHERE operation <> '' ORDER BY operation"
            ).fetchall()
        return [r["operation"] for r in rows]

    def tags(self) -> list[str]:
        """The distinct tags present, for the viewer's filter dropdown."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT tag FROM log_entries WHERE tag <> '' ORDER BY tag"
            ).fetchall()
        return [r["tag"] for r in rows]

    def render(self, **query_kwargs) -> str:
        """The current log as a DATE -- TIME -- ... file, newest-first."""
        entries = self.query(**query_kwargs)
        return "\n".join(_format_dict(e) for e in entries) + ("\n" if entries else "")

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM log_entries")
            self._conn.commit()


# Bounds for the user-supplied search regex (admin log filter) — a defence against
# catastrophic-backtracking ReDoS. The `regex` engine enforces a real per-match
# timeout; an over-long or pathological pattern degrades to a literal substring
# match (the same safe fallback used for an invalid pattern).
_MAX_SEARCH_PATTERN = 250
_SEARCH_TIMEOUT_SECS = 0.25


def _sql_regexp(pattern: str, value: str) -> bool:
    pat = pattern or ""
    text = value or ""
    literal = pat.lower() in text.lower()
    if not pat or len(pat) > _MAX_SEARCH_PATTERN:
        return literal
    if _regex is not None:
        try:
            return (
                _regex.search(pat, text, _regex.IGNORECASE, timeout=_SEARCH_TIMEOUT_SECS)
                is not None
            )
        except (_regex.error, TimeoutError, ValueError):
            return literal
    try:  # stdlib fallback — no timeout, so lean on the length cap above
        return re.search(pat, text, re.IGNORECASE) is not None
    except re.error:
        return literal


# The zone used to render stored (UTC-epoch) log timestamps for the viewer and the
# exported .log. None = the server's own local zone (the historical behaviour); the
# admin server sets this from its display-timezone setting via set_display_timezone.
_display_tz: tzinfo | None = None


def set_display_timezone(tz: tzinfo | None) -> None:
    global _display_tz
    _display_tz = tz


def _row_value(r: sqlite3.Row, key: str) -> str:
    """Read a column that may be absent (a row selected before a migration added it)."""
    try:
        return r[key] or ""
    except (IndexError, KeyError):
        return ""


def _row_to_dict(r: sqlite3.Row) -> dict:
    dt = datetime.fromtimestamp(r["ts"], tz=timezone.utc).astimezone(_display_tz)
    return {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "severity": r["severity"],
        "clientIp": r["client_ip"],
        "user": r["username"],
        "operation": r["operation"],
        "tag": _row_value(r, "tag"),
        "message": r["message"],
    }


def format_line(r: sqlite3.Row) -> str:
    dt = datetime.fromtimestamp(r["ts"], tz=timezone.utc).astimezone(_display_tz)
    return " -- ".join(
        [
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%H:%M:%S"),
            r["severity"],
            r["client_ip"] or "-",
            r["username"] or "-",
            _row_value(r, "tag") or "-",
            r["message"] or "",
        ]
    )


def _format_dict(e: dict) -> str:
    return " -- ".join(
        [
            e["date"],
            e["time"],
            e["severity"],
            e["clientIp"] or "-",
            e["user"] or "-",
            e.get("tag") or "-",
            e["message"],
        ]
    )


store = LogStore()
