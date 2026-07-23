"""Exasol connection management — the port of DatabaseManager.swift.

pyexasol is synchronous and a single `ExaConnection` is not safe for concurrent
statements, which mirrors the Swift `ExasolConnection` constraint. Every query is
therefore serialised through one lock and executed in a worker thread so the
event loop stays free.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import threading
from typing import Any

import pyexasol

from ..models import ConnectionProfile, DatabaseServer, LLMServer
from ..store.settings import store

log = logging.getLogger(__name__)

KEY_DB_SERVERS = "database_servers"
KEY_LLM_SERVERS = "llm_servers"
KEY_PROFILES = "connection_profiles"
KEY_ACTIVE_PROFILE = "active_profile_id"


def _pw_key(server_id: str) -> str:
    return f"conn_pw_{server_id}"


def _api_key_key(server_id: str) -> str:
    return f"llm_api_key_{server_id}"


class QueryResult:
    """Rows plus column names, mirroring the Swift `QueryResult`."""

    __slots__ = ("rows", "columns")

    def __init__(self, rows: list[list[Any]], columns: list[str]) -> None:
        self.rows = rows
        self.columns = columns


class ExasolError(RuntimeError):
    pass


class DatabaseManager:
    """Singleton holding the one live Exasol connection plus server definitions."""

    def __init__(self) -> None:
        self._conn: pyexasol.ExaConnection | None = None
        self._lock = threading.Lock()
        self.is_connected = False
        self.is_llm_reachable = False
        self.active_profile_id: str | None = store.get(KEY_ACTIVE_PROFILE)
        self.last_error: str | None = None
        # Set when connected via an admin-defined connection (the current model).
        self._active_db_server: DatabaseServer | None = None
        self._active_llm_server: LLMServer | None = None

    # ── persisted definitions ────────────────────────────────────────────────

    @property
    def database_servers(self) -> list[DatabaseServer]:
        return [DatabaseServer(**d) for d in store.get(KEY_DB_SERVERS, [])]

    @database_servers.setter
    def database_servers(self, value: list[DatabaseServer]) -> None:
        store.set(KEY_DB_SERVERS, [s.model_dump(by_alias=True) for s in value])

    @property
    def llm_servers(self) -> list[LLMServer]:
        servers = []
        for d in store.get(KEY_LLM_SERVERS, []):
            s = LLMServer(**d)
            # API keys live in the encrypted vault, never in the kv table.
            s.apiKey = store.get_secret(_api_key_key(s.id))
            servers.append(s)
        return servers

    @llm_servers.setter
    def llm_servers(self, value: list[LLMServer]) -> None:
        stripped = []
        for s in value:
            store.set_secret(_api_key_key(s.id), s.apiKey or "")
            d = s.model_dump(by_alias=True)
            d["apiKey"] = ""
            stripped.append(d)
        store.set(KEY_LLM_SERVERS, stripped)

    @property
    def profiles(self) -> list[ConnectionProfile]:
        return [ConnectionProfile(**d) for d in store.get(KEY_PROFILES, [])]

    @profiles.setter
    def profiles(self, value: list[ConnectionProfile]) -> None:
        store.set(KEY_PROFILES, [p.model_dump(by_alias=True) for p in value])

    # ── resolvers ────────────────────────────────────────────────────────────

    def profile(self, profile_id: str | None) -> ConnectionProfile | None:
        if not profile_id:
            return None
        return next((p for p in self.profiles if p.id == profile_id), None)

    @property
    def active_profile(self) -> ConnectionProfile | None:
        return self.profile(self.active_profile_id)

    def database_server(self, profile: ConnectionProfile | None) -> DatabaseServer | None:
        if profile is None or not profile.databaseServerId:
            return None
        return next(
            (s for s in self.database_servers if s.id == profile.databaseServerId), None
        )

    def llm_server(self, profile: ConnectionProfile | None) -> LLMServer | None:
        if profile is None or not profile.llmServerId:
            return None
        return next((s for s in self.llm_servers if s.id == profile.llmServerId), None)

    @property
    def active_database_server(self) -> DatabaseServer | None:
        if self._active_db_server is not None:
            return self._active_db_server
        return self.database_server(self.active_profile)

    @property
    def active_llm_server(self) -> LLMServer | None:
        if self._active_db_server is not None:  # admin-connection path
            return self._active_llm_server
        return self.llm_server(self.active_profile)

    @property
    def username(self) -> str:
        server = self.active_database_server
        return server.username if server else ""

    # ── passwords ────────────────────────────────────────────────────────────

    def password(self, server_id: str) -> str:
        return store.get_secret(_pw_key(server_id))

    def set_password(self, server_id: str, password: str) -> None:
        store.set_secret(_pw_key(server_id), password)

    def delete_password(self, server_id: str) -> None:
        store.delete_secret(_pw_key(server_id))

    # ── connecting ───────────────────────────────────────────────────────────

    def _connect_kwargs(self, server: DatabaseServer, password: str) -> dict[str, Any]:
        dsn = f"{server.host}:{server.port}"
        kwargs: dict[str, Any] = {
            "user": server.username,
            "password": password,
            "compression": True,
            "fetch_dict": False,
            "connection_timeout": 15,
            "socket_timeout": 300,
        }
        if server.schema_:
            kwargs["schema"] = server.schema_

        if server.useTLS:
            kwargs["encryption"] = True
            mode = (server.certModeRaw or "verify").lower()
            fingerprint = (server.fingerprint or "").replace(":", "").strip()
            if mode == "fingerprint" and fingerprint:
                # pyexasol pins the certificate when the DSN carries a fingerprint.
                dsn = f"{server.host}/{fingerprint}:{server.port}"
            elif mode != "verify":
                kwargs["websocket_sslopt"] = {
                    "cert_reqs": ssl.CERT_NONE,
                    "check_hostname": False,
                }
        else:
            kwargs["encryption"] = False

        kwargs["dsn"] = dsn
        return kwargs

    def _open(self, server: DatabaseServer, password: str) -> pyexasol.ExaConnection:
        return pyexasol.connect(**self._connect_kwargs(server, password))

    async def connect(self, profile: ConnectionProfile) -> str | None:
        """Connect and remember the profile. Returns an error message or None."""
        self.active_profile_id = profile.id
        store.set(KEY_ACTIVE_PROFILE, profile.id)
        self.last_error = None

        server = self.database_server(profile)
        if server is None:
            msg = (
                "This connection has no database server selected. "
                "Edit it and choose one."
            )
            self.last_error = msg
            self.is_connected = False
            return msg

        await self.disconnect()
        password = self.password(server.id)
        try:
            conn = await asyncio.to_thread(self._open, server, password)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user verbatim
            msg = friendly_error(exc)
            self.last_error = msg
            self.is_connected = False
            return msg

        self._conn = conn
        self.is_connected = True
        self._active_db_server = None
        self._active_llm_server = None
        self.is_llm_reachable = await check_llm_reachable(self.llm_server(profile))
        return None

    async def connect_connection(self, conn_def) -> str | None:
        """Connect using an admin-defined `Connection` (from the security store).

        `conn_def` must carry its decrypted secrets. Returns an error or None.
        """
        server = DatabaseServer(
            id=conn_def.id,
            name=conn_def.name,
            host=conn_def.host,
            port=conn_def.port,
            username=conn_def.username,
            useTLS=conn_def.use_tls,
            certModeRaw=conn_def.cert_mode,
            fingerprint=conn_def.fingerprint,
            minRSAKeySizeBits=conn_def.min_rsa_bits,
            **{"schema": conn_def.schema},
        )
        llm = (
            LLMServer(
                id=conn_def.id,
                name=f"{conn_def.name} LLM",
                serverURL=conn_def.llm_url,
                apiKey=conn_def.llm_api_key,
                model=conn_def.llm_model,
            )
            if conn_def.llm_url.strip()
            else None
        )

        await self.disconnect()
        self.active_profile_id = conn_def.id
        self.last_error = None
        try:
            exa = await asyncio.to_thread(self._open, server, conn_def.password)
        except Exception as exc:  # noqa: BLE001 — surfaced verbatim
            msg = friendly_error(exc)
            self.last_error = msg
            self.is_connected = False
            return msg

        self._conn = exa
        self.is_connected = True
        self._active_db_server = server
        self._active_llm_server = llm
        self.is_llm_reachable = await check_llm_reachable(llm)
        return None

    async def test_server(self, server: DatabaseServer, password: str) -> str | None:
        """Probe credentials without touching the active connection."""

        def _probe() -> None:
            conn = self._open(server, password)
            conn.close()

        try:
            await asyncio.to_thread(_probe)
        except Exception as exc:  # noqa: BLE001
            return friendly_error(exc)
        return None

    async def disconnect(self) -> None:
        conn, self._conn = self._conn, None
        self.is_connected = False
        self.is_llm_reachable = False
        self._active_db_server = None
        self._active_llm_server = None
        if conn is not None:
            try:
                await asyncio.to_thread(conn.close)
            except Exception:  # noqa: BLE001 — already going away
                log.debug("error while closing Exasol connection", exc_info=True)

    # ── query execution ──────────────────────────────────────────────────────

    def _execute_sync(self, sql: str) -> QueryResult:
        with self._lock:
            conn = self._conn
            if conn is None:
                raise ExasolError("Not connected.")
            stmt = conn.execute(sql)
            columns = list(stmt.column_names())
            rows = [list(r) for r in stmt.fetchall()] if stmt.result_type == "resultSet" else []
            return QueryResult(rows, columns)

    async def execute(self, sql: str, timeout: float | None = None) -> QueryResult:
        coro = asyncio.to_thread(self._execute_sync, sql)
        if timeout is None:
            return await coro
        return await asyncio.wait_for(coro, timeout=timeout)

    async def execute_quiet(self, sql: str) -> QueryResult | None:
        """Run a statement whose failure is acceptable (DDL migrations)."""
        try:
            return await self.execute(sql)
        except Exception:  # noqa: BLE001
            log.debug("ignored failing statement: %s", sql, exc_info=True)
            return None


def friendly_error(exc: Exception) -> str:
    """Port of DatabaseManager.friendlyError — turns driver noise into guidance."""
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()

    if isinstance(exc, pyexasol.ExaAuthError) or "authentication failed" in lowered:
        return f"Authentication failed — check your username and password. ({text})"
    if isinstance(exc, pyexasol.ExaQueryError):
        code = getattr(exc, "code", "") or ""
        message = getattr(exc, "message", "") or text
        return f"[{code}] {message}" if code else message
    if "timed out" in lowered or "timeout" in lowered:
        return "Connection timed out. Verify the host address, port, and network connectivity."
    if "refused" in lowered:
        return "Connection refused. No server is accepting connections at this host and port."
    if any(k in lowered for k in ("certificate", "trust", "ssl", "tls")):
        return (
            "TLS certificate error. Try 'Skip verification' or configure a "
            f"fingerprint in the server's security settings. ({text})"
        )
    if any(
        k in lowered
        for k in ("no such host", "host not found", "nodename", "name or service")
    ):
        return "Host not found. Check the hostname spelling and your DNS / network connectivity."
    return f"Connection failed: {text}"


async def test_db_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    schema: str = "",
    use_tls: bool = False,
    cert_mode: str = "verify",
    fingerprint: str = "",
    min_rsa_bits: int = 2048,
) -> str | None:
    """Open and immediately close a throwaway Exasol connection. Returns a
    user-friendly error string, or None on success. Usable from any process."""
    server = DatabaseServer(
        id="test",
        host=host,
        port=port,
        username=username,
        useTLS=use_tls,
        certModeRaw=cert_mode,
        fingerprint=fingerprint,
        minRSAKeySizeBits=min_rsa_bits,
        **{"schema": schema},
    )
    mgr = DatabaseManager.__new__(DatabaseManager)  # no store side effects

    def _probe() -> None:
        conn = mgr._open(server, password)
        conn.close()

    try:
        await asyncio.to_thread(_probe)
    except Exception as exc:  # noqa: BLE001
        return friendly_error(exc)
    return None


async def check_llm_reachable(server: LLMServer | None) -> bool:
    """GET {base}/models — same reachability probe the Swift app used."""
    if server is None or not server.serverURL.strip():
        return False
    import httpx

    url = server.serverURL.rstrip("/") + "/models"
    headers = {}
    if server.apiKey.strip():
        headers["Authorization"] = f"Bearer {server.apiKey.strip()}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
        return response.status_code < 500
    except Exception:  # noqa: BLE001
        return False


db = DatabaseManager()
