"""MCP server — a machine-facing surface that lets AI clients (Claude, ChatGPT, …) query
the Process Mining tool over the Model Context Protocol (Streamable-HTTP transport).

Auth: every request carries an OAuth access token issued by an external Authentik server.
The token is a signed JWT, verified OFFLINE against Authentik's JWKS (RS256; issuer +
audience checked). The verified user claim is matched to an enabled Process Mining user;
that user's assigned database connections gate what may be queried — so the MCP surface
never exposes more than the same person could see in the app.

Everything here is READ-ONLY except the two note tools (create_note / update_note), the
only writes on this surface. They follow the app's own note rules (author = the token's
user, append-only threads, owner-only severity/scope), validate every field server-side,
and are rate-limited per user. The deeper-analysis tools (compare_segments,
get_bottlenecks, get_trend, get_outcome_drivers, check_conformance) are reserved for
power users (and administrators); anyone else gets a polite refusal.

Timestamps the server creates or reports for notes are local wall-clock time in the
display zone set in the Admin Console, and are returned with that zone's UTC offset.

The whole surface is off until an administrator enables it (admin panel → MCP Server tab),
and 503s while disabled. OAuth/Authentik settings are configured there too.

This is the 7th surface (admin port + 40). Unlike the browser surfaces it does not use
`build_surface_app` (no cookie sign-in) — MCP clients authenticate with a bearer token.
"""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import jwt  # noqa: E402  (PyJWT[crypto])
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from jwt import PyJWKClient  # noqa: E402

from app import log_events as logx  # noqa: E402
from app.config import (  # noqa: E402
    MCP_JWKS_CACHE_SECS,
    MCP_MAX_NOTES_PER_PROJECT,
    MCP_MAX_ROWS,
    MCP_NOTE_WRITES_PER_MIN,
)
from app.db.analysis import MAX_RULES, META_COLUMNS, TREND_UNITS, Analysis, Rule  # noqa: E402
from app.db.manager import DatabaseManager  # noqa: E402
from app.db.repository import JOURNEY_ORDERS, ProcessRepository  # noqa: E402
from app.models import (  # noqa: E402
    NOTE_IMPORTANCE,
    FilterSnapshot,
    FilterSpec,
    NoteTarget,
    ProcessNote,
    SampleSet,
    new_id,
)
from app.services.notes import (  # noqa: E402
    STEP_MAX,
    TEXT_MAX,
    TITLE_MAX,
    clean_text,
    comment_block,
    defang_headers,
    thread_has_room,
)
from app.store.security import store  # noqa: E402
from app.timeutil import local_iso, local_now  # noqa: E402

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
            issuer=[issuer, issuer + "/"] if issuer else None,
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


_MAX_FILTER_STEPS = 200    # steps per includedSteps / excludedSteps list
_MAX_FILTER_STEP_LEN = 2000
_MAX_META_LEN = 256
_MAX_BATCH = 20            # JSON-RPC messages per HTTP request


def _filter_steps(args: dict, key: str) -> list[str]:
    raw = args.get(key)
    if raw in (None, "", []):
        return []
    if isinstance(raw, str):  # one step given as a bare string — not a list of characters
        raw = [raw]
    if not isinstance(raw, list) or len(raw) > _MAX_FILTER_STEPS:
        raise ToolError(f"{key} must be a list of at most {_MAX_FILTER_STEPS} step names.")
    if not all(isinstance(x, str) and 0 < len(x) <= _MAX_FILTER_STEP_LEN for x in raw):
        raise ToolError(f"{key} must contain step names (non-empty strings).")
    return list(raw)


def _filter_meta(args: dict, key: str) -> str:
    raw = args.get(key)
    if raw in (None, ""):
        return ""
    if not isinstance(raw, str) or len(raw) > _MAX_META_LEN:
        raise ToolError(f"{key} must be a string of at most {_MAX_META_LEN} characters.")
    return raw


def _filter_spec(args: dict) -> FilterSpec:
    """Build the read filter every query tool accepts (a subset of the app's FilterSpec).
    Sizes are bounded so one call cannot build an unbounded SQL statement."""
    try:
        sample = SampleSet(args.get("sampleSet") or "ORIGINAL")
    except ValueError:
        raise ToolError(f"Unknown sampleSet {args.get('sampleSet')!r}.")
    try:
        return FilterSpec(
            fromDate=args.get("fromDate") or None,
            toDate=args.get("toDate") or None,
            includedSteps=_filter_steps(args, "includedSteps"),
            excludedSteps=_filter_steps(args, "excludedSteps"),
            meta1=_filter_meta(args, "meta1"),
            meta2=_filter_meta(args, "meta2"),
            meta3=_filter_meta(args, "meta3"),
            sampleSet=sample,
        )
    except ToolError:
        raise
    except Exception:  # noqa: BLE001 — pydantic validation (e.g. a malformed date)
        raise ToolError("fromDate / toDate must be ISO dates (YYYY-MM-DD).") from None


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


async def _projects_on(user, connection, *, include_counts: bool, sample: SampleSet) -> list[dict]:
    """The projects on one connection, each tagged with the connection it came from.

    A connection that cannot be opened yields one entry carrying `error` instead of a
    project, so one unreachable database degrades that row rather than the whole call."""
    try:
        async with _Repo(user.username, connection.id, sample) as repo:
            projects = _dump(await repo.load_projects())
            if include_counts:
                empty = FilterSpec(sampleSet=sample)
                for project in projects:
                    project["journeyCount"] = await repo.load_journey_count(
                        str(project["projectId"]), empty
                    )
    except Exception as exc:  # noqa: BLE001 — report the connection, keep the others
        log.warning("list_projects: connection %s unavailable: %s", connection.id, exc)
        return [{"connectionId": connection.id, "connectionName": connection.name,
                 "error": str(exc)}]
    return [{"connectionId": connection.id, "connectionName": connection.name, **p}
            for p in projects]


async def _tool_list_projects(user, args) -> Any:
    """Projects on one connection, or — with connectionId omitted — on every connection
    the caller may query, so "which process has the most journeys?" is a single call."""
    connections = store.connections_for_user(user.username)
    requested = args.get("connectionId")
    if requested:
        connections = [c for c in connections if c.id == str(requested)]
        if not connections:
            raise ToolError(f"Connection {requested!r} is not assigned to you.")

    include_counts = bool(args.get("includeCounts"))
    sample = _sample_of(args)
    out: list[dict] = []
    for connection in connections:
        out.extend(await _projects_on(user, connection, include_counts=include_counts,
                                      sample=sample))
    return out


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
        # STEPS holds each step's definition (description, score, group, end flag). It is
        # a tiny, cached table — far cheaper than asking for the whole process map.
        try:
            defs = await repo.load_steps(pid)
        except Exception as exc:  # noqa: BLE001 — a missing STEPS row set degrades to names
            log.warning("get_metadata: step definitions unavailable for %s: %s", pid, exc)
            defs = {}
        details = []
        for name in steps:
            d = defs.get(name)
            details.append({
                "step": name,
                "description": d.description if d else None,
                "score": d.score if d else None,
                "belongsTo": d.belongsTo if d else None,
                "endOfProcess": d.endOfProcess if d else False,
                "shape": d.shape if d else None,
            })
        return {
            "metaTitles": {"meta1": m1, "meta2": m2, "meta3": m3},
            "steps": steps,
            "stepDetails": details,
            "dateRange": {
                "from": frm.isoformat() if frm else None,
                "to": to.isoformat() if to else None,
            },
        }


async def _tool_get_journey(user, args) -> Any:
    """One case's ordered trace. The only tool that returns individual events rather
    than an aggregate — everything else here summarises many journeys."""
    pid = _project_id(args)
    raw = str(args.get("eventId") or "").strip()
    if not raw:
        raise ToolError(
            "eventId is required — a business case id (e.g. 'FLT-000123') or the "
            "32-char stored hash."
        )
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        # JOURNEYS never holds the plaintext case id: ingest writes its MD5. Reuse the
        # app's own normalisation so a business id and an already-hashed id both resolve,
        # and so this surface can never disagree with the journey view about identity.
        eid = repo._normalize_event_id(raw)
        info = await repo.load_journey_info(pid, eid)
        if not info or info.get("startDate") is None:
            raise ToolError(f"No journey {raw!r} in project {pid}.")
        events = await repo.load_journey_sequence(pid, eid)
        m1, m2, m3 = await repo.load_meta_titles(pid)
        start, end = info.get("startDate"), info.get("endDate")
        duration = (end - start).total_seconds() if start and end else None
        shown = events[:MCP_MAX_ROWS]
        return {
            "eventId": raw,
            "storedEventId": eid,
            "startDate": start.isoformat() if start else None,
            "endDate": end.isoformat() if end else None,
            "durationSecs": duration,
            "stepCount": len(events),
            "meta": {
                (m1 or "meta1"): info.get("meta1"),
                (m2 or "meta2"): info.get("meta2"),
                (m3 or "meta3"): info.get("meta3"),
            },
            "events": [
                {"step": e["step"], "eventTime": e["eventTime"].isoformat()} for e in shown
            ],
            "truncated": len(events) > len(shown),
        }


async def _tool_find_journeys(user, args) -> Any:
    """The journeys behind an aggregate: the slowest cases, the ones that hit a given
    step, the longest traces. Returns `eventId`s that feed straight into get_journey."""
    pid, spec = _project_id(args), _filter_spec(args)
    limit = min(int(args.get("limit") or 20), MCP_MAX_ROWS)
    order_by = str(args.get("orderBy") or "DURATION_DESC")
    if order_by.upper() not in JOURNEY_ORDERS:
        raise ToolError(
            f"Unknown orderBy {order_by!r}; expected one of {', '.join(JOURNEY_ORDERS)}."
        )
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        rows = await repo.load_journeys(
            pid,
            spec,
            order_by=order_by,
            limit=limit,
            min_duration_secs=args.get("minDurationSecs"),
            max_duration_secs=args.get("maxDurationSecs"),
            min_steps=args.get("minSteps"),
            max_steps=args.get("maxSteps"),
            include_path=bool(args.get("includePath")),
        )
        m1, m2, m3 = await repo.load_meta_titles(pid)
    out = []
    for r in rows:
        entry = {
            # JOURNEYS stores the MD5 of the case id, never the plaintext business id,
            # so this is the stored form — get_journey takes it as-is.
            "eventId": r["eventId"],
            "startDate": r["startDate"].isoformat() if r["startDate"] else None,
            "endDate": r["endDate"].isoformat() if r["endDate"] else None,
            "durationSecs": r["durationSecs"],
            "stepCount": r["stepCount"],
            "meta": {(m1 or "meta1"): r["meta1"], (m2 or "meta2"): r["meta2"],
                     (m3 or "meta3"): r["meta3"]},
        }
        if r["path"] is not None:
            entry["path"] = r["path"]
        out.append(entry)
    return out


# Rank rises with severity (NORMAL < INFO < IMPORTANT < URGENT), so a reverse sort
# puts the most severe first — matching the app's ordering.
_SEVERITY_RANK = {lvl: i for i, lvl in enumerate(NOTE_IMPORTANCE)}


def _note_scope(note) -> str:
    """A note is either 'shared' (visible to everyone) or 'personal' (this caller's own,
    or a legacy unowned note) — the two buckets the app itself distinguishes."""
    return "shared" if note.isShared else "personal"


def _note_dump(note) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "text": note.text,
        "severity": note.importance,                     # NORMAL | INFO | IMPORTANT | URGENT
        "status": "resolved" if note.resolved else "open",
        "scope": _note_scope(note),                      # personal | shared
        "author": note.username or None,
        "target": note.target.display_name,
        "targetType": "edge" if note.target.type == "edge" else "node",
        # Stored as display-zone wall clock; reported with that zone's offset.
        "createdAt": local_iso(note.createdAt),
        "editedAt": local_iso(note.editedAt),
        "lastEditedBy": note.lastEditedBy or None,
    }


async def _tool_get_notes(user, args) -> Any:
    """The notes/annotations on a project's steps and transitions, filterable by severity
    and status and by personal vs shared, and optionally grouped. Visibility is the same as
    the app's: the caller sees shared notes plus their own — never another user's private
    ones (`load_notes` enforces this)."""
    pid = _project_id(args)

    sev_arg = args.get("severity")
    if isinstance(sev_arg, str):
        sev_arg = [sev_arg]
    sev_filter = {str(s).upper() for s in (sev_arg or [])} & set(NOTE_IMPORTANCE)
    status = str(args.get("status") or "all").lower()
    if status not in ("all", "open", "resolved"):
        raise ToolError("status must be one of open, resolved, all.")
    scope = str(args.get("scope") or "all").lower()
    if scope not in ("all", "personal", "shared"):
        raise ToolError("scope must be one of personal, shared, all.")
    group_by = str(args.get("groupBy") or "none").lower()
    if group_by not in ("none", "severity", "status", "scope", "target"):
        raise ToolError("groupBy must be one of severity, status, scope, target, none.")

    async with _Repo(user.username, _conn_id(args), SampleSet.original) as repo:
        try:
            notes = await repo.load_notes(pid, user.username)
        except Exception as exc:  # noqa: BLE001 — NOTES is created lazily; absent ⇒ no notes
            log.warning("get_notes: notes unavailable for project %s: %s", pid, exc)
            notes = []

    def keep(n) -> bool:
        if sev_filter and n.importance.upper() not in sev_filter:
            return False
        if status == "open" and n.resolved:
            return False
        if status == "resolved" and not n.resolved:
            return False
        if scope != "all" and _note_scope(n) != scope:
            return False
        return True

    notes = [n for n in notes if keep(n)]
    # Most severe first, then newest first — the order a reviewer wants.
    notes.sort(key=lambda n: (
        _SEVERITY_RANK.get(n.importance.upper(), 0),
        n.createdAt.timestamp() if n.createdAt else 0.0,
    ), reverse=True)

    summary = {
        "bySeverity": {lvl: sum(1 for n in notes if n.importance.upper() == lvl)
                       for lvl in NOTE_IMPORTANCE},
        "byStatus": {"open": sum(1 for n in notes if not n.resolved),
                     "resolved": sum(1 for n in notes if n.resolved)},
        "byScope": {"personal": sum(1 for n in notes if _note_scope(n) == "personal"),
                    "shared": sum(1 for n in notes if _note_scope(n) == "shared")},
    }

    capped = notes[:MCP_MAX_ROWS]
    dumped = [_note_dump(n) for n in capped]
    out: dict = {
        "projectId": int(pid),
        "total": len(notes),
        "returned": len(dumped),
        "truncated": len(notes) > len(dumped),
        "summary": summary,
    }

    if group_by == "none":
        out["notes"] = dumped
        return out

    keyfn = {
        "severity": lambda d: d["severity"],
        "status": lambda d: d["status"],
        "scope": lambda d: d["scope"],
        "target": lambda d: d["target"],
    }[group_by]
    buckets: dict[str, list] = {}
    for d in dumped:
        buckets.setdefault(keyfn(d), []).append(d)
    if group_by == "severity":
        order = [lvl for lvl in reversed(NOTE_IMPORTANCE) if lvl in buckets]
    elif group_by == "status":
        order = [k for k in ("open", "resolved") if k in buckets]
    elif group_by == "scope":
        order = [k for k in ("shared", "personal") if k in buckets]
    else:
        order = sorted(buckets)
    out["groupBy"] = group_by
    out["groups"] = [{"key": k, "count": len(buckets[k]), "notes": buckets[k]} for k in order]
    return out


# ── lookup helpers: attribute values, a case anywhere ──────────────────────────


async def _tool_get_attribute_values(user, args) -> Any:
    """The values each meta attribute takes, with journey counts — so a caller knows what
    to pass as meta1/meta2/meta3 instead of guessing."""
    pid, spec = _project_id(args), _filter_spec(args)
    wanted = args.get("meta")
    if wanted in (None, "", "all"):
        metas = list(META_COLUMNS)
    else:
        wanted = str(wanted).lower()
        if wanted not in META_COLUMNS:
            raise ToolError("meta must be one of meta1, meta2, meta3 (or omit it for all three).")
        metas = [wanted]
    limit = min(int(args.get("limit") or 50), MCP_MAX_ROWS)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        titles = dict(zip(META_COLUMNS, await repo.load_meta_titles(pid)))
        an = Analysis(repo)
        out = []
        for meta in metas:
            distinct, values = await an.attribute_values(pid, meta, spec, limit)
            out.append({
                "meta": meta,
                "title": titles.get(meta),
                "distinctValues": distinct,
                "values": [{"value": v, "journeys": n} for v, n in values],
                "truncated": distinct > len(values),
            })
    return {
        "projectId": int(pid),
        "attributes": out,
        "filterHint": "Pass a value as meta1/meta2/meta3 in any filtered tool; the match "
                      "is case-insensitive and also matches substrings.",
    }


async def _tool_find_journey(user, args) -> Any:
    """Locate one case id across every project the caller may query (or one connection),
    so get_journey can be called without guessing the project from the id's prefix."""
    raw = str(args.get("eventId") or "").strip()
    if not raw:
        raise ToolError("eventId is required — a business case id (e.g. 'FLT-000123') or "
                        "the 32-char stored hash.")
    if len(raw) > 512:
        raise ToolError("eventId is too long.")
    stored = ProcessRepository._normalize_event_id(raw)
    connections = store.connections_for_user(user.username)
    requested = args.get("connectionId")
    if requested:
        connections = [c for c in connections if c.id == str(requested)]
        if not connections:
            raise ToolError(f"Connection {requested!r} is not assigned to you.")

    sample = _sample_of(args)
    matches: list[dict] = []
    unreachable: list[dict] = []
    projects_searched = 0
    for connection in connections:
        try:
            async with _Repo(user.username, connection.id, sample) as repo:
                an = Analysis(repo)
                for project in _dump(await repo.load_projects()):
                    projects_searched += 1
                    hit = await an.journey_lookup(str(project["projectId"]), stored)
                    if hit:
                        matches.append({
                            "connectionId": connection.id,
                            "connectionName": connection.name,
                            "projectId": project["projectId"],
                            "title": project.get("title"),
                            "startDate": hit["startDate"].isoformat() if hit["startDate"] else None,
                            "endDate": hit["endDate"].isoformat() if hit["endDate"] else None,
                            "durationSecs": hit["durationSecs"],
                            "stepCount": hit["stepCount"],
                        })
        except Exception as exc:  # noqa: BLE001 — report the connection, keep searching
            log.warning("find_journey: connection %s unavailable: %s", connection.id, exc)
            unreachable.append({"connectionId": connection.id,
                                "connectionName": connection.name, "error": str(exc)})
    out: dict = {
        "eventId": raw,
        "storedEventId": stored,
        "matches": matches,
        "searched": {"connections": len(connections), "projects": projects_searched},
    }
    if unreachable:
        out["unreachable"] = unreachable
    if not matches:
        out["message"] = f"No journey {raw!r} in any project you can query."
    return out


# ── the note-writing tools (the only writes on this surface) ───────────────────

# A note id is the app's uppercase UUID; accept that shape (case-insensitive) and nothing
# else, so a crafted id never even reaches the SQL layer.
_NOTE_ID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")

# Rolling one-minute window of note writes per user (process-local; the MCP server is a
# single process). Every *attempt* that passes argument validation counts, successful or
# not, so the limit also slows probing (e.g. guessing note ids).
_NOTE_WRITES: dict[str, deque] = {}


def _check_write_rate(username: str) -> None:
    now = time.monotonic()
    window = _NOTE_WRITES.setdefault(username.lower(), deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= MCP_NOTE_WRITES_PER_MIN:
        raise ToolError(
            f"You have reached the limit of {MCP_NOTE_WRITES_PER_MIN} note changes per "
            "minute. Please wait a moment and try again."
        )
    window.append(now)


def _clean(value: Any, field: str, *, max_len: int, single_line: bool = False) -> str:
    try:
        return clean_text(value, max_len=max_len, single_line=single_line)
    except ValueError as exc:
        raise ToolError(f"{field} {exc}.") from None


def _author_name(username: str) -> str:
    u = store.get_user(username)
    return (u.display_name if u and getattr(u, "display_name", "") else "") or username


def _audit(user, tool: str, connection_id: str, project_id: str, note_id: str) -> None:
    """Every note write lands in the admin log (who, what, where — never the text)."""
    msg = f"MCP {tool}: note {note_id} on connection {connection_id}, project {project_id}"
    log.info("%s by %s", msg, user.username)
    logx.usage(msg, username=user.username, operation=f"mcp_{tool}")


async def _require_project(repo, pid: str) -> dict:
    for project in _dump(await repo.load_projects()):
        if str(project.get("projectId")) == str(pid):
            return project
    raise ToolError(f"No project {pid} on this connection.")


async def _known_steps(repo, pid: str) -> set[str]:
    try:
        defs = await repo.load_steps(pid)
    except Exception:  # noqa: BLE001
        defs = {}
    return set(defs) or set(await repo.load_all_step_names(pid))


def _step_arg(args: dict, key: str) -> str:
    val = args.get(key)
    if val is None or val == "":
        return ""
    if not isinstance(val, str) or len(val) > STEP_MAX:
        raise ToolError(f"{key} must be a step name.")
    return val


async def _note_target(repo, pid: str, args: dict) -> NoteTarget:
    """The step or transition a new note annotates — it must exist in the project."""
    step = _step_arg(args, "step")
    frm, to = _step_arg(args, "fromStep"), _step_arg(args, "toStep")
    if step and (frm or to):
        raise ToolError("Give either step (a note on a step) or fromStep + toStep "
                        "(a note on a transition), not both.")
    if not step and not (frm and to):
        raise ToolError("A note needs a target: step, or fromStep + toStep.")
    known = await _known_steps(repo, pid)
    for name in ([step] if step else [frm, to]):
        if name not in known:
            raise ToolError(f"Step {name!r} does not exist in project {pid}. Use "
                            "get_metadata to list the exact step names.")
    if step:
        return NoteTarget(type="node", value=step)
    return NoteTarget.model_validate({"type": "edge", "from": frm, "to": to})


def _severity_arg(args: dict, *, default: str | None) -> str | None:
    raw = args.get("severity")
    if raw in (None, ""):
        return default
    sev = str(raw).upper()
    if sev not in NOTE_IMPORTANCE:
        raise ToolError(f"severity must be one of {', '.join(NOTE_IMPORTANCE)}.")
    return sev


def _choice_arg(args: dict, key: str, choices: tuple[str, ...], *, default: str | None) -> str | None:
    raw = args.get(key)
    if raw in (None, ""):
        return default
    val = str(raw).lower()
    if val not in choices:
        raise ToolError(f"{key} must be one of {', '.join(choices)}.")
    return val


async def _tool_create_note(user, args) -> Any:
    """Create a note on a step or transition, authored by the caller."""
    pid, cid = _project_id(args), _conn_id(args)
    title = _clean(args.get("title"), "title", max_len=TITLE_MAX, single_line=True)
    # The note body opens its thread, so it must not imitate a comment header either.
    text = defang_headers(_clean(args.get("text"), "text", max_len=TEXT_MAX))
    if not text:
        raise ToolError("text is required — the body of the note.")
    severity = _severity_arg(args, default="NORMAL")
    scope = _choice_arg(args, "scope", ("personal", "shared"), default="personal")
    _check_write_rate(user.username)

    async with _Repo(user.username, cid, SampleSet.original) as repo:
        await _require_project(repo, pid)
        target = await _note_target(repo, pid, args)
        await repo.ensure_notes_table()
        if MCP_MAX_NOTES_PER_PROJECT > 0:
            # Bound total accumulation, not just the rate: an agent cannot build up an
            # unbounded pile of notes that only its owner can later delete.
            owned = await repo.count_user_notes(pid, user.username)
            if owned >= MCP_MAX_NOTES_PER_PROJECT:
                raise ToolError(
                    f"You already own {owned} notes in project {pid} (the limit is "
                    f"{MCP_MAX_NOTES_PER_PROJECT}). Delete some in the app before adding more."
                )
        frm, to = await repo.load_date_bounds(pid)
        now = local_now()
        note = ProcessNote(
            id=new_id(), title=title, text=text, createdAt=now, editedAt=None,
            target=target, filterSnapshot=FilterSnapshot(fromDate=frm or now, toDate=to or now),
            username=user.username, lastEditedBy="", isShared=(scope == "shared"),
            importance=severity, resolved=False,
        )
        await repo.upsert_note(note, pid, user.username)
        saved = await repo.get_note(note.id, pid)
    _audit(user, "create_note", cid, pid, note.id)
    return {"created": True, "note": _note_dump(saved or note)}


async def _tool_update_note(user, args) -> Any:
    """Comment on a note, resolve/reopen it, or (author only) change severity/scope.
    The thread is append-only: existing text is never rewritten."""
    pid, cid = _project_id(args), _conn_id(args)
    raw_id = args.get("noteId")
    note_id = raw_id.strip() if isinstance(raw_id, str) else ""
    if not _NOTE_ID_RE.match(note_id):
        raise ToolError("noteId must be a note id as returned by get_notes or create_note.")
    note_id = note_id.upper()  # ids are stored as the app's uppercase UUIDs
    comment = _clean(args.get("comment"), "comment", max_len=TEXT_MAX)
    title = _clean(args.get("title"), "title", max_len=TITLE_MAX, single_line=True)
    status = _choice_arg(args, "status", ("open", "resolved"), default=None)
    severity = _severity_arg(args, default=None)
    scope = _choice_arg(args, "scope", ("personal", "shared"), default=None)
    if not (comment or title or status or severity or scope):
        raise ToolError("Nothing to change — pass a comment, title, status, severity or scope.")
    _check_write_rate(user.username)

    async with _Repo(user.username, cid, SampleSet.original) as repo:
        await _require_project(repo, pid)
        await repo.ensure_notes_table()
        note = await repo.get_note(note_id, pid)
        owner = (note.username or "") if note else ""
        is_owner = bool(note) and owner.upper() == user.username.upper()
        # Same visibility as the app (own, shared or unowned). A note that is missing, in
        # another project, or another user's private note all get the SAME answer, so the
        # tool can't be used to discover which ids exist.
        if note is None or not (is_owner or note.isShared or owner == ""):
            raise ToolError(f"No note {note_id!r} that you can see in project {pid}.")
        if (severity is not None or scope is not None) and not is_owner:
            raise ToolError("Only the note's author can change its severity or scope. You "
                            "can still add a comment or change its status.")
        block = comment_block(_author_name(user.username), comment, title or None) if comment else None
        if block and not thread_has_room(note.text, block):
            raise ToolError("This note's thread is full — create a new note to continue the "
                            "discussion.")
        await repo.update_note(
            note_id, pid,
            edited_by=user.username,
            comment_block=block,
            title=title or None,
            resolved=None if status is None else (status == "resolved"),
            importance=severity,
            is_shared=None if scope is None else (scope == "shared"),
            caller=user.username,  # the permission rule is repeated in the UPDATE itself
        )
        saved = await repo.get_note(note_id, pid)
    _audit(user, "update_note", cid, pid, note_id)
    changes = [k for k, v in (("comment", comment), ("title", title), ("status", status),
                              ("severity", severity), ("scope", scope)) if v]
    return {"updated": True, "changes": changes, "note": _note_dump(saved or note)}


# ── deeper analysis — power users (and administrators) only ────────────────────


def _require_power(user, tool: str) -> None:
    if getattr(user, "is_power", False) or getattr(user, "is_admin", False):
        return
    raise ToolError(
        f"Sorry — {tool} is one of the deeper-analysis tools, which are reserved for power "
        f"users. Your account ({user.username}) doesn't have the power-user role, so I "
        "can't run it for you. If you need it, please ask your Process Mining administrator "
        "to grant the role in the Admin Console (Users). In the meantime get_statistics, "
        "get_transition_metrics, get_variants and find_journeys are available to you."
    )


def _steps_list(args: dict, key: str, *, required: bool, max_items: int = 20) -> list[str]:
    raw = args.get(key)
    if raw in (None, "", []):
        if required:
            raise ToolError(f"{key} is required — one or more step names.")
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or len(raw) > max_items:
        raise ToolError(f"{key} must be a list of at most {max_items} step names.")
    out = []
    for item in raw:
        if not isinstance(item, str) or not item or len(item) > STEP_MAX:
            raise ToolError(f"{key} must contain step names (non-empty strings).")
        out.append(item)
    return out


def _int_arg(args: dict, key: str, default: int, low: int, high: int) -> int:
    raw = args.get(key)
    if raw in (None, ""):
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"{key} must be a whole number.") from None
    return max(low, min(val, high))


def _segment(args: dict, key: str) -> tuple[str, FilterSpec]:
    seg = args.get(key)
    if not isinstance(seg, dict):
        raise ToolError(f"{key} must be an object of filter fields (fromDate, toDate, "
                        "includedSteps, excludedSteps, meta1, meta2, meta3) plus an optional label.")
    label = str(seg.get("label") or key)[:100]
    return label, _filter_spec({**seg, "sampleSet": args.get("sampleSet")})


def _share(n: int, total: int) -> float | None:
    return round(n / total, 4) if total else None


async def _segment_profile(repo, an: Analysis, pid: str, spec: FilterSpec) -> dict:
    count = await repo.load_journey_count(pid, spec)
    durations = await repo.load_journey_duration_stats(pid, spec)
    goodness = await repo.load_process_goodness(pid, spec)
    ends = await an.end_steps(pid, spec, limit=50)
    transitions = await repo.load_transitions(pid, spec)
    return {
        "count": count, "durations": _dump(durations),
        "goodness": None if goodness is None else goodness[0],
        "ends": ends, "transitions": {(t.fromStep, t.toStep): t for t in transitions},
    }


async def _tool_compare_segments(user, args) -> Any:
    _require_power(user, "compare_segments")
    pid = _project_id(args)
    (label_a, spec_a), (label_b, spec_b) = _segment(args, "segmentA"), _segment(args, "segmentB")
    limit = _int_arg(args, "limit", 10, 1, 100)
    min_occ = _int_arg(args, "minOccurrences", 30, 1, 10_000_000)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        an = Analysis(repo)
        a = await _segment_profile(repo, an, pid, spec_a)
        b = await _segment_profile(repo, an, pid, spec_b)

    def seg_out(label, p):
        return {
            "label": label, "journeyCount": p["count"], "durations": p["durations"],
            "processGoodness": p["goodness"],
            "endSteps": [{"step": s, "journeys": n, "share": _share(n, p["count"])}
                         for s, n in p["ends"][:limit]],
        }

    ends_a, ends_b = dict(a["ends"]), dict(b["ends"])
    end_diff = []
    for step in set(ends_a) | set(ends_b):
        sa, sb = _share(ends_a.get(step, 0), a["count"]), _share(ends_b.get(step, 0), b["count"])
        if sa is None or sb is None:
            continue
        end_diff.append({"step": step, "shareA": sa, "shareB": sb, "deltaPoints": round((sb - sa) * 100, 2)})
    end_diff.sort(key=lambda d: abs(d["deltaPoints"]), reverse=True)

    time_diff, freq_diff = [], []
    for key in set(a["transitions"]) & set(b["transitions"]):
        ta, tb = a["transitions"][key], b["transitions"][key]
        if ta.occurrences < min_occ or tb.occurrences < min_occ:
            continue
        row = {"fromStep": key[0], "toStep": key[1],
               "occurrencesA": ta.occurrences, "occurrencesB": tb.occurrences}
        if ta.avgSecs is not None and tb.avgSecs is not None:
            time_diff.append({**row, "avgSecsA": round(ta.avgSecs, 1), "avgSecsB": round(tb.avgSecs, 1),
                              "deltaSecs": round(tb.avgSecs - ta.avgSecs, 1)})
        pa = ta.occurrences / a["count"] if a["count"] else 0.0
        pb = tb.occurrences / b["count"] if b["count"] else 0.0
        freq_diff.append({**row, "perJourneyA": round(pa, 4), "perJourneyB": round(pb, 4),
                          "delta": round(pb - pa, 4)})
    time_diff.sort(key=lambda d: abs(d["deltaSecs"]), reverse=True)
    freq_diff.sort(key=lambda d: abs(d["delta"]), reverse=True)

    def only(p, other):
        rows = [p["transitions"][k] for k in set(p["transitions"]) - set(other["transitions"])]
        rows.sort(key=lambda t: t.occurrences, reverse=True)
        return [{"fromStep": t.fromStep, "toStep": t.toStep, "occurrences": t.occurrences}
                for t in rows[:limit]]

    return {
        "segments": [seg_out(label_a, a), seg_out(label_b, b)],
        "differences": {
            "endSteps": end_diff[:limit],
            "transitionTime": time_diff[:limit],
            "transitionFrequency": freq_diff[:limit],
            "onlyInA": only(a, b),
            "onlyInB": only(b, a),
        },
        "notes": "Deltas are B minus A. Transition rows need at least minOccurrences in "
                 "both segments.",
    }


async def _tool_get_bottlenecks(user, args) -> Any:
    _require_power(user, "get_bottlenecks")
    pid, spec = _project_id(args), _filter_spec(args)
    limit = _int_arg(args, "limit", 10, 1, 100)
    min_occ = _int_arg(args, "minOccurrences", 30, 1, 10_000_000)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        transitions = await repo.load_transitions(pid, spec)
        rework = await Analysis(repo).rework(pid, spec, limit)
    waits = [(t, t.occurrences * (t.avgSecs or 0.0)) for t in transitions]
    total_wait = sum(w for _, w in waits) or 0.0

    def row(t, wait=None):
        out = {"fromStep": t.fromStep, "toStep": t.toStep, "occurrences": t.occurrences,
               "avgSecs": None if t.avgSecs is None else round(t.avgSecs, 1),
               "medianSecs": None if t.medianSecs is None else round(t.medianSecs, 1)}
        if wait is not None:
            out["totalWaitSecs"] = round(wait, 1)
            out["shareOfWaitTime"] = round(wait / total_wait, 4) if total_wait else None
        return out

    by_wait = sorted(waits, key=lambda x: x[1], reverse=True)[:limit]
    slowest = sorted((t for t in transitions if t.occurrences >= min_occ and t.medianSecs is not None),
                     key=lambda t: t.medianSecs, reverse=True)[:limit]
    loops = sorted((t for t in transitions if t.fromStep == t.toStep),
                   key=lambda t: t.occurrences, reverse=True)[:limit]
    return {
        "totalWaitSecs": round(total_wait, 1),
        "byTotalWaitTime": [row(t, w) for t, w in by_wait],
        "slowestTypicalTransitions": [row(t) for t in slowest],
        "rework": rework,
        "selfLoops": [row(t) for t in loops],
        "notes": "totalWaitSecs = occurrences × average transition time. The slowest list "
                 "ranks by median and ignores transitions below minOccurrences.",
    }


async def _tool_get_trend(user, args) -> Any:
    _require_power(user, "get_trend")
    pid, spec = _project_id(args), _filter_spec(args)
    unit = str(args.get("granularity") or "month").lower()
    if unit not in TREND_UNITS:
        raise ToolError(f"granularity must be one of {', '.join(TREND_UNITS)}.")
    outcome = _steps_list(args, "outcomeSteps", required=False)
    limit = _int_arg(args, "limit", 366, 1, MCP_MAX_ROWS)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        points = await Analysis(repo).trend(pid, spec, unit, outcome, limit)
    return {"granularity": unit, "outcomeSteps": outcome, "periods": points,
            "truncated": len(points) >= limit,
            "notes": "Journeys are assigned to the period in which they started. When "
                     "truncated, the most recent periods are the ones returned."}


async def _tool_get_outcome_drivers(user, args) -> Any:
    _require_power(user, "get_outcome_drivers")
    pid, spec = _project_id(args), _filter_spec(args)
    outcome = _steps_list(args, "outcomeSteps", required=True)
    min_support = _int_arg(args, "minSupport", 30, 1, 10_000_000)
    limit = _int_arg(args, "limit", 10, 1, 100)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        titles = dict(zip(META_COLUMNS, await repo.load_meta_titles(pid)))
        res = await Analysis(repo).outcome_drivers(pid, spec, outcome, min_support)
    total, hits = res["total"], res["hits"]
    if not total:
        return {"outcomeSteps": outcome, "journeys": 0, "message": "No journeys match this filter."}
    base = hits / total

    def factor(n, h):
        rate = h / n if n else 0.0
        rest_n = total - n
        rest = (hits - h) / rest_n if rest_n else None
        return {"journeys": n, "outcomeJourneys": h, "outcomeRate": round(rate, 4),
                "rateWithout": None if rest is None else round(rest, 4),
                "deltaPoints": round((rate - base) * 100, 2),
                "lift": round(rate / base, 3) if base else None}

    meta = [{"attribute": m, "title": titles.get(m), "value": v, **factor(n, h)}
            for m, v, n, h in res["meta"]]
    steps = [{"step": s, **factor(n, h)} for s, n, h in res["steps"]]

    def split(rows):
        up = sorted((r for r in rows if r["deltaPoints"] > 0), key=lambda r: r["deltaPoints"], reverse=True)
        down = sorted((r for r in rows if r["deltaPoints"] < 0), key=lambda r: r["deltaPoints"])
        return up[:limit], down[:limit]

    meta_up, meta_down = split(meta)
    step_up, step_down = split(steps)
    return {
        "outcomeSteps": outcome,
        "journeys": total,
        "outcomeJourneys": hits,
        "outcomeRate": round(base, 4),
        "raisesOutcome": {"attributes": meta_up, "steps": step_up},
        "lowersOutcome": {"attributes": meta_down, "steps": step_down},
        "notes": "Rates compare journeys with a factor against the overall rate; they show "
                 "association, not cause. Factors below minSupport journeys are left out.",
    }


async def _tool_check_conformance(user, args) -> Any:
    _require_power(user, "check_conformance")
    pid, spec = _project_id(args), _filter_spec(args)
    raw_rules = args.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ToolError("rules is required — a list of rule objects (see the tool description).")
    if len(raw_rules) > MAX_RULES:
        raise ToolError(f"At most {MAX_RULES} rules per call.")
    try:
        rules = [Rule.parse(r, step_max=STEP_MAX) for r in raw_rules]
    except ValueError as exc:
        raise ToolError(f"Invalid rule: {exc}.") from None
    examples = _int_arg(args, "examples", 5, 0, 50)
    async with _Repo(user.username, _conn_id(args), _sample_of(args)) as repo:
        known = await _known_steps(repo, pid)
        checked, results = await Analysis(repo).conformance(pid, spec, rules, examples)
    unknown = sorted({s for r in rules for s in r.steps()} - known)
    out = {
        "journeysChecked": checked,
        "rules": [
            {"type": r.kind, "rule": r.describe(), "violations": n,
             "violationRate": _share(n, checked),
             "conformanceRate": None if not checked else round(1 - n / checked, 4),
             "exampleEventIds": ids}
            for r, (n, ids) in zip(rules, results)
        ],
        "notes": "exampleEventIds are stored ids — pass one to get_journey for the full trace.",
    }
    if unknown:
        out["unknownSteps"] = unknown
        out["warning"] = ("Some rule steps do not exist in this project (check spelling with "
                          "get_metadata); rules on them can never match.")
    return out


_TOOLS: list[dict] = [
    {"name": "list_connections", "handler": _tool_list_connections,
     "description": "List the database connections you may query (id, name, schema).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_projects", "handler": _tool_list_projects,
     "description": "List process-mining projects. Omit connectionId to list every "
                    "project on every connection you may query; set includeCounts to "
                    "get each project's journey count, so project sizes can be compared "
                    "in one call. Each entry names the connection it belongs to; a "
                    "connection that could not be opened comes back as a single entry "
                    "carrying 'error' instead of a project.",
     "inputSchema": {"type": "object", "properties": {
         "connectionId": {"type": "string",
                          "description": "A connection id from list_connections. Omit "
                                         "to span all of your connections."},
         "includeCounts": {"type": "boolean",
                           "description": "Also return journeyCount per project "
                                          "(one count query each; default false)."},
         "sampleSet": _FILTER_PROPS["sampleSet"]}}},
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
                    "each step's definition (stepDetails: description, score, belongsTo "
                    "group, endOfProcess, shape) and the event date range.",
     "inputSchema": {"type": "object", "properties": {**_CONN, **_PROJ},
                     "required": ["connectionId", "projectId"]}},
    {"name": "get_journey", "handler": _tool_get_journey,
     "description": "One journey's ordered events: the trace for a single case id "
                    "(a business id like 'FLT-000123', or the 32-char stored hash), with "
                    "its meta attributes, start/end timestamps and total duration.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ,
         "eventId": {"type": "string",
                     "description": "The case id — a business id (e.g. 'FLT-000123') or "
                                    "the 32-char stored hash."},
         "sampleSet": _FILTER_PROPS["sampleSet"]},
         "required": ["connectionId", "projectId", "eventId"]}},
    {"name": "find_journeys", "handler": _tool_find_journeys,
     "description": "Find individual journeys matching a filter — the drill-down from "
                    "an aggregate to the cases behind it: the slowest journeys, the "
                    "ones that visited a given step (includedSteps), the longest "
                    "traces. Returns one row per case with its stored id, start/end, "
                    "duration, step count and meta attributes; pass a returned eventId "
                    "to get_journey for the full trace.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "orderBy": {"type": "string", "enum": list(JOURNEY_ORDERS),
                     "description": "Sort order (default DURATION_DESC — slowest first)."},
         "limit": {"type": "integer",
                   "description": f"Max journeys (default 20, <= {MCP_MAX_ROWS})."},
         "minDurationSecs": {"type": "number",
                             "description": "Keep journeys lasting at least this long."},
         "maxDurationSecs": {"type": "number",
                             "description": "Keep journeys lasting at most this long."},
         "minSteps": {"type": "integer", "description": "Keep journeys with >= this many events."},
         "maxSteps": {"type": "integer", "description": "Keep journeys with <= this many events."},
         "includePath": {"type": "boolean",
                         "description": "Also return each journey's full step path "
                                        "(default false; costlier on large projects)."}},
         "required": ["connectionId", "projectId"]}},
    {"name": "get_notes", "handler": _tool_get_notes,
     "description": "The notes/annotations placed on a project's steps and transitions — "
                    "issues, observations and review comments. Filter by severity "
                    "(NORMAL/INFO/IMPORTANT/URGENT), by status (open / resolved) and by "
                    "scope (personal — your own — or shared), and optionally group the "
                    "result by any of those. Returns each note's title, text, severity, "
                    "status, scope, author, target (the step or transition it annotates) "
                    "and timestamps, plus a summary count breakdown. You see shared notes "
                    "and your own, never another user's private notes.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ,
         "severity": {"type": "array", "items": {"type": "string", "enum": list(NOTE_IMPORTANCE)},
                      "description": "Keep only notes at these severities (default all)."},
         "status": {"type": "string", "enum": ["open", "resolved", "all"],
                    "description": "Keep only open or only resolved notes (default all)."},
         "scope": {"type": "string", "enum": ["personal", "shared", "all"],
                   "description": "Keep only your personal notes or only shared notes "
                                  "(default all)."},
         "groupBy": {"type": "string", "enum": ["severity", "status", "scope", "target", "none"],
                     "description": "Group the returned notes by this dimension (default "
                                    "none — a flat list). 'target' groups by the annotated "
                                    "step/transition."}},
         "required": ["connectionId", "projectId"]}},
    {"name": "get_attribute_values", "handler": _tool_get_attribute_values,
     "description": "The values a project's meta attributes (meta1/meta2/meta3) take, each "
                    "with its journey count, most frequent first, plus the attribute's title "
                    "and the number of distinct values. Use it to find valid values before "
                    "filtering with meta1/meta2/meta3 in any other tool.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "meta": {"type": "string", "enum": ["meta1", "meta2", "meta3", "all"],
                  "description": "Which attribute (default all three)."},
         "limit": {"type": "integer",
                   "description": f"Max values per attribute (default 50, <= {MCP_MAX_ROWS})."}},
         "required": ["connectionId", "projectId"]}},
    {"name": "find_journey", "handler": _tool_find_journey,
     "description": "Find which project(s) hold a case id — searches every project on every "
                    "connection you may query (or only connectionId). Returns each match's "
                    "connection, project, start/end, duration and step count, ready for "
                    "get_journey. Accepts a business id (e.g. 'CRA-000123') or the 32-char "
                    "stored hash.",
     "inputSchema": {"type": "object", "properties": {
         "eventId": {"type": "string", "description": "The case id to look for."},
         "connectionId": {"type": "string",
                          "description": "Limit the search to one connection (default all)."},
         "sampleSet": _FILTER_PROPS["sampleSet"]},
         "required": ["eventId"]}},
    {"name": "create_note", "handler": _tool_create_note,
     "description": "WRITE: create a note on a step (step) or a transition (fromStep + "
                    "toStep) of a project. You become its author. text is required (max "
                    f"{TEXT_MAX} characters), title optional (max {TITLE_MAX}); severity "
                    "NORMAL/INFO/IMPORTANT/URGENT (default NORMAL); scope personal (only "
                    "you see it, default) or shared (the whole team). Step names must match "
                    "the project exactly (see get_metadata). Rate-limited per user, and "
                    "capped at a maximum number of notes you may own per project.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ,
         "step": {"type": "string", "description": "The step to annotate."},
         "fromStep": {"type": "string", "description": "Transition source step (with toStep)."},
         "toStep": {"type": "string", "description": "Transition target step (with fromStep)."},
         "title": {"type": "string", "description": f"Short subject (max {TITLE_MAX})."},
         "text": {"type": "string", "description": f"The note body (required, max {TEXT_MAX})."},
         "severity": {"type": "string", "enum": list(NOTE_IMPORTANCE)},
         "scope": {"type": "string", "enum": ["personal", "shared"]}},
         "required": ["connectionId", "projectId", "text"]}},
    {"name": "update_note", "handler": _tool_update_note,
     "description": "WRITE: change a note you can see (your own, a shared one, or an "
                    "unowned one): add a comment to its thread (with an optional title), "
                    "set its status to open or resolved, and — author only — change its "
                    "severity or scope. Existing text is never rewritten; comments are "
                    "prepended, newest first. noteId comes from get_notes or create_note. "
                    "Rate-limited per user.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ,
         "noteId": {"type": "string", "description": "The note's id."},
         "comment": {"type": "string", "description": f"A comment to add (max {TEXT_MAX})."},
         "title": {"type": "string",
                   "description": f"A title for this comment; also becomes the note's title (max {TITLE_MAX})."},
         "status": {"type": "string", "enum": ["open", "resolved"]},
         "severity": {"type": "string", "enum": list(NOTE_IMPORTANCE),
                      "description": "Author only."},
         "scope": {"type": "string", "enum": ["personal", "shared"],
                   "description": "Author only."}},
         "required": ["connectionId", "projectId", "noteId"]}},
    {"name": "compare_segments", "handler": _tool_compare_segments,
     "description": "POWER USERS ONLY. Compare two slices of one project side by side — "
                    "e.g. segmentA {meta1: 'Bank Transfer'} vs segmentB {meta1: 'PayPal'}. "
                    "Returns each segment's journey count, duration stats, goodness and end "
                    "steps, then the biggest differences (B minus A): end-step shares, "
                    "transition times, transition frequency per journey, and transitions "
                    "found in only one segment.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ,
         "segmentA": {"type": "object", "description": "Filter for segment A: fromDate, "
                      "toDate, includedSteps, excludedSteps, meta1, meta2, meta3, label."},
         "segmentB": {"type": "object", "description": "Filter for segment B (same fields)."},
         "limit": {"type": "integer", "description": "Rows per difference list (default 10)."},
         "minOccurrences": {"type": "integer",
                            "description": "Ignore transitions rarer than this in either segment (default 30)."},
         "sampleSet": _FILTER_PROPS["sampleSet"]},
         "required": ["connectionId", "projectId", "segmentA", "segmentB"]}},
    {"name": "get_bottlenecks", "handler": _tool_get_bottlenecks,
     "description": "POWER USERS ONLY. Where time is lost: transitions ranked by total "
                    "waiting time (occurrences × average), the slowest typical transitions "
                    "(by median), steps repeated inside journeys (rework) and self-loops.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "limit": {"type": "integer", "description": "Rows per list (default 10)."},
         "minOccurrences": {"type": "integer",
                            "description": "Minimum occurrences for the slowest list (default 30)."}},
         "required": ["connectionId", "projectId"]}},
    {"name": "get_trend", "handler": _tool_get_trend,
     "description": "POWER USERS ONLY. The process over time: per day, week or month (by "
                    "journey start) the journey count, average and median duration, and — "
                    "with outcomeSteps — how many and what share of journeys reached one of "
                    "those steps. Shows drift, seasonality and whether a change helped.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "granularity": {"type": "string", "enum": list(TREND_UNITS),
                         "description": "Period size (default month)."},
         "outcomeSteps": {"type": "array", "items": {"type": "string"},
                          "description": "Optional steps whose reach rate to track."},
         "limit": {"type": "integer", "description": "Max periods (default 366)."}},
         "required": ["connectionId", "projectId"]}},
    {"name": "get_outcome_drivers", "handler": _tool_get_outcome_drivers,
     "description": "POWER USERS ONLY. Why an outcome happens: for journeys reaching any of "
                    "outcomeSteps (e.g. 'Rejected', 'Payment Failed'), the overall rate and "
                    "the meta values and visited steps that raise or lower it (rate with the "
                    "factor, rate without it, delta in percentage points, lift). Shows "
                    "association, not cause.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "outcomeSteps": {"type": "array", "items": {"type": "string"},
                          "description": "The outcome step(s) (required)."},
         "minSupport": {"type": "integer",
                        "description": "Ignore factors seen in fewer journeys (default 30)."},
         "limit": {"type": "integer", "description": "Rows per list (default 10)."}},
         "required": ["connectionId", "projectId", "outcomeSteps"]}},
    {"name": "check_conformance", "handler": _tool_check_conformance,
     "description": "POWER USERS ONLY. Test journeys against up to 10 rules and count the "
                    "violations, with example case ids. Rule types: "
                    "{type:'requires', step, ifStep?} — must visit step (only when ifStep "
                    "was visited, if given); {type:'forbidden', step}; "
                    "{type:'precedes', before, after} — before must happen before after; "
                    "{type:'max_duration', maxSecs}; "
                    "{type:'max_gap', fromStep, toStep, maxSecs} — toStep within maxSecs of fromStep.",
     "inputSchema": {"type": "object", "properties": {
         **_CONN, **_PROJ, **_FILTER_PROPS,
         "rules": {"type": "array", "items": {"type": "object"},
                   "description": "The rules to check (1–10)."},
         "examples": {"type": "integer",
                      "description": "Example case ids per violated rule (default 5, max 50)."}},
         "required": ["connectionId", "projectId", "rules"]}},
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
        if len(body) > _MAX_BATCH:
            return JSONResponse(
                _rpc_error(None, -32600, f"A batch may hold at most {_MAX_BATCH} messages."),
                status_code=400)
        responses = [r for m in body if isinstance(m, dict)
                     and (r := await _dispatch(m, user)) is not None]
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
