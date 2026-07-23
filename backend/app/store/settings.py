"""SQLite-backed replacement for the Swift app's UserDefaults + Keychain.

`kv`      — JSON values keyed exactly like the Swift UserDefaults keys, so a
            backup taken from the macOS app restores cleanly here.
`secrets` — database passwords and LLM API keys, encrypted with Fernet using a
            key file that is created on first run with mode 0600.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ..config import DB_PATH, SECRET_KEY_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS secrets (
    key   TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
"""


def _load_fernet() -> Fernet:
    if not SECRET_KEY_PATH.exists():
        SECRET_KEY_PATH.write_bytes(Fernet.generate_key())
        SECRET_KEY_PATH.chmod(0o600)
    return Fernet(SECRET_KEY_PATH.read_bytes())


class SettingsStore:
    """Thread-safe key/value store. One connection guarded by a lock — the write
    volume is tiny (UI preferences) so this is simpler than a pool."""

    def __init__(self, path=DB_PATH) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._fernet = _load_fernet()

    # ── plain values ─────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return default

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, payload),
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
            self._conn.commit()

    def all(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM kv").fetchall()
        out: dict[str, Any] = {}
        for key, raw in rows:
            try:
                out[key] = json.loads(raw)
            except json.JSONDecodeError:
                continue
        return out

    def keys_with_prefix(self, prefix: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM kv WHERE key LIKE ?", (f"{prefix}%",)
            ).fetchall()
        return [r[0] for r in rows]

    # ── secrets ──────────────────────────────────────────────────────────────

    def get_secret(self, key: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM secrets WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return ""
        try:
            return self._fernet.decrypt(row[0]).decode("utf-8")
        except InvalidToken:
            # Key file was replaced — treat the stored secret as lost rather than
            # crashing the request; the user can re-enter it.
            return ""

    def set_secret(self, key: str, value: str) -> None:
        blob = self._fernet.encrypt(value.encode("utf-8"))
        with self._lock:
            self._conn.execute(
                "INSERT INTO secrets (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, blob),
            )
            self._conn.commit()

    def delete_secret(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM secrets WHERE key = ?", (key,))
            self._conn.commit()


store = SettingsStore()
