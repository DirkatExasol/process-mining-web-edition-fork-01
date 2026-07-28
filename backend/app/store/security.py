"""Security store — users, TLS certificates and TLS mode.

Backed by a dedicated SQLite database (`data/security.sqlite3`) so it is cleanly
separable from the app's settings and can be read by every process (the admin
service manages it; the GUI launcher reads the TLS mode; the future login flow
will authenticate against the users table).

Private keys are encrypted at rest with the shared Fernet key. Passwords are
scrypt-hashed and never stored reversibly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import (
    ACTIVE_CERT_PATH,
    ACTIVE_KEY_PATH,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    SECURITY_DB_PATH,
)
from ..services import certs as cert_service
from .crypto import decrypt_text, encrypt_text, hash_password, verify_password

log = logging.getLogger("security-store")

# A throwaway hash so `authenticate` can run one scrypt verification even when the
# username doesn't exist — equalising response time against username enumeration.
_DUMMY_HASH = hash_password("pmw-nonexistent-account")

TLS_OFF = "off"
TLS_OPTIONAL = "optional"
TLS_REQUIRED = "required"
_TLS_MODES = {TLS_OFF, TLS_OPTIONAL, TLS_REQUIRED}

# ── Login-page appearance (admin "Customize" tab) ───────────────────────────
# Applies to both the app and admin sign-in pages. "default" keeps each page's
# existing theme colour; "color" paints a solid colour; "image" uses an uploaded
# background image (stored inline as a data: URI).
LOGIN_BG_DEFAULT = "default"
LOGIN_BG_COLOR = "color"
LOGIN_BG_IMAGE = "image"
_LOGIN_BG_TYPES = {LOGIN_BG_DEFAULT, LOGIN_BG_COLOR, LOGIN_BG_IMAGE}
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# data:image/<png|jpeg|gif|webp|svg+xml>;base64,<standard base64>
_DATA_IMAGE_RE = re.compile(
    r"^data:image/(png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/]+={0,2}$"
)
# Cap the stored data URI so a background image can't bloat the settings DB or a
# backup export. ~4 MB of base64 ≈ a 3 MB source image — plenty for a backdrop.
_MAX_LOGIN_IMAGE_CHARS = 4_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    is_enabled    INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);
CREATE TABLE IF NOT EXISTS certificates (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    cert_pem       TEXT NOT NULL,
    key_enc        TEXT NOT NULL,
    subject        TEXT,
    issuer         TEXT,
    not_before     TEXT,
    not_after      TEXT,
    sans           TEXT,
    is_self_signed INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS security_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connections (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    comment       TEXT DEFAULT '',
    host          TEXT DEFAULT '',
    port          INTEGER DEFAULT 8563,
    username      TEXT DEFAULT '',
    db_schema     TEXT DEFAULT '',
    use_tls       INTEGER DEFAULT 0,
    cert_mode     TEXT DEFAULT 'verify',
    fingerprint   TEXT DEFAULT '',
    min_rsa_bits  INTEGER DEFAULT 2048,
    password_enc  TEXT DEFAULT '',
    llm_url       TEXT DEFAULT '',
    llm_model     TEXT DEFAULT '',
    llm_key_enc   TEXT DEFAULT '',
    owner         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connection_assignments (
    connection_id TEXT NOT NULL,
    username      TEXT NOT NULL,
    PRIMARY KEY (connection_id, username)
);
CREATE TABLE IF NOT EXISTS ldap_config (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    enabled           INTEGER NOT NULL DEFAULT 0,
    server_uri        TEXT NOT NULL DEFAULT '',
    start_tls         INTEGER NOT NULL DEFAULT 0,
    verify_cert       INTEGER NOT NULL DEFAULT 1,
    ca_cert           TEXT NOT NULL DEFAULT '',
    bind_dn           TEXT NOT NULL DEFAULT '',
    bind_password_enc TEXT NOT NULL DEFAULT '',
    base_dn           TEXT NOT NULL DEFAULT '',
    user_filter       TEXT NOT NULL DEFAULT '(uid={username})',
    login_attr        TEXT NOT NULL DEFAULT 'uid',
    email_attr        TEXT NOT NULL DEFAULT 'mail',
    display_attr      TEXT NOT NULL DEFAULT 'cn',
    admin_login_enabled INTEGER NOT NULL DEFAULT 0,
    updated_at        TEXT NOT NULL DEFAULT ''
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class User:
    username: str
    is_admin: bool
    is_enabled: bool
    created_at: str
    last_login: str | None = None
    auth_source: str = "local"  # 'local' | 'ldap'
    email: str = ""
    display_name: str = ""
    is_power: bool = False  # may create/manage their own DB connections from the app
    failed_logins: int = 0
    login_locked: bool = False  # disabled by the failed-sign-in lockout
    session_epoch: int = 0  # bumped on logout; stale-epoch tokens are rejected

    def public(self) -> dict:
        return {
            "username": self.username,
            "isAdmin": self.is_admin,
            "isEnabled": self.is_enabled,
            "failedLogins": self.failed_logins,
            "loginLocked": self.login_locked,
            "createdAt": self.created_at,
            "lastLogin": self.last_login,
            "authSource": self.auth_source,
            "email": self.email,
            "displayName": self.display_name,
            "isPower": self.is_power,
        }


@dataclass
class Certificate:
    id: str
    name: str
    subject: str
    issuer: str
    not_before: str
    not_after: str
    sans: list[str] = field(default_factory=list)
    is_self_signed: bool = False
    created_at: str = ""

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "issuer": self.issuer,
            "notBefore": self.not_before,
            "notAfter": self.not_after,
            "sans": self.sans,
            "isSelfSigned": self.is_self_signed,
            "createdAt": self.created_at,
        }


@dataclass
class Connection:
    """An admin-defined server connection (Exasol + optional LLM) with the set of
    usernames it is assigned to. Secret fields hold decrypted values only when the
    row was read for connecting; the serialisers below never leak them."""

    id: str
    name: str
    comment: str = ""
    host: str = ""
    port: int = 8563
    username: str = ""
    schema: str = ""
    use_tls: bool = False
    cert_mode: str = "verify"
    fingerprint: str = ""
    min_rsa_bits: int = 2048
    password: str = ""
    llm_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    assignments: list[str] = field(default_factory=list)
    has_password: bool = False
    has_llm_key: bool = False
    owner: str = ""  # power user who created it from the app; '' = admin-defined
    created_at: str = ""
    use_materialized_transitions: bool = False

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_url.strip())

    def admin_public(self) -> dict:
        """Full definition for the admin UI — assignments included, secrets not."""
        return {
            "id": self.id,
            "name": self.name,
            "comment": self.comment,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "schema": self.schema,
            "useTLS": self.use_tls,
            "certModeRaw": self.cert_mode,
            "fingerprint": self.fingerprint,
            "minRSAKeySizeBits": self.min_rsa_bits,
            "hasPassword": self.has_password,
            "llmURL": self.llm_url,
            "llmModel": self.llm_model,
            "hasLLMKey": self.has_llm_key,
            "assignments": self.assignments,
            "owner": self.owner,
            "createdAt": self.created_at,
            "useMaterializedTransitions": self.use_materialized_transitions,
        }

    def user_public(self) -> dict:
        """What a signed-in user may see about a connection assigned to them."""
        return {
            "id": self.id,
            "name": self.name,
            "comment": self.comment,
            "host": self.host,
            "port": self.port,
            "schema": self.schema,
            "hasLLM": self.has_llm,
            "llmURL": self.llm_url if self.has_llm else None,
        }


class SecurityStore:
    def __init__(self, path=SECURITY_DB_PATH) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL improves concurrency between the admin (writer) and backend (reader).
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()
        self._bootstrap()
        # Recovery valve: set PMW_RESET_LOCKOUTS=1 and restart to clear every
        # failed-sign-in lockout (e.g. if the sole admin locked themselves out).
        if os.environ.get("PMW_RESET_LOCKOUTS", "").strip().lower() in (
            "1", "true", "yes", "on"
        ):
            with self._lock:
                self._conn.execute(
                    "UPDATE users SET login_locked = 0, failed_logins = 0, "
                    "is_enabled = 1 WHERE login_locked = 1"
                )
                self._conn.commit()
            log.warning("PMW_RESET_LOCKOUTS set — cleared all failed-sign-in lockouts.")

    def _migrate(self) -> None:
        """Add columns introduced after the initial release to existing databases."""
        cols = {
            r["name"] for r in self._conn.execute("PRAGMA table_info(users)").fetchall()
        }
        for name, ddl in (
            ("auth_source", "auth_source TEXT NOT NULL DEFAULT 'local'"),
            ("email", "email TEXT NOT NULL DEFAULT ''"),
            ("display_name", "display_name TEXT NOT NULL DEFAULT ''"),
            ("is_power", "is_power INTEGER NOT NULL DEFAULT 0"),
            # Failed-sign-in lockout (admin-configurable threshold).
            ("failed_logins", "failed_logins INTEGER NOT NULL DEFAULT 0"),
            ("login_locked", "login_locked INTEGER NOT NULL DEFAULT 0"),
            # Bumped on logout to invalidate that user's outstanding session tokens.
            ("session_epoch", "session_epoch INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                self._conn.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
        # Connections gained an owner (the power user who created them; '' = admin).
        conn_cols = {
            r["name"] for r in self._conn.execute("PRAGMA table_info(connections)").fetchall()
        }
        if "owner" not in conn_cols:
            self._conn.execute("ALTER TABLE connections ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        # Opt-in to reading transitions from the pre-materialised TRANSITIONS_RAW
        # table instead of the live LEAD() query (falls back if it isn't built).
        if "use_materialized_transitions" not in conn_cols:
            self._conn.execute(
                "ALTER TABLE connections ADD COLUMN "
                "use_materialized_transitions INTEGER NOT NULL DEFAULT 0"
            )
        # Directory sign-in to the admin interface is an explicit opt-in (default off).
        ldap_cols = {
            r["name"] for r in self._conn.execute("PRAGMA table_info(ldap_config)").fetchall()
        }
        if "admin_login_enabled" not in ldap_cols:
            self._conn.execute(
                "ALTER TABLE ldap_config ADD COLUMN admin_login_enabled INTEGER NOT NULL DEFAULT 0"
            )

    # ── bootstrap ─────────────────────────────────────────────────────────────

    def _bootstrap(self) -> None:
        """Seed the default administrator and default TLS mode on first run."""
        with self._lock:
            count = self._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                self._conn.execute(
                    "INSERT INTO users (username, password_hash, is_admin, is_enabled, created_at) "
                    "VALUES (?, ?, 1, 1, ?)",
                    (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD), _now()),
                )
            if count == 0:
                # Track that the bootstrap admin still uses its default password.
                self._set_config("default_admin_active", "1")
            if self._get_config("tls_mode") is None:
                self._set_config("tls_mode", TLS_OFF)
            if self._get_config("require_login") is None:
                # Multi-user default: the main app requires sign-in.
                self._set_config("require_login", "1")
            self._conn.commit()

    @property
    def default_admin_password_active(self) -> bool:
        with self._lock:
            return self._get_config("default_admin_active") == "1"

    @property
    def require_login(self) -> bool:
        with self._lock:
            return self._get_config("require_login") != "0"

    def set_require_login(self, required: bool) -> None:
        with self._lock:
            self._set_config("require_login", "1" if required else "0")
            self._conn.commit()

    @property
    def idle_timeout_mins(self) -> int:
        """Auto sign-out after this many minutes of inactivity (0 = never)."""
        with self._lock:
            try:
                return max(0, int(self._get_config("idle_timeout_mins") or 0))
            except (TypeError, ValueError):
                return 0

    def set_idle_timeout_mins(self, minutes: int) -> None:
        minutes = max(0, int(minutes))
        with self._lock:
            self._set_config("idle_timeout_mins", str(minutes))
            self._conn.commit()

    @property
    def admin_idle_timeout_mins(self) -> int:
        """Auto sign-out of the *admin interface* after N minutes idle (0 = never).
        Configured separately from the main app's idle timeout."""
        with self._lock:
            try:
                return max(0, int(self._get_config("admin_idle_timeout_mins") or 0))
            except (TypeError, ValueError):
                return 0

    def set_admin_idle_timeout_mins(self, minutes: int) -> None:
        minutes = max(0, int(minutes))
        with self._lock:
            self._set_config("admin_idle_timeout_mins", str(minutes))
            self._conn.commit()

    # ── failed-sign-in lockout ────────────────────────────────────────────────

    @property
    def max_failed_logins(self) -> int:
        """Disable an account after this many consecutive failed sign-ins
        (0 = never lock). Applies to every account, including the Administrator."""
        with self._lock:
            try:
                return max(0, int(self._get_config("max_failed_logins") or 0))
            except (TypeError, ValueError):
                return 0

    def set_max_failed_logins(self, count: int) -> None:
        with self._lock:
            self._set_config("max_failed_logins", str(max(0, int(count))))
            self._conn.commit()

    def record_login_failure(self, username: str) -> bool:
        """Count a failed sign-in; lock (disable) the account once it reaches the
        configured threshold. Returns True if this failure locked it. A direct write
        so it can lock the built-in Administrator too (per the configured policy)."""
        threshold = self.max_failed_logins
        with self._lock:
            row = self._conn.execute(
                "SELECT failed_logins FROM users WHERE LOWER(username) = LOWER(?)",
                (username,),
            ).fetchone()
            if row is None:
                return False
            count = int(row["failed_logins"] or 0) + 1
            locked = threshold > 0 and count >= threshold
            self._conn.execute(
                "UPDATE users SET failed_logins = ?, "
                "is_enabled = CASE WHEN ? THEN 0 ELSE is_enabled END, "
                "login_locked = CASE WHEN ? THEN 1 ELSE login_locked END "
                "WHERE LOWER(username) = LOWER(?)",
                (count, int(locked), int(locked), username),
            )
            self._conn.commit()
        if locked:  # logged outside the store lock (the log store has its own lock)
            from .. import log_events as logx

            logx.warn(
                f"account {username!r} locked (disabled) after {count} failed "
                f"sign-in attempts",
                username=username,
                operation="login",
            )
        return locked

    def reset_login_failures(self, username: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET failed_logins = 0, login_locked = 0 "
                "WHERE LOWER(username) = LOWER(?)",
                (username,),
            )
            self._conn.commit()

    def session_epoch(self, username: str) -> int:
        """Current session epoch for a user (0 if unknown). Embedded in freshly
        issued session tokens; a token whose epoch is stale is no longer valid."""
        with self._lock:
            row = self._conn.execute(
                "SELECT session_epoch FROM users WHERE LOWER(username) = LOWER(?)",
                (username,),
            ).fetchone()
        return int(row["session_epoch"]) if row else 0

    def bump_session_epoch(self, username: str) -> None:
        """Invalidate every outstanding session token for a user (used on logout).
        Because tokens are stateless and re-minted on each request, revoking by
        epoch is the only way to also kill a token captured earlier in the session."""
        with self._lock:
            self._conn.execute(
                "UPDATE users SET session_epoch = session_epoch + 1 "
                "WHERE LOWER(username) = LOWER(?)",
                (username,),
            )
            self._conn.commit()

    def login_block_message(self, username: str) -> str | None:
        """A message to show the user when their account is disabled/locked, or None
        for a plain bad-credentials failure (so we don't reveal account existence)."""
        user = self.get_user(username)
        if user is None or user.is_enabled:
            return None
        if user.login_locked:
            return (
                "This account has been locked after too many failed sign-in "
                "attempts. Contact an administrator."
            )
        return "This account has been disabled. Contact an administrator."

    # ── LDAP / directory ──────────────────────────────────────────────────────

    def _ldap_row(self) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM ldap_config WHERE id = 1").fetchone()

    @property
    def ldap_enabled(self) -> bool:
        with self._lock:
            row = self._ldap_row()
        return bool(row and row["enabled"])

    def ldap_admin_public(self) -> dict:
        """LDAP settings for the admin UI — the bind password is never returned."""
        with self._lock:
            row = self._ldap_row()
        if row is None:
            return {
                "enabled": False,
                "serverURI": "",
                "startTLS": False,
                "verifyCert": True,
                "caCert": "",
                "bindDN": "",
                "hasBindPassword": False,
                "baseDN": "",
                "userFilter": "(uid={username})",
                "loginAttr": "uid",
                "emailAttr": "mail",
                "displayAttr": "cn",
                "adminLoginEnabled": False,
            }
        return {
            "enabled": bool(row["enabled"]),
            "serverURI": row["server_uri"],
            "startTLS": bool(row["start_tls"]),
            "verifyCert": bool(row["verify_cert"]),
            "caCert": row["ca_cert"],
            "bindDN": row["bind_dn"],
            "hasBindPassword": bool(row["bind_password_enc"]),
            "baseDN": row["base_dn"],
            "userFilter": row["user_filter"],
            "loginAttr": row["login_attr"],
            "emailAttr": row["email_attr"],
            "displayAttr": row["display_attr"],
            "adminLoginEnabled": self._row_flag(row, "admin_login_enabled"),
        }

    @property
    def ldap_admin_login_enabled(self) -> bool:
        """Whether directory accounts may sign in to the admin interface (opt-in).

        Requires the directory to be enabled at all; admin rights are still enforced
        separately (a directory user must be promoted to admin to get in)."""
        with self._lock:
            row = self._ldap_row()
        return bool(row and row["enabled"] and self._row_flag(row, "admin_login_enabled"))

    @staticmethod
    def _row_flag(row: sqlite3.Row, name: str) -> bool:
        """Read an optional boolean column that may predate a migration."""
        return bool(row[name]) if name in row.keys() else False

    def ldap_settings(self):
        """Build the LdapSettings used for authentication (bind password decrypted)."""
        from ..services.ldap_auth import LdapSettings

        with self._lock:
            row = self._ldap_row()
        if row is None:
            return LdapSettings()
        return LdapSettings(
            enabled=bool(row["enabled"]),
            server_uri=row["server_uri"],
            start_tls=bool(row["start_tls"]),
            verify_cert=bool(row["verify_cert"]),
            ca_cert=row["ca_cert"],
            bind_dn=row["bind_dn"],
            bind_password=decrypt_text(row["bind_password_enc"]) if row["bind_password_enc"] else "",
            base_dn=row["base_dn"],
            user_filter=row["user_filter"] or "(uid={username})",
            login_attr=row["login_attr"] or "uid",
            email_attr=row["email_attr"] or "mail",
            display_attr=row["display_attr"] or "cn",
        )

    def set_ldap_config(self, data: dict) -> None:
        """Upsert the single LDAP config row. The bind password follows the same
        secret rule as connections: pass ``bindPassword`` to set it, omit to keep
        the stored value, or pass an empty string to clear it."""
        with self._lock:
            existing = self._ldap_row()
            if "bindPassword" in data:
                pw = data["bindPassword"] or ""
                bind_enc = encrypt_text(pw) if pw else ""
            else:
                bind_enc = existing["bind_password_enc"] if existing else ""
            self._conn.execute(
                """
                INSERT INTO ldap_config
                    (id, enabled, server_uri, start_tls, verify_cert, ca_cert, bind_dn,
                     bind_password_enc, base_dn, user_filter, login_attr, email_attr,
                     display_attr, admin_login_enabled, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    enabled=excluded.enabled, server_uri=excluded.server_uri,
                    start_tls=excluded.start_tls, verify_cert=excluded.verify_cert,
                    ca_cert=excluded.ca_cert, bind_dn=excluded.bind_dn,
                    bind_password_enc=excluded.bind_password_enc, base_dn=excluded.base_dn,
                    user_filter=excluded.user_filter, login_attr=excluded.login_attr,
                    email_attr=excluded.email_attr, display_attr=excluded.display_attr,
                    admin_login_enabled=excluded.admin_login_enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    int(bool(data.get("enabled"))),
                    (data.get("serverURI") or "").strip(),
                    int(bool(data.get("startTLS"))),
                    int(bool(data.get("verifyCert", True))),
                    data.get("caCert") or "",
                    (data.get("bindDN") or "").strip(),
                    bind_enc,
                    (data.get("baseDN") or "").strip(),
                    (data.get("userFilter") or "(uid={username})").strip(),
                    (data.get("loginAttr") or "uid").strip(),
                    (data.get("emailAttr") or "mail").strip(),
                    (data.get("displayAttr") or "cn").strip(),
                    int(bool(data.get("adminLoginEnabled"))),
                    _now(),
                ),
            )
            self._conn.commit()

    def provision_ldap_user(self, username: str, email: str = "", display_name: str = "") -> User:
        """Create (or refresh) the local record for a directory user on login.

        Directory users have no local password; their admin/enabled flags and DB
        connection assignments still live here, so a row must exist locally.
        """
        username = username.strip()
        existing = self.get_user(username)
        with self._lock:
            if existing is None:
                self._conn.execute(
                    "INSERT INTO users (username, password_hash, is_admin, is_enabled, "
                    "created_at, auth_source, email, display_name) "
                    "VALUES (?, '', 0, 1, ?, 'ldap', ?, ?)",
                    (username, _now(), email, display_name),
                )
            else:
                # Keep the directory-sourced attributes fresh; never touch role/enabled.
                self._conn.execute(
                    "UPDATE users SET email = ?, display_name = ? "
                    "WHERE LOWER(username) = LOWER(?)",
                    (email, display_name, username),
                )
            self._conn.commit()
        return self.get_user(username)  # type: ignore[return-value]

    # ── config ────────────────────────────────────────────────────────────────

    def _get_config(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM security_config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def _set_config(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO security_config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    @property
    def tls_mode(self) -> str:
        with self._lock:
            return self._get_config("tls_mode") or TLS_OFF

    def set_tls_mode(self, mode: str) -> None:
        if mode not in _TLS_MODES:
            raise ValueError(f"Unknown TLS mode {mode!r}")
        with self._lock:
            self._set_config("tls_mode", mode)
            self._conn.commit()
        self._materialise_active_cert()

    @property
    def active_cert_id(self) -> str | None:
        with self._lock:
            return self._get_config("active_cert_id")

    # ── materialised-transitions rebuild token ──────────────────────────────
    # A high-entropy bearer token that lets an external scheduler (cron/ETL)
    # trigger a rebuild after loading JOURNEYS, without an admin session. Only
    # the SHA-256 hash is stored; the plaintext is shown once at generation.

    def generate_rebuild_token(self) -> str:
        """Create (or rotate) the rebuild token and return the plaintext ONCE."""
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            self._set_config("rebuild_token_hash", digest)
            self._conn.commit()
        return token

    def clear_rebuild_token(self) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM security_config WHERE key = ?", ("rebuild_token_hash",)
            )
            self._conn.commit()

    @property
    def rebuild_token_set(self) -> bool:
        with self._lock:
            return bool(self._get_config("rebuild_token_hash"))

    def verify_rebuild_token(self, token: str) -> bool:
        """Constant-time check of a presented token against the stored hash."""
        if not token:
            return False
        with self._lock:
            stored = self._get_config("rebuild_token_hash")
        if not stored:
            return False
        presented = hashlib.sha256(token.encode()).hexdigest()
        return hmac.compare_digest(stored, presented)

    # ── per-connection materialisation status (for the admin display) ───────

    def materialization_status(self, conn_id: str) -> dict | None:
        """Last rebuild outcome for a connection: {ok, rows, built_at, error}."""
        with self._lock:
            raw = self._get_config(f"matview:{conn_id}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def set_materialization_status(self, conn_id: str, status: dict) -> None:
        with self._lock:
            self._set_config(f"matview:{conn_id}", json.dumps(status))
            self._conn.commit()

    # ── login-page appearance ───────────────────────────────────────────────

    def login_appearance(self) -> dict:
        """Background chosen in the admin Customize tab, applied to both sign-in
        pages. `type` is default|color|image; only the field for the active type
        is meaningful."""
        with self._lock:
            bg_type = self._get_config("login_bg_type") or LOGIN_BG_DEFAULT
            if bg_type not in _LOGIN_BG_TYPES:
                bg_type = LOGIN_BG_DEFAULT
            return {
                "type": bg_type,
                "color": self._get_config("login_bg_color") or "",
                "image": self._get_config("login_bg_image") or "",
            }

    def set_login_appearance(
        self, *, type: str, color: str = "", image: str | None = None
    ) -> dict:
        """Persist the login background. Validates every field so the stored
        values are always safe to inject into CSS (no injection / no bloat).
        Raises ValueError on bad input. Returns the stored appearance."""
        if type not in _LOGIN_BG_TYPES:
            raise ValueError(f"Unknown login background type {type!r}")

        # Validate ANY supplied value up front, not just the one matching `type`,
        # so a non-active field can never persist an unvalidated (CSS-unsafe)
        # value — even though the render side re-checks before injecting.
        color = (color or "").strip()
        if color and not _HEX_COLOR_RE.match(color):
            raise ValueError("Color must be a #rrggbb hex value")
        if image is not None:
            image = image.strip()
            if image:
                if len(image) > _MAX_LOGIN_IMAGE_CHARS:
                    raise ValueError("Image is too large (max ~3 MB)")
                if not _DATA_IMAGE_RE.match(image):
                    raise ValueError(
                        "Background image must be a PNG, JPEG, GIF, WebP or SVG"
                    )

        if type == LOGIN_BG_COLOR and not color:
            raise ValueError("Color must be a #rrggbb hex value")
        if type == LOGIN_BG_IMAGE:
            # No new upload → the already-stored image must itself be valid.
            candidate = image if image else (self._get_config("login_bg_image") or "")
            if not candidate:
                raise ValueError("Choose a background image first")
            if len(candidate) > _MAX_LOGIN_IMAGE_CHARS or not _DATA_IMAGE_RE.match(
                candidate
            ):
                raise ValueError("Choose a valid background image first")

        with self._lock:
            self._set_config("login_bg_type", type)
            if color:
                self._set_config("login_bg_color", color)
            if image:
                self._set_config("login_bg_image", image)
            self._conn.commit()
        return self.login_appearance()

    # ── users ─────────────────────────────────────────────────────────────────

    def _row_to_user(self, row: sqlite3.Row) -> User:
        keys = row.keys()
        return User(
            username=row["username"],
            is_admin=bool(row["is_admin"]),
            is_enabled=bool(row["is_enabled"]),
            created_at=row["created_at"],
            last_login=row["last_login"],
            auth_source=(row["auth_source"] if "auth_source" in keys else "local") or "local",
            email=(row["email"] if "email" in keys else "") or "",
            display_name=(row["display_name"] if "display_name" in keys else "") or "",
            is_power=bool(row["is_power"]) if "is_power" in keys else False,
            failed_logins=int(row["failed_logins"]) if "failed_logins" in keys else 0,
            login_locked=bool(row["login_locked"]) if "login_locked" in keys else False,
            session_epoch=int(row["session_epoch"]) if "session_epoch" in keys else 0,
        )

    def list_users(self) -> list[User]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM users ORDER BY LOWER(username)"
            ).fetchall()
        return [self._row_to_user(r) for r in rows]

    def get_user(self, username: str) -> User | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def create_user(self, username: str, password: str, is_admin: bool) -> User:
        username = username.strip()
        if not username:
            raise ValueError("Username is required.")
        if not password:
            raise ValueError("Password is required.")
        if self.get_user(username) is not None:
            raise ValueError(f"A user named {username!r} already exists.")
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, is_enabled, created_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (username, hash_password(password), int(is_admin), _now()),
            )
            self._conn.commit()
        return self.get_user(username)  # type: ignore[return-value]

    def set_password(self, username: str, password: str) -> None:
        if not password:
            raise ValueError("Password is required.")
        with self._lock:
            self._conn.execute(
                "UPDATE users SET password_hash = ? WHERE LOWER(username) = LOWER(?)",
                (hash_password(password), username),
            )
            # Changing the bootstrap admin's password clears the default-password flag.
            if username.lower() == DEFAULT_ADMIN_USERNAME.lower():
                self._conn.execute(
                    "DELETE FROM security_config WHERE key = 'default_admin_active'"
                )
            self._conn.commit()

    def set_enabled(self, username: str, enabled: bool) -> None:
        user = self.get_user(username)
        if user is None:
            raise ValueError("No such user.")
        if not enabled and self._is_builtin_admin(username):
            raise ValueError("The built-in Administrator account cannot be disabled.")
        if not enabled and user.is_admin:
            self._guard_last_admin(exclude=username)
        with self._lock:
            # Re-enabling also clears any failed-sign-in lockout (and its counter).
            if enabled:
                self._conn.execute(
                    "UPDATE users SET is_enabled = 1, login_locked = 0, "
                    "failed_logins = 0 WHERE LOWER(username) = LOWER(?)",
                    (username,),
                )
            else:
                self._conn.execute(
                    "UPDATE users SET is_enabled = 0 WHERE LOWER(username) = LOWER(?)",
                    (username,),
                )
            self._conn.commit()

    def set_admin(self, username: str, is_admin: bool) -> None:
        user = self.get_user(username)
        if user is None:
            raise ValueError("No such user.")
        if not is_admin and self._is_builtin_admin(username):
            raise ValueError(
                "The built-in Administrator account must remain an administrator."
            )
        if not is_admin and user.is_admin:
            self._guard_last_admin(exclude=username)
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_admin = ? WHERE LOWER(username) = LOWER(?)",
                (int(is_admin), username),
            )
            self._conn.commit()

    def set_power(self, username: str, is_power: bool) -> None:
        """Grant/revoke the 'power' role — may create & manage their own connections."""
        if self.get_user(username) is None:
            raise ValueError("No such user.")
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_power = ? WHERE LOWER(username) = LOWER(?)",
                (int(is_power), username),
            )
            self._conn.commit()

    def delete_user(self, username: str) -> None:
        user = self.get_user(username)
        if user is None:
            return
        if self._is_builtin_admin(username):
            raise ValueError("The built-in Administrator account cannot be deleted.")
        if user.is_admin:
            self._guard_last_admin(exclude=username)
        with self._lock:
            self._conn.execute(
                "DELETE FROM users WHERE LOWER(username) = LOWER(?)", (username,)
            )
            self._conn.commit()

    def _is_builtin_admin(self, username: str) -> bool:
        """The seeded default administrator, protected from disable / demote."""
        return username.strip().lower() == DEFAULT_ADMIN_USERNAME.lower()

    def _guard_last_admin(self, exclude: str) -> None:
        """Refuse an operation that would leave no enabled administrator."""
        remaining = [
            u
            for u in self.list_users()
            if u.is_admin
            and u.is_enabled
            and u.username.lower() != exclude.lower()
        ]
        if not remaining:
            raise ValueError(
                "This would leave no enabled administrator. Promote or enable "
                "another admin first."
            )

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user on a successful, enabled login; None otherwise.

        A failed sign-in on an enabled account is counted and can lock the account
        (see max_failed_logins); a success clears the counter. One scrypt check runs
        even when the account is missing, so timing doesn't reveal its existence.
        """
        user = self.get_user(username)
        with self._lock:
            row = self._conn.execute(
                "SELECT password_hash FROM users WHERE LOWER(username) = LOWER(?)",
                (username,),
            ).fetchone()
        password_ok = verify_password(
            password, row["password_hash"] if row is not None else _DUMMY_HASH
        )
        if user is None or row is None:
            return None
        if not password_ok:
            # Count local-password failures only; directory users have no local
            # password (a local check always "fails" for them and is authenticated
            # via LDAP separately), and an already-disabled account isn't re-counted.
            if user.is_enabled and user.auth_source != "ldap":
                self.record_login_failure(username)
            return None
        if not user.is_enabled:
            return None  # correct password, but the account is disabled / locked
        self.reset_login_failures(username)
        with self._lock:
            self._conn.execute(
                "UPDATE users SET last_login = ? WHERE LOWER(username) = LOWER(?)",
                (_now(), username),
            )
            self._conn.commit()
        return user

    def authenticate_app(self, username: str, password: str) -> User | None:
        """Authenticate a *main-app* sign-in: local accounts first (always, so a
        local admin stays a break-glass account), then the directory when enabled.

        Admin rights are never granted from LDAP — a JIT-provisioned directory user
        is a plain, enabled user until an admin promotes them locally.
        """
        local = self.authenticate(username, password)
        if local is not None:
            return local

        if not self.ldap_enabled:
            return None

        from ..services.ldap_auth import LdapError, authenticate as ldap_authenticate

        try:
            dir_user = ldap_authenticate(self.ldap_settings(), username, password)
        except LdapError as exc:
            log.warning("LDAP authentication error for %r: %s", username, exc)
            return None
        if dir_user is None:
            return None

        user = self.provision_ldap_user(
            dir_user.username, email=dir_user.email, display_name=dir_user.display_name
        )
        if not user.is_enabled:
            return None  # an admin has blocked this directory account locally
        with self._lock:
            self._conn.execute(
                "UPDATE users SET last_login = ? WHERE LOWER(username) = LOWER(?)",
                (_now(), user.username),
            )
            self._conn.commit()
        return self.get_user(user.username)

    # ── certificates ──────────────────────────────────────────────────────────

    def _row_to_cert(self, row: sqlite3.Row) -> Certificate:
        return Certificate(
            id=row["id"],
            name=row["name"],
            subject=row["subject"] or "",
            issuer=row["issuer"] or "",
            not_before=row["not_before"] or "",
            not_after=row["not_after"] or "",
            sans=(row["sans"] or "").split(",") if row["sans"] else [],
            is_self_signed=bool(row["is_self_signed"]),
            created_at=row["created_at"],
        )

    def list_certificates(self) -> list[Certificate]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM certificates ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_cert(r) for r in rows]

    def get_certificate(self, cert_id: str) -> Certificate | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM certificates WHERE id = ?", (cert_id,)
            ).fetchone()
        return self._row_to_cert(row) if row else None

    def certificate_pem(self, cert_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT cert_pem FROM certificates WHERE id = ?", (cert_id,)
            ).fetchone()
        return row["cert_pem"] if row else None

    def _store_certificate(
        self, name: str, cert_pem: str, key_pem: str, info: cert_service.CertInfo
    ) -> Certificate:
        cert_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO certificates "
                "(id, name, cert_pem, key_enc, subject, issuer, not_before, not_after, "
                " sans, is_self_signed, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cert_id,
                    name.strip() or "certificate",
                    cert_pem,
                    encrypt_text(key_pem),
                    info.subject,
                    info.issuer,
                    info.not_before,
                    info.not_after,
                    ",".join(info.sans),
                    int(info.is_self_signed),
                    _now(),
                ),
            )
            self._conn.commit()
        return self.get_certificate(cert_id)  # type: ignore[return-value]

    def generate_certificate(
        self, *, name: str, common_name: str, sans: list[str], days: int, key_size: int
    ) -> Certificate:
        cert_pem, key_pem = cert_service.generate_self_signed(
            common_name=common_name, sans=sans, days=days, key_size=key_size
        )
        info = cert_service.inspect(cert_pem)
        return self._store_certificate(name, cert_pem, key_pem, info)

    def upload_certificate(
        self, *, name: str, cert_pem: str, key_pem: str
    ) -> Certificate:
        info = cert_service.validate_pair(cert_pem, key_pem)
        return self._store_certificate(name, cert_pem, key_pem, info)

    def activate_certificate(self, cert_id: str) -> None:
        if self.get_certificate(cert_id) is None:
            raise ValueError("No such certificate.")
        with self._lock:
            self._set_config("active_cert_id", cert_id)
            self._conn.commit()
        self._materialise_active_cert()

    def delete_certificate(self, cert_id: str) -> None:
        with self._lock:
            if self._get_config("active_cert_id") == cert_id:
                self._conn.execute(
                    "DELETE FROM security_config WHERE key = 'active_cert_id'"
                )
            self._conn.execute("DELETE FROM certificates WHERE id = ?", (cert_id,))
            self._conn.commit()
        self._materialise_active_cert()

    def _materialise_active_cert(self) -> None:
        """Write (or clear) the active certificate on disk for the TLS listener."""
        with self._lock:
            cert_id = self._get_config("active_cert_id")
            row = (
                self._conn.execute(
                    "SELECT cert_pem, key_enc FROM certificates WHERE id = ?",
                    (cert_id,),
                ).fetchone()
                if cert_id
                else None
            )
        if row is None:
            ACTIVE_CERT_PATH.unlink(missing_ok=True)
            ACTIVE_KEY_PATH.unlink(missing_ok=True)
            return
        ACTIVE_CERT_PATH.write_text(row["cert_pem"], encoding="utf-8")
        ACTIVE_KEY_PATH.write_text(decrypt_text(row["key_enc"]), encoding="utf-8")
        ACTIVE_CERT_PATH.chmod(0o600)
        ACTIVE_KEY_PATH.chmod(0o600)

    # ── connections & assignments ────────────────────────────────────────────

    def _row_to_connection(self, row: sqlite3.Row, *, with_secrets: bool) -> Connection:
        assignments = [
            r["username"]
            for r in self._conn.execute(
                "SELECT username FROM connection_assignments WHERE connection_id = ? "
                "ORDER BY LOWER(username)",
                (row["id"],),
            ).fetchall()
        ]
        return Connection(
            id=row["id"],
            name=row["name"],
            comment=row["comment"] or "",
            host=row["host"] or "",
            port=row["port"] or 8563,
            username=row["username"] or "",
            schema=row["db_schema"] or "",
            use_tls=bool(row["use_tls"]),
            cert_mode=row["cert_mode"] or "verify",
            fingerprint=row["fingerprint"] or "",
            min_rsa_bits=row["min_rsa_bits"] or 2048,
            password=decrypt_text(row["password_enc"]) if with_secrets and row["password_enc"] else "",
            llm_url=row["llm_url"] or "",
            llm_model=row["llm_model"] or "",
            llm_api_key=decrypt_text(row["llm_key_enc"]) if with_secrets and row["llm_key_enc"] else "",
            assignments=assignments,
            has_password=bool(row["password_enc"]),
            has_llm_key=bool(row["llm_key_enc"]),
            owner=(row["owner"] if "owner" in row.keys() else "") or "",
            created_at=row["created_at"],
            use_materialized_transitions=bool(
                row["use_materialized_transitions"]
                if "use_materialized_transitions" in row.keys()
                else 0
            ),
        )

    def list_connections(self) -> list[Connection]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM connections ORDER BY LOWER(name)"
            ).fetchall()
            return [self._row_to_connection(r, with_secrets=False) for r in rows]

    def connections_for_user(self, username: str | None) -> list[Connection]:
        """Connections assigned to `username`. When `username` is None (sign-in not
        required), every connection is visible."""
        with self._lock:
            if username is None:
                rows = self._conn.execute(
                    "SELECT * FROM connections ORDER BY LOWER(name)"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT c.* FROM connections c "
                    "JOIN connection_assignments a ON a.connection_id = c.id "
                    "WHERE LOWER(a.username) = LOWER(?) ORDER BY LOWER(c.name)",
                    (username,),
                ).fetchall()
            return [self._row_to_connection(r, with_secrets=False) for r in rows]

    def get_connection(self, conn_id: str, *, with_secrets: bool = False) -> Connection | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM connections WHERE id = ?", (conn_id,)
            ).fetchone()
            return self._row_to_connection(row, with_secrets=with_secrets) if row else None

    def user_can_use(self, conn_id: str, username: str | None) -> bool:
        if username is None:
            return True
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM connection_assignments "
                "WHERE connection_id = ? AND LOWER(username) = LOWER(?)",
                (conn_id, username),
            ).fetchone()
        return row is not None

    def connections_owned_by(self, username: str) -> list[Connection]:
        """Connections a power user created and may edit/delete/re-assign."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM connections WHERE LOWER(owner) = LOWER(?) ORDER BY LOWER(name)",
                (username,),
            ).fetchall()
            return [self._row_to_connection(r, with_secrets=False) for r in rows]

    def can_manage_connection(self, conn_id: str, username: str | None) -> bool:
        """True if `username` may edit/delete/re-assign the connection: an admin,
        or the power user who owns it."""
        user = self.get_user(username) if username else None
        if user is None or not user.is_enabled:
            return False
        if user.is_admin:
            return True
        conn = self.get_connection(conn_id)
        return (
            user.is_power
            and conn is not None
            and conn.owner.strip().lower() == user.username.lower()
        )

    def upsert_connection(self, data: dict) -> Connection:
        """Create or update a connection. `data` uses the admin_public field names.
        Secrets are only written when present: pass ``password`` / ``llmKey`` to set
        them, omit to keep the stored value, or pass an empty string to clear."""
        conn_id = data.get("id") or str(uuid.uuid4())
        with self._lock:
            existing = self._conn.execute(
                "SELECT password_enc, llm_key_enc FROM connections WHERE id = ?",
                (conn_id,),
            ).fetchone()

            if "password" in data:
                pw = data["password"] or ""
                password_enc = encrypt_text(pw) if pw else ""
            else:
                password_enc = existing["password_enc"] if existing else ""

            if "llmKey" in data:
                key = data["llmKey"] or ""
                llm_key_enc = encrypt_text(key) if key else ""
            else:
                llm_key_enc = existing["llm_key_enc"] if existing else ""

            self._conn.execute(
                """
                INSERT INTO connections
                    (id, name, comment, host, port, username, db_schema, use_tls,
                     cert_mode, fingerprint, min_rsa_bits, password_enc,
                     llm_url, llm_model, llm_key_enc, owner,
                     use_materialized_transitions, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, comment=excluded.comment, host=excluded.host,
                    port=excluded.port, username=excluded.username, db_schema=excluded.db_schema,
                    use_tls=excluded.use_tls, cert_mode=excluded.cert_mode,
                    fingerprint=excluded.fingerprint, min_rsa_bits=excluded.min_rsa_bits,
                    password_enc=excluded.password_enc, llm_url=excluded.llm_url,
                    llm_model=excluded.llm_model, llm_key_enc=excluded.llm_key_enc,
                    use_materialized_transitions=excluded.use_materialized_transitions
                """,
                (
                    conn_id,
                    (data.get("name") or "").strip() or "Connection",
                    data.get("comment") or "",
                    data.get("host") or "",
                    int(data.get("port") or 8563),
                    data.get("username") or "",
                    data.get("schema") or "",
                    int(bool(data.get("useTLS"))),
                    data.get("certModeRaw") or "verify",
                    data.get("fingerprint") or "",
                    int(data.get("minRSAKeySizeBits") or 2048),
                    password_enc,
                    data.get("llmURL") or "",
                    data.get("llmModel") or "",
                    llm_key_enc,
                    (data.get("owner") or "").strip(),  # only applied on INSERT (immutable after)
                    int(bool(data.get("useMaterializedTransitions"))),
                    _now(),
                ),
            )
            if "assignments" in data:
                self._conn.execute(
                    "DELETE FROM connection_assignments WHERE connection_id = ?", (conn_id,)
                )
                for user in dict.fromkeys(data["assignments"] or []):
                    if self.get_user(user) is not None:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO connection_assignments (connection_id, username) "
                            "VALUES (?, ?)",
                            (conn_id, user),
                        )
            self._conn.commit()
        return self.get_connection(conn_id)  # type: ignore[return-value]

    def set_assignments(self, conn_id: str, usernames: list[str]) -> None:
        if self.get_connection(conn_id) is None:
            raise ValueError("No such connection.")
        with self._lock:
            self._conn.execute(
                "DELETE FROM connection_assignments WHERE connection_id = ?", (conn_id,)
            )
            for user in dict.fromkeys(usernames):
                if self.get_user(user) is not None:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO connection_assignments (connection_id, username) "
                        "VALUES (?, ?)",
                        (conn_id, user),
                    )
            self._conn.commit()

    def delete_connection(self, conn_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM connection_assignments WHERE connection_id = ?", (conn_id,)
            )
            self._conn.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
            self._conn.commit()

    # ── effective TLS plan (read by the GUI launcher) ─────────────────────────

    def tls_plan(self) -> dict:
        """Describe how the GUI server should bind, given the current config."""
        mode = self.tls_mode
        self._materialise_active_cert()  # keep disk in sync on read
        has_cert = ACTIVE_CERT_PATH.exists() and ACTIVE_KEY_PATH.exists()
        return {
            "mode": mode,
            "hasActiveCert": has_cert,
            "http": mode in (TLS_OFF, TLS_OPTIONAL) or not has_cert,
            "https": mode in (TLS_OPTIONAL, TLS_REQUIRED) and has_cert,
            "certPath": str(ACTIVE_CERT_PATH) if has_cert else None,
            "keyPath": str(ACTIVE_KEY_PATH) if has_cert else None,
        }


store = SecurityStore()
