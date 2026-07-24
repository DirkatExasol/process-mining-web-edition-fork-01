"""Connection management endpoints — DatabaseServer / LLMServer / profile CRUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import log_events as logx
from ..db.manager import check_llm_reachable, db
from ..models import ConnectionProfile, ConnectionStatus, DatabaseServer, LLMServer
from ..services import llm as llm_service
from ..store.security import store as security_store

router = APIRouter(prefix="/api", tags=["connections"])

# The GUI proxy injects the signed-in user here after validating the session; the
# backend trusts it for per-user connection filtering. When absent (sign-in not
# required), the user is unknown and every connection is visible.
USER_HEADER = "x-pmw-user"


def _request_user(request: Request) -> str | None:
    value = request.headers.get(USER_HEADER)
    return value.strip() if value and value.strip() else None


class DatabaseServerPayload(BaseModel):
    server: DatabaseServer
    password: str | None = None


class LLMTestPayload(BaseModel):
    server: LLMServer


# ── database servers ─────────────────────────────────────────────────────────


@router.get("/servers/db", response_model=list[DatabaseServer])
def list_db_servers() -> list[DatabaseServer]:
    return db.database_servers


@router.post("/servers/db", response_model=DatabaseServer)
def upsert_db_server(payload: DatabaseServerPayload) -> DatabaseServer:
    servers = db.database_servers
    index = next((i for i, s in enumerate(servers) if s.id == payload.server.id), None)
    if index is None:
        servers.append(payload.server)
    else:
        servers[index] = payload.server
    db.database_servers = servers
    if payload.password is not None:
        db.set_password(payload.server.id, payload.password)
    return payload.server


@router.get("/servers/db/{server_id}/password")
def get_db_password(server_id: str) -> dict[str, str]:
    """The editor pre-fills the stored password so the user can see it is set."""
    return {"password": db.password(server_id)}


@router.delete("/servers/db/{server_id}")
async def delete_db_server(server_id: str) -> dict[str, bool]:
    if (active := db.active_database_server) and active.id == server_id:
        await db.disconnect()
    db.database_servers = [s for s in db.database_servers if s.id != server_id]
    db.delete_password(server_id)
    profiles = db.profiles
    for profile in profiles:
        if profile.databaseServerId == server_id:
            profile.databaseServerId = None
    db.profiles = profiles
    return {"ok": True}


@router.post("/servers/db/test")
async def test_db_server(payload: DatabaseServerPayload) -> dict[str, str | None]:
    password = payload.password
    if password is None:
        password = db.password(payload.server.id)
    error = await db.test_server(payload.server, password)
    return {"error": error}


# ── LLM servers ──────────────────────────────────────────────────────────────


@router.get("/servers/llm", response_model=list[LLMServer])
def list_llm_servers() -> list[LLMServer]:
    return db.llm_servers


@router.post("/servers/llm", response_model=LLMServer)
def upsert_llm_server(server: LLMServer) -> LLMServer:
    servers = db.llm_servers
    index = next((i for i, s in enumerate(servers) if s.id == server.id), None)
    if index is None:
        servers.append(server)
    else:
        servers[index] = server
    db.llm_servers = servers
    return server


@router.delete("/servers/llm/{server_id}")
def delete_llm_server(server_id: str) -> dict[str, bool]:
    db.llm_servers = [s for s in db.llm_servers if s.id != server_id]
    profiles = db.profiles
    for profile in profiles:
        if profile.llmServerId == server_id:
            profile.llmServerId = None
    db.profiles = profiles
    return {"ok": True}


@router.post("/servers/llm/test")
async def test_llm_server(payload: LLMTestPayload) -> dict[str, object]:
    server = payload.server
    if not server.serverURL.strip():
        return {"error": "Enter a valid server URL.", "models": []}
    reachable = await check_llm_reachable(server)  # logs the real cause on failure
    if not reachable:
        return {"error": "Server not reachable.", "models": []}
    try:
        models = await llm_service.list_models(server.serverURL, server.apiKey)
    except Exception as exc:  # noqa: BLE001
        logx.warn(
            f"LLM server test failed — {server.serverURL}: {exc}",
            operation="llm-test",
        )
        return {"error": str(exc), "models": []}
    return {"error": None, "models": models}


# ── profiles (pairings) ──────────────────────────────────────────────────────


@router.get("/profiles", response_model=list[ConnectionProfile])
def list_profiles() -> list[ConnectionProfile]:
    return db.profiles


@router.post("/profiles", response_model=ConnectionProfile)
def upsert_profile(profile: ConnectionProfile) -> ConnectionProfile:
    profiles = db.profiles
    index = next((i for i, p in enumerate(profiles) if p.id == profile.id), None)
    if index is None:
        profiles.append(profile)
    else:
        profiles[index] = profile
    db.profiles = profiles
    return profile


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, bool]:
    if db.active_profile_id == profile_id:
        await db.disconnect()
    db.profiles = [p for p in db.profiles if p.id != profile_id]
    return {"ok": True}


# ── admin-defined connections (assigned per user) ─────────────────────────────


@router.get("/connections")
def list_connections(request: Request) -> list[dict]:
    """Connections assigned to the signed-in user (secrets stripped)."""
    user = _request_user(request)
    return [c.user_public() for c in security_store.connections_for_user(user)]


@router.post("/connections/{conn_id}/connect", response_model=ConnectionStatus)
async def connect_connection(conn_id: str, request: Request) -> ConnectionStatus:
    user = _request_user(request)
    if not security_store.user_can_use(conn_id, user):
        raise HTTPException(status_code=403, detail="This connection is not available to you.")
    conn_def = security_store.get_connection(conn_id, with_secrets=True)
    if conn_def is None:
        raise HTTPException(status_code=404, detail="Connection not found.")
    error = await db.connect_connection(conn_def)
    return ConnectionStatus(
        isConnected=db.is_connected,
        isLLMReachable=db.is_llm_reachable,
        activeProfileId=db.active_profile_id,
        username=db.username,
        lastError=error,
    )


# ── power users: create & manage their own connections from the app ───────────
#
# A user with the 'power' role (or an admin) may define connections and assign
# them from the main application. Ownership is enforced: a power user manages only
# the connections they created; an admin manages all. The GUI proxy injects the
# trusted X-PMW-User header the checks below rely on.


def _request_user_obj(request: Request):
    username = _request_user(request)
    return security_store.get_user(username) if username else None


def _require_power(request: Request):
    user = _request_user_obj(request)
    if user is None or not user.is_enabled or not (user.is_admin or user.is_power):
        raise HTTPException(
            status_code=403, detail="You are not allowed to manage connections."
        )
    return user


class ManagedConnectionBody(BaseModel):
    id: str | None = None
    name: str
    comment: str = ""
    host: str = ""
    port: int = 8563
    username: str = ""
    schema_: str = Field(default="", alias="schema")
    useTLS: bool = False
    certModeRaw: str = "verify"
    fingerprint: str = ""
    minRSAKeySizeBits: int = 2048
    password: str | None = None  # omit to keep, "" to clear, value to set
    llmURL: str = ""
    llmModel: str = ""
    llmKey: str | None = None
    assignments: list[str] = []

    model_config = {"populate_by_name": True}


class ManagedAssignmentsBody(BaseModel):
    assignments: list[str]


class ManagedConnectionTestBody(BaseModel):
    host: str
    port: int = 8563
    username: str = ""
    password: str = ""
    schema_: str = Field(default="", alias="schema")
    useTLS: bool = False
    certModeRaw: str = "verify"
    fingerprint: str = ""
    minRSAKeySizeBits: int = 2048
    llmURL: str = ""
    llmKey: str = ""

    model_config = {"populate_by_name": True}


def _managed_payload(body: ManagedConnectionBody) -> dict:
    data: dict = {
        "id": body.id,
        "name": body.name,
        "comment": body.comment,
        "host": body.host,
        "port": body.port,
        "username": body.username,
        "schema": body.schema_,
        "useTLS": body.useTLS,
        "certModeRaw": body.certModeRaw,
        "fingerprint": body.fingerprint,
        "minRSAKeySizeBits": body.minRSAKeySizeBits,
        "llmURL": body.llmURL,
        "llmModel": body.llmModel,
        "assignments": body.assignments,
    }
    if body.password is not None:
        data["password"] = body.password
    if body.llmKey is not None:
        data["llmKey"] = body.llmKey
    return data


@router.get("/connections/manageable")
def list_manageable_connections(request: Request) -> list[dict]:
    """Connections the signed-in power user (or admin) may create / edit / assign."""
    user = _require_power(request)
    conns = (
        security_store.list_connections()
        if user.is_admin
        else security_store.connections_owned_by(user.username)
    )
    return [c.admin_public() for c in conns]


@router.get("/assignable-users")
def list_assignable_users(request: Request) -> list[str]:
    """Enabled usernames a power user can assign a connection to."""
    _require_power(request)
    return [u.username for u in security_store.list_users() if u.is_enabled]


@router.post("/connections")
def upsert_managed_connection(body: ManagedConnectionBody, request: Request) -> dict:
    user = _require_power(request)
    data = _managed_payload(body)
    if body.id:
        if not security_store.can_manage_connection(body.id, user.username):
            raise HTTPException(status_code=403, detail="You cannot edit this connection.")
    else:
        # New connection: the power user owns it and is auto-assigned so they can use it.
        data["owner"] = user.username
        data["assignments"] = list(dict.fromkeys([user.username, *(body.assignments or [])]))
    try:
        conn = security_store.upsert_connection(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return conn.admin_public()


@router.delete("/connections/{conn_id}")
async def delete_managed_connection(conn_id: str, request: Request) -> dict:
    user = _require_power(request)
    if not security_store.can_manage_connection(conn_id, user.username):
        raise HTTPException(status_code=403, detail="You cannot delete this connection.")
    if db.active_profile_id == conn_id:
        await db.disconnect()
    security_store.delete_connection(conn_id)
    return {"ok": True}


@router.post("/connections/{conn_id}/assignments")
def set_managed_assignments(
    conn_id: str, body: ManagedAssignmentsBody, request: Request
) -> dict:
    user = _require_power(request)
    if not security_store.can_manage_connection(conn_id, user.username):
        raise HTTPException(status_code=403, detail="You cannot re-assign this connection.")
    try:
        security_store.set_assignments(conn_id, body.assignments)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/connections/test")
async def test_managed_connection(
    body: ManagedConnectionTestBody, request: Request
) -> dict:
    _require_power(request)
    from ..db.manager import test_db_connection

    db_error = await test_db_connection(
        host=body.host,
        port=body.port,
        username=body.username,
        password=body.password,
        schema=body.schema_,
        use_tls=body.useTLS,
        cert_mode=body.certModeRaw,
        fingerprint=body.fingerprint,
        min_rsa_bits=body.minRSAKeySizeBits,
    )
    llm_error: str | None = None
    llm_models: list[str] = []
    if body.llmURL.strip():
        llm = LLMServer(serverURL=body.llmURL, apiKey=body.llmKey)
        if await check_llm_reachable(llm):
            try:
                llm_models = await llm_service.list_models(body.llmURL, body.llmKey)
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
                logx.warn(
                    f"LLM server test failed — {body.llmURL}: {exc}",
                    operation="llm-test",
                )
        else:
            llm_error = "LLM server not reachable."  # check_llm_reachable logged the cause
    return {"dbError": db_error, "llmError": llm_error, "llmModels": llm_models}


@router.post("/connections/provision-schema")
async def provision_managed_schema(body: ManagedConnectionTestBody, request: Request) -> dict:
    """Create the process-mining schema + tables using the supplied credentials.

    Requires elevated database privileges (CREATE SCHEMA / CREATE TABLE) that only a
    database administrator can grant — the app cannot. Returns {ok, error, created}.
    """
    _require_power(request)
    from ..db.schema_ddl import provision_process_mining_schema

    return await provision_process_mining_schema(
        host=body.host,
        port=body.port,
        username=body.username,
        password=body.password,
        schema=body.schema_,
        use_tls=body.useTLS,
        cert_mode=body.certModeRaw,
        fingerprint=body.fingerprint,
        min_rsa_bits=body.minRSAKeySizeBits,
    )


class DemoContentBody(ManagedConnectionTestBody):
    journeys: int = 500
    dataset: str = "retail"  # "retail" (Online Bookstore) | "finance" (Credit Application)


@router.post("/connections/generate-demo")
async def generate_demo_content(body: DemoContentBody, request: Request) -> dict:
    """Provision the schema + tables and load a demo event log (retail or finance).

    Requires elevated database privileges (CREATE SCHEMA / CREATE TABLE / INSERT) that
    only a database administrator can grant — the app cannot. Returns
    {ok, error, journeys, project, dataset, message}.
    """
    _require_power(request)
    from ..db.demo_data import generate_demo_content as _generate

    return await _generate(
        dataset=body.dataset,
        host=body.host,
        port=body.port,
        username=body.username,
        password=body.password,
        schema=body.schema_,
        journeys=body.journeys,
        use_tls=body.useTLS,
        cert_mode=body.certModeRaw,
        fingerprint=body.fingerprint,
        min_rsa_bits=body.minRSAKeySizeBits,
    )


# ── connect / disconnect / status ────────────────────────────────────────────


@router.post("/profiles/{profile_id}/connect", response_model=ConnectionStatus)
async def connect(profile_id: str) -> ConnectionStatus:
    profile = db.profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    error = await db.connect(profile)
    return ConnectionStatus(
        isConnected=db.is_connected,
        isLLMReachable=db.is_llm_reachable,
        activeProfileId=db.active_profile_id,
        username=db.username,
        lastError=error,
    )


@router.post("/disconnect", response_model=ConnectionStatus)
async def disconnect() -> ConnectionStatus:
    await db.disconnect()
    return ConnectionStatus(activeProfileId=db.active_profile_id)


@router.get("/connection/status", response_model=ConnectionStatus)
def status() -> ConnectionStatus:
    return ConnectionStatus(
        isConnected=db.is_connected,
        isLLMReachable=db.is_llm_reachable,
        activeProfileId=db.active_profile_id,
        username=db.username,
        lastError=db.last_error,
    )
