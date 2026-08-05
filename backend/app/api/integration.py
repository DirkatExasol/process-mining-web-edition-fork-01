"""Integration abstraction-layer endpoints.

Read-only for now: the console polls the layer *status* and lists the *registered
extractors*. Triggering a run and managing extractors is built on top of this in a
later stage (the layer already exposes ``run``; it just isn't wired to an endpoint
yet). Reached by the integration console through its `/api` proxy; the signed-in
user arrives in the trusted ``X-PMW-User`` header the proxy injects.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import log_events as logx
from ..db.manager import current_db
from ..integration import SqlIngestBackend, layer
from ..integration.backends import DEFAULT_TRANSACTION_ROWS, clamp_transaction_rows
from ..integration.extractors import FileExtractor
from ..integration.files import FileAccessError, read_preview
from ..integration.parsing import ROLES, analyze_timestamp, detect_fields, regex_from_segment
from ..store.security import store as security_store

USER_HEADER = "x-pmw-user"


def _request_user(request: Request) -> str | None:
    value = request.headers.get(USER_HEADER)
    return value.strip() if value and value.strip() else None


def _require_developer(request: Request) -> str | None:
    """Gate every integration endpoint on the Developer (or admin) role.

    The integration *console* checks this too (integration/server.py), but that only
    guards signing in to port 8100. These endpoints live on the shared compute backend,
    and the MAIN app proxies `/api/*` for any enabled user — so without this check a
    plain user (or a power user, who is deliberately refused the console) could drive the
    whole data-source surface through the app's proxy. Also honours the admin's
    integration on/off switch, so disabling the console disables its API too.

    When no user header is present, sign-in is disabled for the whole deployment
    (single-user/dev mode) and the surface is open, matching the other routers.
    """
    username = _request_user(request)
    if username is None:
        return None
    if not security_store.integration_enabled:
        raise HTTPException(status_code=403, detail="The integration console is turned off.")
    user = security_store.get_user(username)
    if user is None or not user.is_enabled or not (user.is_developer or user.is_admin):
        raise HTTPException(
            status_code=403,
            detail="You need the Developer role to use the integration features.",
        )
    return username


# The gate is a ROUTER-level dependency, so it covers every endpoint below —
# including ones added later — rather than relying on each to remember it.
router = APIRouter(
    prefix="/api/integration",
    tags=["integration"],
    dependencies=[Depends(_require_developer)],
)


def _active_schema() -> tuple[str | None, str | None, bool]:
    """(active connection id, its target schema, connected?) for the current user —
    where an extraction would land. Best-effort; never raises."""
    try:
        mgr = current_db()
        if not mgr.is_connected:
            return (None, None, False)
        server = mgr.active_database_server
        schema = (server.schema_ or None) if server is not None else None
        return (mgr.active_profile_id, schema, True)
    except Exception:  # noqa: BLE001 — status must never fail on a probe
        return (None, None, False)


@router.get("/status")
def integration_status(request: Request) -> dict:
    """The abstraction-layer status for the signed-in user, plus the current target
    (the active connection's schema) and how many extractors are registered."""
    user = _request_user(request)
    conn_id, schema, connected = _active_schema()
    return {
        **layer.status_for(user).public(),
        "registeredExtractors": len(layer.extractors()),
        "activeConnectionId": conn_id,
        "activeSchema": schema,
        "connected": connected,
    }


@router.get("/extractors")
def integration_extractors() -> list[dict]:
    """The extractors currently plugged into the abstraction layer (empty until the
    first one ships)."""
    return [info.public() for info in layer.extractors()]


# ── source types (a user's extraction definitions) ────────────────────────────


class ExtractionField(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    role: str = "meta"
    regex: str = Field(default="", max_length=2000)
    format: str = Field(default="", max_length=120)
    # Human-readable business name for a meta field (→ METAS.META_n_TITLE).
    title: str = Field(default="", max_length=200)


class SourceTypeBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # The extraction spec captured by the wizard.
    sample: str = Field(default="", max_length=20000)
    fields: list[ExtractionField] = Field(default_factory=list)


def _spec_config(body: SourceTypeBody) -> str:
    """Serialise the extraction spec (sample + fields) to the source type's config JSON.
    Unknown roles fall back to 'meta'."""
    fields = [
        {
            "name": f.name.strip(),
            "role": f.role if f.role in ROLES else "meta",
            "regex": f.regex,
            **({"format": f.format} if f.format else {}),
            **({"title": f.title.strip()} if f.title.strip() else {}),
        }
        for f in body.fields
    ]
    return json.dumps({"sample": body.sample, "fields": fields})


@router.get("/source-types")
def list_source_types(request: Request) -> list[dict]:
    """The signed-in user's source types (with their extraction spec)."""
    user = _request_user(request)
    return [s.public() for s in security_store.list_source_types(user)]


@router.post("/source-types")
def create_source_type(body: SourceTypeBody, request: Request) -> dict:
    user = _request_user(request)
    created = security_store.add_source_type(user or "", name=body.name, config=_spec_config(body))
    return created.public()


@router.put("/source-types/{source_type_id}")
def update_source_type(source_type_id: str, body: SourceTypeBody, request: Request) -> dict:
    user = _request_user(request)
    updated = security_store.update_source_type(
        source_type_id, user, name=body.name, config=_spec_config(body)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Source type not found.")
    return updated.public()


@router.delete("/source-types/{source_type_id}")
def delete_source_type(source_type_id: str, request: Request) -> dict:
    user = _request_user(request)
    if not security_store.delete_source_type(source_type_id, user):
        raise HTTPException(status_code=404, detail="Source type not found.")
    return {"ok": True}


# ── data sources (generic kind + config) ──────────────────────────────────────

# Source kinds the backend accepts. Kept small on purpose — extend as new kinds ship;
# the frontend registry drives the per-kind form, this just gates what may be stored.
SOURCE_KINDS = {"file"}


def _transaction_rows(cfg: dict) -> int:
    """The source's configured transaction-bracket size (rows committed together)."""
    if "transactionRows" not in cfg:
        return DEFAULT_TRANSACTION_ROWS
    return clamp_transaction_rows(cfg.get("transactionRows"))


class SourceBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="file", max_length=40)
    # Kind-specific settings (e.g. {"path": "/var/log/app.log"} for a file source).
    config: dict = Field(default_factory=dict)


def _source_config(body: SourceBody, user: str | None) -> str:
    if body.kind not in SOURCE_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown source kind {body.kind!r}.")
    blob = json.dumps(body.config)
    if len(blob) > 8000:
        raise HTTPException(status_code=400, detail="Source settings are too large.")
    # A watchdog runs headless with the destination's STORED credentials, so the saver
    # must be assigned to that connection. (Also re-checked on every poll, which covers
    # later revocation — this save-time check just fails fast with a clear message.)
    wd = body.config.get("watchdog")
    if isinstance(wd, dict) and wd.get("enabled"):
        conn_id = str(wd.get("connectionId") or "").strip()
        if not conn_id or not security_store.user_can_use(conn_id, user):
            raise HTTPException(
                status_code=400,
                detail="The watchdog's destination connection is not assigned to you.",
            )
    return blob


@router.get("/sources")
def list_sources(request: Request) -> list[dict]:
    """The signed-in user's data sources."""
    user = _request_user(request)
    return [s.public() for s in security_store.list_sources(user)]


@router.post("/sources")
def create_source(body: SourceBody, request: Request) -> dict:
    user = _request_user(request)
    config = _source_config(body, user)
    created = security_store.add_source(user or "", name=body.name, kind=body.kind, config=config)
    return created.public()


@router.put("/sources/{source_id}")
def update_source(source_id: str, body: SourceBody, request: Request) -> dict:
    user = _request_user(request)
    config = _source_config(body, user)
    # If the file path changed, the old read checkpoint no longer applies — forget it so
    # the watchdog re-reads the new file from the start.
    old = _source_owned(source_id, user)
    old_path = str((old.public()["config"].get("path") if old else "") or "")
    updated = security_store.update_source(source_id, user, name=body.name, kind=body.kind, config=config)
    if updated is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    new_path = str(body.config.get("path") or "")
    if new_path != old_path:
        security_store.delete_source_checkpoint(source_id)
    return updated.public()


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, request: Request) -> dict:
    user = _request_user(request)
    if not security_store.delete_source(source_id, user):
        raise HTTPException(status_code=404, detail="Source not found.")
    return {"ok": True}


class PreviewBody(BaseModel):
    path: str = Field(default="", max_length=4000)
    limit: int = 5


@router.post("/sources/preview")
def preview_source(body: PreviewBody) -> dict:
    """First N lines of a File source's file (sandboxed — see integration/files.py)."""
    try:
        return read_preview(body.path, body.limit)
    except FileAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class RunBody(BaseModel):
    projectId: str = Field(min_length=1, max_length=100)


def _source_owned(source_id: str, user: str | None):
    for s in security_store.list_sources(user):
        if s.id == source_id:
            return s
    return None


@router.get("/sources/{source_id}/checkpoint")
def source_checkpoint(source_id: str, request: Request) -> dict:
    """The watchdog's read checkpoint for a File source (byte offset, imported records,
    last error, when it last ran) — or nulls if it has never imported."""
    user = _request_user(request)
    if _source_owned(source_id, user) is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    cp = security_store.get_source_checkpoint(source_id)
    return cp or {
        "byteOffset": 0, "size": 0, "signature": "", "records": 0,
        "updatedAt": None, "lastError": None,
    }


@router.post("/sources/{source_id}/checkpoint/reset")
def reset_source_checkpoint(source_id: str, request: Request) -> dict:
    """Forget the read checkpoint so the next watchdog poll re-imports from the start."""
    user = _request_user(request)
    if _source_owned(source_id, user) is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    security_store.delete_source_checkpoint(source_id)
    return {"ok": True}


@router.post("/sources/{source_id}/run")
async def run_source(source_id: str, body: RunBody, request: Request) -> dict:
    """Run a File source's extraction into the user's *active* connection + schema under
    the given project id. The source must link a source type; the file is read sandboxed."""
    user = _request_user(request)
    source = _source_owned(source_id, user)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    if source.kind != "file":
        raise HTTPException(status_code=400, detail="Only file sources can be run yet.")

    cfg = source.public()["config"]
    path = str(cfg.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="This source has no file path.")
    st_id = str(cfg.get("sourceTypeId") or "").strip()
    st = next((s for s in security_store.list_source_types(user) if s.id == st_id), None)
    if st is None:
        raise HTTPException(status_code=400, detail="Link a source type to this source first.")
    fields = st.public()["fields"]
    if not any(f.get("role") == "timestamp" for f in fields):
        raise HTTPException(status_code=400, detail="The source type has no timestamp field.")

    # Destination = the user's active connection + its schema.
    mgr = current_db()
    if not mgr.is_connected:
        raise HTTPException(status_code=400, detail="Connect to a destination database first.")
    server = mgr.active_database_server
    schema = (server.schema_ or "").strip() if server is not None else ""
    if not schema:
        raise HTTPException(status_code=400, detail="The active connection has no target schema.")

    # Insert inside real transactions: turn the driver's per-statement autocommit off
    # so the layer's bracket (transactionRows) decides when work becomes durable.
    raw = mgr._conn
    if raw is not None:
        raw.set_autocommit(False)
    backend = SqlIngestBackend(
        run_sql=lambda sql: mgr._execute_sync(sql).rows,
        commit=(lambda: raw.commit()) if raw is not None else None,
        rollback=(lambda: raw.rollback()) if raw is not None else None,
    )
    extractor = FileExtractor(
        path=path, encoding=str(cfg.get("encoding") or "utf-8"),
        fields=fields, project_id=body.projectId.strip(),
    )
    conn = security_store.get_connection(mgr.active_profile_id) if mgr.active_profile_id else None
    project_id = body.projectId.strip()
    transaction_rows = _transaction_rows(cfg)
    target = f"{conn.name if conn is not None else schema}/{schema}"
    logx.usage(
        f"import started: {source.name!r} (source type {st.name!r}) → {target} "
        f"project {project_id}",
        request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
    )
    try:
        result = await layer.run(
            user=user, extractor=extractor, backend=backend, schema=schema,
            connection_id=mgr.active_profile_id,
            connection_name=conn.name if conn is not None else None,
            source_name=source.name, source_type_name=st.name,
            transaction_rows=transaction_rows,
        )
    except FileAccessError as exc:
        logx.error(
            f"import failed: {source.name!r} → {target} project {project_id} — {exc}",
            request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
        )
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller + the status panel
        logx.error(
            f"import failed: {source.name!r} → {target} project {project_id} — {exc}",
            request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
        )
        raise HTTPException(status_code=400, detail=f"Extraction failed: {exc}")
    logx.usage(
        f"import finished: {source.name!r} → {target} project {project_id} — "
        f"{result.detail}",
        request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
    )
    return {"records": result.records, "detail": result.detail}


# ── example-log parsing (wizard helpers) ──────────────────────────────────────


class DetectBody(BaseModel):
    sample: str = Field(default="", max_length=20000)


class SegmentBody(BaseModel):
    sample: str = Field(default="", max_length=20000)
    start: int = 0
    end: int = 0


@router.post("/parse/detect")
def parse_detect(body: DetectBody) -> dict:
    """Suggest extraction fields (timestamp / id / step / meta) for a pasted log line."""
    return {"fields": detect_fields(body.sample)}


@router.post("/parse/segment")
def parse_segment(body: SegmentBody) -> dict:
    """Generalise a highlighted span into a single-capture-group regex."""
    try:
        return regex_from_segment(body.sample, body.start, body.end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class TimestampBody(BaseModel):
    value: str = Field(default="", max_length=200)


@router.post("/parse/timestamp")
def parse_timestamp(body: TimestampBody) -> dict:
    """Infer a timestamp field's parse format and its normalised
    YYYY-MM-DD HH:MM:SS value from an example captured value."""
    return analyze_timestamp(body.value)
