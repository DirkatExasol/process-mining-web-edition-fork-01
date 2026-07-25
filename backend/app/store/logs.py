"""Structured, shared application log.

One SQLite store (``data/logs.sqlite3``) is written by all three processes (compute
backend, GUI server, admin) and read by the admin "Logging" tab. Entries carry a
severity, the client IP, the acting user, an operation tag and a message, and are
always shown/exported **newest-first**.

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
from datetime import datetime, timezone

from ..config import LOGS_DB_PATH, LOGS_DIR

# Cumulative severity ladder — index is the rank; a max level records ranks <= it.
LEVELS: list[str] = ["INFO", "USAGE", "WARN", "ERROR", "DEBUG"]
_RANK: dict[str, int] = {name: i for i, name in enumerate(LEVELS)}

DEFAULT_LEVEL = "ERROR"  # INFO + USAGE + WARN + ERROR (everything but DEBUG)
DEFAULT_MAX_BYTES = 5_000_000
_MIN_MAX_BYTES = 50_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS log_entries (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    severity  TEXT NOT NULL,
    client_ip TEXT NOT NULL DEFAULT '',
    username  TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT '',
    message   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_log_severity ON log_entries(severity);
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
        # WAL so the three processes can write/read concurrently.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

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
    ) -> None:
        sev = normalize_level(severity, "")
        if not sev:
            return
        with self._lock:
            if _RANK[sev] > _RANK[normalize_level(self._get("level"), DEFAULT_LEVEL)]:
                return
            self._conn.execute(
                "INSERT INTO log_entries (ts, severity, client_ip, username, operation, message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), sev, client_ip or "", username or "", operation or "", message or ""),
            )
            self._conn.commit()
            self._maybe_rotate()

    # ── rotation ─────────────────────────────────────────────────────────────────

    def _total_bytes(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(LENGTH(message) + LENGTH(client_ip) + LENGTH(username) "
            "+ LENGTH(operation) + 40), 0) AS n FROM log_entries"
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
            "SELECT ts, severity, client_ip, username, operation, message "
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
        except OSError:
            pass  # never let a rotation IO error break request handling
        self._conn.execute("DELETE FROM log_entries")
        self._conn.commit()

    # ── query / export ────────────────────────────────────────────────────────

    def _build_where(
        self,
        *,
        level: str | None,
        severities: list[str] | None,
        client_ip: str,
        operation: str,
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
        search: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        where, params = self._build_where(
            level=level,
            severities=severities,
            client_ip=client_ip,
            operation=operation,
            search=search,
        )
        limit = max(1, min(int(limit), 5000))
        offset = max(0, int(offset))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT ts, severity, client_ip, username, operation, message "
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
        search: str = "",
    ) -> int:
        """Total rows matching the same filter query() uses — for pagination."""
        where, params = self._build_where(
            level=level,
            severities=severities,
            client_ip=client_ip,
            operation=operation,
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

    def render(self, **query_kwargs) -> str:
        """The current log as a DATE -- TIME -- ... file, newest-first."""
        entries = self.query(**query_kwargs)
        return "\n".join(_format_dict(e) for e in entries) + ("\n" if entries else "")

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM log_entries")
            self._conn.commit()


def _sql_regexp(pattern: str, value: str) -> bool:
    try:
        return re.search(pattern, value or "", re.IGNORECASE) is not None
    except re.error:
        # Fall back to a literal substring match on an invalid pattern.
        return (pattern or "").lower() in (value or "").lower()


def _row_to_dict(r: sqlite3.Row) -> dict:
    dt = datetime.fromtimestamp(r["ts"], tz=timezone.utc).astimezone()
    return {
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "severity": r["severity"],
        "clientIp": r["client_ip"],
        "user": r["username"],
        "operation": r["operation"],
        "message": r["message"],
    }


def format_line(r: sqlite3.Row) -> str:
    dt = datetime.fromtimestamp(r["ts"], tz=timezone.utc).astimezone()
    return " -- ".join(
        [
            dt.strftime("%Y-%m-%d"),
            dt.strftime("%H:%M:%S"),
            r["severity"],
            r["client_ip"] or "-",
            r["username"] or "-",
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
            e["message"],
        ]
    )


store = LogStore()
