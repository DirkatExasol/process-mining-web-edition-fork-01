"""MCP server — a machine-facing surface that lets AI clients (Claude, ChatGPT, …) query
the Process Mining tool over the Model Context Protocol (Streamable-HTTP transport).

Auth: every request carries an OAuth access token issued by an external Authentik server.
The token is a signed JWT, verified OFFLINE against Authentik's JWKS (RS256; issuer +
audience checked). The verified user claim is matched to an enabled Process Mining user;
that user's assigned database connections gate what may be queried — so the MCP surface
never exposes more than the same person could see in the app. Everything here is
READ-ONLY (metrics, paths, metadata); there are no write tools.

The whole surface is off until an administrator enables it (admin panel → MCP Server tab),
and 503s while disabled. OAuth/Authentik settings are configured there too.

This is the 7th surface (admin port + 40). Unlike the browser surfaces it does not use
`build_surface_app` (no cookie sign-in) — MCP clients authenticate with a bearer token.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import jwt  # noqa: E402  (PyJWT[crypto])
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from jwt import PyJWKClient  # noqa: E402

from app.config import MCP_JWKS_CACHE_SECS, MCP_MAX_ROWS  # noqa: E402
from app.db.manager import DatabaseManager  # noqa: E402
from app.db.repository import ProcessRepository  # noqa: E402
from app.models import FilterSpec, SampleSet  # noqa: E402
from app.store.security import store  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("mcp")

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "process-mining", "title": "Process Mining", "version": "1.0.0"}

app = FastAPI(title="Process Mining - MCP Server", docs_url=None, redoc_url=None)


# ── OAuth token validation (offline, against Authentik's JWKS) ─────────────────

# Authentik is an admin-configured, trusted internal host that commonly serves a
# self-signed certificate — mirror the rest of the app (sink / internal TLS), which does
# not verify these internal certs. The JWT signature itself is still verified against the
# fetched key, so token integrity does not depend on the transport.
_JWKS_SSL = ssl.create_default_context()
_JWKS_SSL.check_hostname = False
_JWKS_SSL.verify_mode = ssl.CERT_NONE

_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks_client(uri: str) -> PyJWKClient:
    client = _jwks_clients.get(uri)
    if client is None:
        client = PyJWKClient(
            uri, cache_keys=True, lifespan=MCP_JWKS_CACHE_SECS, ssl_context=_JWKS_SSL
        )
        _jwks_clients[uri] = client
    return client


class AuthError(Exception):
    """401/403 while authenticating the caller. `challenge` → emit WWW-Authenticate."""

    def __init__(self, status: int, message: str, *, challenge: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.challenge = challenge


async def _authenticate(request: Request):
    """Validate the bearer token and return the mapped, enabled Process Mining user.

    Raises AuthError(401, challenge=True) when the token is missing/invalid (so the MCP
    client starts the OAuth flow), 403 when the user is unknown/disabled or not in the
    required group, 503 when OAuth isn't configured yet."""
    s = store.mcp_settings()
    issuer, audience, jwks_uri = s["issuer"].rstrip("/"), s["audience"], s["jwksUri"]
    if not issuer or not jwks_uri:
        raise AuthError(503, "The MCP server's OAuth (Authentik) settings are not configured.")

    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise AuthError(401, "A bearer access token is required.", challenge=True)
    token = header[7:].strip()

    try:
        signing_key = await asyncio.to_thread(
            _jwks_client(jwks_uri).get_signing_key_from_jwt, token
        )
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience or None,
            issuer=issuer or None,
            options={"verify_aud": bool(audience)},
        )
    except AuthError:
        raise
    except Exception as exc:  # noqa: BLE001 — any verification failure is a 401
        raise AuthError(401, f"Invalid access token: {exc}", challenge=True) from exc

    required_group = s["requiredGroup"]
    if required_group and required_group not in (claims.get("groups") or []):
        raise AuthError(403, "Your account is not in the group required for MCP access.")

    claim = s["usernameClaim"] or "preferred_username"
    username = claims.get(claim) or claims.get("preferred_username") or claims.get("email")
    if not username:
        raise AuthError(401, f"The token carries no '{claim}' claim to map to a user.", challenge=True)

    user = store.get_user(str(username))
    if user is None or not user.is_enabled:
        raise AuthError(403, f"No enabled Process Mining user matches '{username}'.")
    return user


# ── running queries as the mapped user, on one of their connections ────────────


class _Repo:
    """Open a fresh Exasol connection for `username` on `connection_id` (which they must
    be assigned), yield a ProcessRepository, and always close it. One connection per call
    — MCP traffic is interactive, not high-frequency."""

    def __init__(self, username: str, connection_id: str, sample_set: SampleSet):
        self.username, self.connection_id, self.sample_set = username, connection_id, sample_set
        self.mgr: DatabaseManager | None = None

    async def __aenter__(self) -> ProcessRepository:
        if not store.user_can_use(self.connection_id, self.username):
            raise ToolError(f"Connection {self.connection_id!r} is not assigned to you.")
        conn_def = store.get_connection(self.connection_id, with_secrets=True)
        if conn_def is None:
            raise ToolError(f"Connection {self.connection_id!r} was not found.")
        mgr = DatabaseManager(load_legacy_active=False)
        err = await mgr.connect_connection(conn_def)
        if err:
            raise ToolError(f"Could not open the database connection: {err}")
        mgr.use_materialized_transitions = conn_def.use_materialized_transitions
        self.mgr = mgr
        repo = ProcessRepository(mgr)
        repo.active_sample_set = self.sample_set
        return repo

    async def __aexit__(self, *exc: Any) -> None:
        if self.mgr is not None:
            await self.mgr.disconnect()


class ToolError(Exception):
    """A tool could not complete (bad args, unknown connection/project, DB error)."""


def _dump(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    return obj


def _filter_spec(args: dict) -> FilterSpec:
    """Build the read filter every query tool accepts (a subset of the app's FilterSpec)."""
    try:
        sample = SampleSet(args.get("sampleSet") or "ORIGINAL")
    except ValueError:
        raise ToolError(f"Unknown sampleSet {args.get('sampleSet')!r}.")
    return FilterSpec(
        fromDate=args.get("fromDate") or None,
        toDate=args.get("toDate") or None,
        includedSteps=list(args.get("includedSteps") or []),
        excludedSteps=list(args.get("excludedSteps") or []),
        meta1=args.get("meta1") or "",
        meta2=args.get("meta2") or "",
        meta3=args.get("meta3") or "",
        sampleSet=sample,
    )


def _sample_of(args: dict) -> SampleSet:
    try:
        return SampleSet(args.get("sampleSet") or "ORIGINAL")
    except ValueError:
        raise ToolError(f"Unknown sampleSet {args.get('sampleSet')!r}.")


def _project_id(args: dict) -> str:
    pid = args.get("projectId")
    if pid is None:
        raise ToolError("projectId is required.")
    return str(pid)


def _conn_id(args: dict) -> str:
    cid = args.get("connectionId")
    if not cid:
        raise ToolError("connectionId is required.")
    return str(cid)


# ── the read-only tools ────────────────────────────────────────────────────────

_FILTER_PROPS = {
    "sampleSet": {"type": "string", "enum": [s.value for s in SampleSet],
                  "description": "Which data set to query (default ORIGINAL)."},
    "fromDate": {"type": "string", "description": "ISO date; include journeys on/after it."},
    "toDate": {"type": "string", "description": "ISO date; include journeys on/before it."},
    "includedSteps": {"type": "array", "items": {"type": "string"},
                      "description": "Keep only journeys visiting all of these steps."},
    "excludedSteps": {"type": "array", "items": {"type": "string"},
                      "description": "Drop journeys visiting any of these steps."},
    "meta1": {"type": "string"}, "meta2": {"type": "string"}, "meta3": {"type": "string"},
}
_CONN = {"connectionId": {"type": "string", "description": "A connection id from list_connections."}}
_PROJ = {"projectId": {"type": "integer", "description": "A project id from list_projects."}}


async def _tool_list_connections(user, args) -> Any:
    return [
        {"id": c.id, "name": c.name, "schema": c.schema, "comment": c.comment}
        for c in store.connections_for_user(user.username)
    ]


async def _tool_list_projects(user, args) -> Any:
    async with _Repo(user.username, _conn_id(args), SampleSet.original) as repo:
        return _dump(await repo.load_projects())


async def _tool_get_process_map(user, args) -> Any:
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        graph = await repo.load_graph(_project_id(args), _filter_spec(args))
        return _dump(graph)


async def _tool_get_transition_metrics(user, args) -> Any:
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        return _dump(await repo.load_transitions(_project_id(args), _filter_spec(args)))


async def _tool_get_variants(user, args) -> Any:
    limit = min(int(args.get("limit") or 100), MCP_MAX_ROWS)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        return _dump(await repo.load_journey_paths(_project_id(args), _filter_spec(args), limit))


async def _tool_get_statistics(user, args) -> Any:
    pid, spec = _project_id(args), _filter_spec(args)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        count = await repo.load_journey_count(pid, spec)
        durations = await repo.load_journey_duration_stats(pid, spec)
        goodness = await repo.load_process_goodness(pid, spec)
        return {
            "journeyCount": count,
            "durations": _dump(durations),
            "processGoodness": None if goodness is None else goodness[0],
        }


async def _tool_get_metadata(user, args) -> Any:
    pid = _project_id(args)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        m1, m2, m3 = await repo.load_meta_titles(pid)
        steps = await repo.load_all_step_names(pid)
        frm, to = await repo.load_date_bounds(pid)
        return {
            "metaTitles": {"meta1": m1, "meta2": m2, "meta3": m3},
            "steps": steps,
            "dateRange": {
                "from": frm.isoformat() if frm else None,
                "to": to.isoformat() if to else None,
            },
        }


_TOOLS: list[dict] = [
    {"name": "list_connections", "handler": _tool_list_connections,
     "description": "List the database connections you may query (id, name, schema).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_projects", "handler": _tool_list_projects,
     "description": "List the process-mining projects on a connection.",
     "inputSchema": {"type": "object", "properties": {**_CONN}, "required": ["connectionId"]}},
    {"name": "get_process_map", "handler": _tool_get_process_map,
     "description": "The directly-follows process map for a project: steps (nodes) and "
                    "transitions (edges) with occurrence counts and timing.",
     "inputSchema": {"type": "object", "properties": {**_CONN, **_PROJ, **_FILTER_PROPS},
                     "required": ["connectionId", "projectId"]}},
    {"name": "get_transition_metrics", "handler": _tool_get_transition_metrics,
     "description": "The transition table: for each step pair, count and avg/min/max/stddev "
                    "transition time (seconds).",
     "inputSchema": {"type": "object", "properties": {**_CONN, **_PROJ, **_FILTER_PROPS},
                     "required": ["connectionId", "projectId"]}},
    {"name": "get_variants", "handler": _tool_get_variants,
     "description": "The distinct journey paths (variants) and how often each occurs, "
                    "most frequent first.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "limit": {"type": "integer", "description": f"Max variants (<= {MCP_MAX_ROWS})."}},
         "required": ["connectionId", "projectId"]}},
    {"name": "get_statistics", "handler": _tool_get_statistics,
     "description": "Project KPIs for the filter: journey count, journey-duration stats "
                    "and the process-goodness score.",
     "inputSchema": {"type": "object", "properties": {**_CONN, **_PROJ, **_FILTER_PROPS},
                     "required": ["connectionId", "projectId"]}},
    {"name": "get_metadata", "handler": _tool_get_metadata,
     "description": "Project metadata: the three meta-attribute titles, the step names, "
                    "and the event date range.",
     "inputSchema": {"type": "object", "properties": {**_CONN, **_PROJ},
                     "required": ["connectionId", "projectId"]}},
]
_TOOLS_BY_NAME = {t["name"]: t for t in _TOOLS}


# ── MCP JSON-RPC dispatch (Streamable-HTTP transport) ──────────────────────────


def _rpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def _dispatch(message: dict, user) -> dict | None:
    """Handle one JSON-RPC message. Returns a response dict, or None for a notification."""
    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}

    if req_id is None:  # a notification (e.g. notifications/initialized) — no response
        return None

    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _rpc_result(req_id, {})
    if method == "tools/list":
        return _rpc_result(req_id, {"tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in _TOOLS
        ]})
    if method == "tools/call":
        name = params.get("name")
        tool = _TOOLS_BY_NAME.get(name)
        if tool is None:
            return _rpc_error(req_id, -32602, f"Unknown tool: {name}")
        args = params.get("arguments") or {}
        try:
            payload = await tool["handler"](user, args)
        except ToolError as exc:
            return _rpc_result(req_id, {
                "content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:  # noqa: BLE001 — surface as a tool error, keep serving
            log.exception("MCP tool %s failed", name)
            return _rpc_result(req_id, {
                "content": [{"type": "text", "text": f"Tool failed: {exc}"}], "isError": True})
        import json as _json
        return _rpc_result(req_id, {
            "content": [{"type": "text", "text": _json.dumps(payload, ensure_ascii=False)}],
            "isError": False,
        })
    return _rpc_error(req_id, -32601, f"Method not found: {method}")


def _external_base(request: Request) -> str:
    """The externally visible base URL. Behind a reverse proxy (the usual deployment —
    the MCP server sits on its own port and a proxy forwards a public path to it) the
    proxy must send X-Forwarded-Proto / X-Forwarded-Host; we honour them so the OAuth
    discovery documents advertise the public URL, not the internal host:port."""
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    return f"{proto}://{host}" if host else str(request.base_url).rstrip("/")


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    if not store.mcp_enabled:
        return JSONResponse({"error": "The MCP server is disabled."}, status_code=503)
    try:
        user = await _authenticate(request)
    except AuthError as exc:
        headers = {}
        if exc.challenge:
            meta = _external_base(request) + "/.well-known/oauth-protected-resource"
            headers["WWW-Authenticate"] = f'Bearer resource_metadata="{meta}"'
        return JSONResponse({"error": exc.message}, status_code=exc.status, headers=headers)

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=400)

    # A batch (list) or a single message.
    if isinstance(body, list):
        responses = [r for m in body if (r := await _dispatch(m, user)) is not None]
        return JSONResponse(responses) if responses else JSONResponse(None, status_code=202)
    response = await _dispatch(body, user)
    if response is None:
        return JSONResponse(None, status_code=202)  # notification acknowledged
    return JSONResponse(response)


@app.get("/mcp")
async def mcp_get() -> JSONResponse:
    # No server-initiated streaming — this server only answers POSTed requests.
    return JSONResponse({"error": "Method Not Allowed; POST JSON-RPC to this endpoint."},
                        status_code=405)


# Also answer at the ROOT, so a reverse proxy that forwards a public `/mcp` path to this
# backend AND strips the prefix (nginx `proxy_pass http://backend/;`) still reaches the
# handler — the request then arrives here as `/` rather than `/mcp`.
app.add_api_route("/", mcp_endpoint, methods=["POST"])
app.add_api_route("/", mcp_get, methods=["GET"])


# ── discovery + health (unauthenticated) ───────────────────────────────────────


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata(request: Request) -> JSONResponse:
    """RFC 9728 metadata: tells the MCP client which authorization server (Authentik)
    guards this resource, so it can run the OAuth flow on its own. Served at both the bare
    well-known path and the resource-suffixed one (`…/mcp`), since clients differ."""
    s = store.mcp_settings()
    return JSONResponse({
        "resource": _external_base(request) + "/mcp",
        "authorization_servers": [s["issuer"]] if s["issuer"] else [],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "profile", "email"],
    })


@app.get("/health")
async def health() -> dict:
    # Liveness only — no identifying detail.
    return {"ok": True, "enabled": store.mcp_enabled}
