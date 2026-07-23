"""Connection management endpoints — DatabaseServer / LLMServer / profile CRUD."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
    reachable = await check_llm_reachable(server)
    if not reachable:
        return {"error": "Server not reachable.", "models": []}
    models = await llm_service.list_models(server.serverURL, server.apiKey)
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
