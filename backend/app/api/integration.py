"""Integration abstraction-layer endpoints.

Read-only for now: the console polls the layer *status* and lists the *registered
extractors*. Triggering a run and managing extractors is built on top of this in a
later stage (the layer already exposes ``run``; it just isn't wired to an endpoint
yet). Reached by the integration console through its `/api` proxy; the signed-in
user arrives in the trusted ``X-PMW-User`` header the proxy injects.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import log_events as logx
from ..config import INTEGRATION_WATCHDOG_ENABLED
from ..db.manager import current_db
from ..integration import SqlIngestBackend, layer
from ..integration.backends import DEFAULT_TRANSACTION_ROWS, clamp_transaction_rows
from ..integration.extractors import FileExtractor
from ..integration.files import (
    FORMAT_JSON,
    FORMAT_TEXT,
    FORMAT_XML,
    FORMATS as FILE_FORMATS,
    DeltaReader,
    FileAccessError,
    detect_records,
    detect_structure,
    json_shape,
    list_source_files,
    read_preview,
    read_text_file,
    resolve_source_file,
)
from ..integration.compound import OPS as COMPOUND_OPS
from ..integration.destinations import open_stored_connection
from ..integration.structured import iter_json_from_text, iter_xml_records, parse_xml
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


def _watchdog_counts(user: str | None) -> tuple[int, int]:
    """(watchdogs switched on, file sources that could have one) for this user."""
    file_sources = [s for s in security_store.list_sources(user) if s.kind == "file"]
    active = sum(
        1
        for s in file_sources
        if ((s.public()["config"].get("watchdog") or {}).get("enabled"))
    )
    return active, len(file_sources)


@router.get("/status")
def integration_status(request: Request) -> dict:
    """The abstraction-layer status for the signed-in user, plus the current target
    (the active connection's schema), how many extractors are registered, and how many
    of the user's file sources have their watchdog switched on."""
    user = _request_user(request)
    conn_id, schema, connected = _active_schema()
    active, total = _watchdog_counts(user)
    return {
        **layer.status_for(user).public(),
        "registeredExtractors": len(layer.extractors()),
        "activeConnectionId": conn_id,
        "activeSchema": schema,
        "connected": connected,
        "watchdogsActive": active,
        "watchdogsTotal": total,
        # The whole loop can be switched off for the deployment (PMW_INTEGRATION_WATCHDOG=0),
        # in which case an "enabled" watchdog still never polls — surfaced so the console
        # can say so instead of showing a count that quietly does nothing.
        "watchdogEnabled": INTEGRATION_WATCHDOG_ENABLED,
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
    # Unstructured (text) sources capture a field with a regex; semi-structured
    # (json/xml) sources locate it with a path selector. Exactly one is used per source
    # type, chosen by SourceTypeBody.format.
    regex: str = Field(default="", max_length=2000)
    path: str = Field(default="", max_length=1000)
    # `format` here is the timestamp strptime pattern for a timestamp field — NOT the
    # data format (that lives on SourceTypeBody).
    format: str = Field(default="", max_length=120)
    # Human-readable business name for a meta field (→ METAS.META_n_TITLE).
    title: str = Field(default="", max_length=200)


class CompoundCondition(BaseModel):
    """One test in a compound-step rule: a named field compared to a value."""

    field: str = Field(default="", max_length=60)
    op: str = "eq"
    value: str = Field(default="", max_length=500)


class CompoundRule(BaseModel):
    """Derive the final STEP from several fields at once (optional). All conditions
    must hold; the first matching rule wins."""

    step: str = Field(default="", max_length=500)
    when: list[CompoundCondition] = Field(default_factory=list)


class SourceTypeBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # The extraction spec captured by the wizard.
    sample: str = Field(default="", max_length=20000)
    # Data format: "text" (unstructured, regex — the default), "json" or "xml"
    # (semi-structured, path selectors).
    format: str = Field(default="text", max_length=8)
    # XML only: the repeating element that is one record (relative to the root).
    recordPath: str = Field(default="", max_length=500)
    fields: list[ExtractionField] = Field(default_factory=list)
    # Optional compound-step rules. Absent/empty = the plain step field is used as-is.
    compound: list[CompoundRule] = Field(default_factory=list, max_length=200)


def _spec_config(body: SourceTypeBody) -> str:
    """Serialise the extraction spec (sample + fields) to the source type's config JSON.
    Unknown roles fall back to 'meta'; an unknown format falls back to 'text'."""
    fmt = body.format if body.format in FILE_FORMATS else "text"
    structured = fmt in ("json", "xml")
    fields = [
        {
            "name": f.name.strip(),
            "role": f.role if f.role in ROLES else "meta",
            # Keep the selector the format uses (path for json/xml, regex for text) — and
            # drop the other so the stored spec is unambiguous.
            **({"path": f.path} if structured else {"regex": f.regex}),
            **({"format": f.format} if f.format else {}),
            **({"title": f.title.strip()} if f.title.strip() else {}),
        }
        for f in body.fields
    ]
    # Compound rules are stored only when complete (a resulting step + at least one
    # condition naming a field), so a half-built rule from the wizard can never relabel
    # events at import time.
    compound = [
        {
            "step": r.step.strip(),
            "when": [
                {
                    "field": c.field.strip(),
                    "op": c.op if c.op in COMPOUND_OPS else "eq",
                    "value": c.value,
                }
                for c in r.when
                if c.field.strip()
            ],
        }
        for r in body.compound
        if r.step.strip() and any(c.field.strip() for c in r.when)
    ]
    spec: dict = {"sample": body.sample, "format": fmt, "fields": fields}
    if fmt == "xml" and body.recordPath.strip():
        spec["recordPath"] = body.recordPath.strip()
    if compound:
        spec["compound"] = compound
    return json.dumps(spec)


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
    old = _source_owned(source_id, user)
    old_cfg = old.public()["config"] if old else {}
    # `lastRun` is written by the run endpoint, never edited in the wizard, so carry it
    # across a save — otherwise renaming a source would forget where it last imported to.
    if "lastRun" not in body.config and old_cfg.get("lastRun"):
        body.config["lastRun"] = old_cfg["lastRun"]
    config = _source_config(body, user)
    # If the file path changed, the old read checkpoint no longer applies — forget it so
    # the watchdog re-reads the new file from the start.
    old_path = str(old_cfg.get("path") or "")
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


@router.get("/files")
def list_files() -> list[dict]:
    """The files available in the sandboxed sources directory, for the source-type
    wizard's file picker. Empty in allow-any-path mode (no single root to enumerate)."""
    return list_source_files()


class RecordsBody(BaseModel):
    path: str = Field(default="", max_length=4000)
    # Optional explicit delimiter id (crlf/lf/cr/ff/rs/nul/blank); omitted = auto-detect.
    delimiter: str = Field(default="", max_length=16)
    limit: int = 5
    encoding: str = Field(default="utf-8", max_length=40)


@router.post("/files/records")
def detect_file_records(body: RecordsBody) -> dict:
    """Detect the record delimiter of a sandboxed file (or use the one given) and return
    the first N records split on it, plus the candidate delimiters with their counts."""
    try:
        return detect_records(
            body.path, body.delimiter or None, body.limit, body.encoding or "utf-8"
        )
    except FileAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class StructureBody(BaseModel):
    path: str = Field(default="", max_length=4000)
    limit: int = 5
    encoding: str = Field(default="utf-8", max_length=40)


@router.post("/files/structure")
def detect_file_structure(body: StructureBody) -> dict:
    """Detect a sandboxed file's data format (text / JSON / XML) and return rendered
    sample records plus suggested fields with their path selectors, for the source-type
    wizard. Text delegates to record-delimiter detection; JSON/XML parse a bounded head
    (XML via defusedxml — XXE-safe) and flatten the first record to suggest paths."""
    try:
        return detect_structure(body.path, body.encoding or "utf-8", body.limit)
    except FileAccessError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class RunBody(BaseModel):
    projectId: str = Field(min_length=1, max_length=100)
    # The destination connection, picked in the Run dialog. Optional only for callers
    # that still rely on the signed-in session's active connection; naming it here is
    # what lets a run be triggered without a session at all (remote push, scheduler).
    connectionId: str = Field(default="", max_length=100)
    # Delta upload: import only what was appended since this source's checkpoint. On by
    # default — re-running a source should top it up, not duplicate everything.
    delta: bool = True


def _source_owned(source_id: str, user: str | None):
    for s in security_store.list_sources(user):
        if s.id == source_id:
            return s
    return None


@router.get("/sources/{source_id}/checkpoint")
def source_checkpoint(source_id: str, request: Request) -> dict:
    """A File source's read checkpoint (byte offset, imported records, last error, when
    it last ran) — or nulls if it has never imported.

    One checkpoint per source, shared by both triggers: a manual delta run and a watchdog
    poll advance the same offset, which is what keeps them from importing a line twice
    between them."""
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
    """Forget the read checkpoint, so the next import — manual or watchdog — starts from
    the top of the file again. Nothing is deleted from the database, so re-importing after
    a reset appends the file's events a second time unless the project is cleared first."""
    user = _request_user(request)
    if _source_owned(source_id, user) is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    security_store.delete_source_checkpoint(source_id)
    return {"ok": True}


def _remember_last_run(source, user: str | None, *, connection_id: str, project_id: str) -> None:
    """Persist the destination an import used, so the Run dialog reopens on it.

    Best-effort bookkeeping: a failure here must never turn an import that already wrote
    its rows into an error for the caller.
    """
    try:
        cfg = source.public()["config"]
        last = cfg.get("lastRun") or {}
        if last.get("connectionId") == connection_id and last.get("projectId") == project_id:
            return  # unchanged — no write needed
        cfg["lastRun"] = {"connectionId": connection_id, "projectId": project_id}
        security_store.update_source(
            source.id, user, name=source.name, kind=source.kind, config=json.dumps(cfg)
        )
    except Exception as exc:  # noqa: BLE001 — the import itself already succeeded
        logx.warn(
            f"could not remember the destination for source {source.name!r}: {exc}",
            username=user or "", operation="import", tag=logx.TAG_DATA,
        )


@router.get("/connections/{conn_id}/projects")
async def list_destination_projects(conn_id: str, request: Request) -> dict:
    """The projects already stored in a destination connection's schema, so the Run
    dialog can offer them instead of asking the user to retype a project id.

    Deliberately *not* the manager-gated ``/api/connections/{id}/projects``: a developer
    is normally only **assigned** a connection, never its manager, so that endpoint would
    refuse them. Assignment is the gate here, exactly as it is for running.
    """
    user = _request_user(request)
    if not security_store.user_can_use(conn_id, user):
        raise HTTPException(status_code=404, detail="Connection not found.")
    conn = security_store.get_connection(conn_id, with_secrets=True)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found.")
    from ..db.schema_ddl import list_projects_with_counts

    return await list_projects_with_counts(
        host=conn.host, port=conn.port, username=conn.username, password=conn.password,
        schema=conn.schema, use_tls=conn.use_tls, cert_mode=conn.cert_mode,
        fingerprint=conn.fingerprint, min_rsa_bits=conn.min_rsa_bits,
    )


@router.post("/sources/{source_id}/run")
async def run_source(source_id: str, body: RunBody, request: Request) -> dict:
    """Run a File source's extraction into the chosen connection's schema under the given
    project id. The source must link a source type; the file is read sandboxed."""
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

    # ── destination ───────────────────────────────────────────────────────────
    # Resolve the destination to a *stored* connection (the caller names it, or we fall
    # back to the session's active one for older clients), then open a DEDICATED
    # connection for the run — never the user's live session. Reusing the live handle
    # would mean toggling its autocommit, and any missed restore would leave the shared
    # session in manual-commit mode (stale reads + held locks). Opening our own, like the
    # watchdog does, keeps the run's transaction fully isolated and disposable.
    mgr = current_db()
    conn_id = body.connectionId.strip()
    if conn_id:
        # Authorisation: assignment is the gate, re-checked here rather than trusted
        # from the dropdown — otherwise knowing a connection's id would be enough to
        # write into it with credentials the caller never had.
        if not security_store.user_can_use(conn_id, user):
            raise HTTPException(status_code=404, detail="Connection not found.")
        conn = security_store.get_connection(conn_id, with_secrets=True)
        if conn is None:
            raise HTTPException(status_code=404, detail="Connection not found.")
    else:
        conn_id = mgr.active_profile_id or ""
        if not conn_id:
            raise HTTPException(status_code=400, detail="Pick a destination connection first.")
        conn = security_store.get_connection(conn_id, with_secrets=True)
        if conn is None:
            raise HTTPException(
                status_code=400, detail="The active connection is not available for import."
            )

    schema = (conn.schema or "").strip()
    if not schema:
        raise HTTPException(
            status_code=400, detail=f"“{conn.name}” has no target schema configured."
        )

    # Open our own connection for the run; it is closed again in the finally below.
    try:
        opened, run_sql = await asyncio.to_thread(open_stored_connection, conn)
    except Exception as exc:  # noqa: BLE001 — a bad destination is a 400, not a 500
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to “{conn.name}”: {exc}",
        )
    backend = SqlIngestBackend(
        run_sql=run_sql, commit=opened.commit, rollback=opened.rollback,
    )

    # ── what to read ──────────────────────────────────────────────────────────
    # The read strategy depends on the source type's data FORMAT:
    #   • text / JSONL — byte-offset DELTA: re-running a source tops it up. The reader
    #     streams the whole remainder of the file to EOF in bounded chunks (DeltaReader),
    #     so a big file imports in one run while never holding more than a chunk at once.
    #     `delta=False` is the explicit "start over" and reads from byte 0.
    #   • JSON array / XML — whole-file, so it can't be byte-delta'd; instead it is
    #     IMPORT-ONCE by content signature: an unchanged file re-imports nothing, a
    #     changed one re-imports whole (`delta=False` forces the whole re-read either way).
    encoding = str(cfg.get("encoding") or "utf-8")
    fmt = st.public().get("format") or FORMAT_TEXT
    record_path = st.public().get("recordPath") or ""
    checkpoint = security_store.get_source_checkpoint(source_id)
    prev_records = int(checkpoint["records"]) if checkpoint else 0
    project_id = body.projectId.strip()
    transaction_rows = _transaction_rows(cfg)
    target = f"{conn.name if conn is not None else schema}/{schema}"
    compound = st.public().get("compound") or []

    # Validate the path/sandbox up front so a bad file fails fast with a clear 400.
    try:
        await asyncio.to_thread(resolve_source_file, path)
    except FileAccessError as exc:
        if opened is not None:
            await asyncio.to_thread(opened.close)
        raise HTTPException(status_code=400, detail=str(exc))

    # JSON physically comes as a top-level array or as JSONL/NDJSON; only JSONL can be
    # byte-delta'd (it is line-oriented). The array/object case joins XML on import-once.
    shape = ""
    if fmt == FORMAT_JSON:
        try:
            shape = await asyncio.to_thread(json_shape, path)
        except FileAccessError as exc:
            if opened is not None:
                await asyncio.to_thread(opened.close)
            raise HTTPException(status_code=400, detail=str(exc))
    use_byte_delta = fmt == FORMAT_TEXT or (fmt == FORMAT_JSON and shape == "jsonl")

    # These are filled by whichever branch runs, then used for the checkpoint + response.
    reader: DeltaReader | None = None
    content_sig = ""
    read_count = 0
    read_size = 0

    if use_byte_delta:
        prev_offset = int(checkpoint["byteOffset"]) if (checkpoint and body.delta) else 0
        prev_sig = str(checkpoint["signature"] or "") if (checkpoint and body.delta) else ""
        # An empty file, or nothing appended since the checkpoint, is a normal outcome —
        # the run still happens (so it shows in the pipeline) and simply writes no rows.
        reader = DeltaReader(path, encoding, prev_offset, prev_sig)
        extractor = FileExtractor(
            path=path, encoding=encoding, fields=fields, project_id=project_id,
            fmt=fmt, line_stream=reader, compound=compound,
        )
    else:
        # Whole-file structured read (JSON array/object or XML). Read + fingerprint the
        # file; if it's unchanged since the last import (delta on), there is nothing to do.
        try:
            text = await asyncio.to_thread(read_text_file, path, encoding)
        except FileAccessError as exc:  # oversize or unreadable
            if opened is not None:
                await asyncio.to_thread(opened.close)
            raise HTTPException(status_code=400, detail=str(exc))
        read_size = len(text.encode("utf-8", errors="ignore"))
        content_sig = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        unchanged = (
            body.delta and checkpoint
            and str(checkpoint.get("signature") or "") == content_sig
            and int(checkpoint.get("size") or 0) == read_size
        )
        if unchanged:
            if opened is not None:
                await asyncio.to_thread(opened.close)
            logx.usage(
                f"import skipped: {source.name!r} → {target} project {project_id} — "
                f"file unchanged since the last import",
                request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
            )
            return {
                "records": 0, "linesRead": 0,
                "detail": "Nothing new to import — the file is unchanged since the last import.",
            }
        try:
            if fmt == FORMAT_JSON:
                records = list(iter_json_from_text(text))
            else:
                root = await asyncio.to_thread(parse_xml, text)
                records = iter_xml_records(root, record_path)
        except ValueError as exc:  # malformed / unsafe document
            if opened is not None:
                await asyncio.to_thread(opened.close)
            raise HTTPException(status_code=400, detail=str(exc))
        read_count = len(records)
        extractor = FileExtractor(
            path=path, encoding=encoding, fields=fields, project_id=project_id,
            fmt=fmt, record_path=record_path, records=records, record_total=read_count,
            compound=compound,
        )

    logx.usage(
        f"import started: {source.name!r} (source type {st.name!r}) → {target} "
        f"project {project_id} — {'delta' if body.delta else 'full'} [{fmt}]",
        request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
    )
    try:
        result = await layer.run(
            user=user, extractor=extractor, backend=backend, schema=schema,
            connection_id=conn_id or None,
            connection_name=conn.name if conn is not None else None,
            source_name=source.name, source_type_name=st.name, trigger="manual",
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
    finally:
        if opened is not None:  # a connection we opened for this run only
            await asyncio.to_thread(opened.close)

    # Advance the checkpoint only once the rows are safely in — a failed run leaves it
    # where it was, so the next attempt re-reads rather than skipping.
    if reader is not None:
        # The reader drained the whole file, so end_offset is EOF. A full re-import (or a
        # from-scratch re-read after rotation) restarts the counter; a delta run adds to it.
        base_records = prev_records if (body.delta and not reader.rotated) else 0
        security_store.set_source_checkpoint(
            source_id, byte_offset=reader.end_offset, size=reader.size,
            signature=reader.signature, records=base_records + result.records, last_error="",
        )
        lines_read = reader.lines_read
    else:
        # Import-once: the checkpoint is the file's content signature + size, so the next
        # run recognises an unchanged file. A re-imported (changed) file replaces the count.
        security_store.set_source_checkpoint(
            source_id, byte_offset=read_size, size=read_size,
            signature=content_sig, records=result.records, last_error="",
        )
        lines_read = read_count

    _remember_last_run(source, user, connection_id=conn_id, project_id=project_id)
    logx.usage(
        f"import finished: {source.name!r} → {target} project {project_id} — "
        f"{result.detail} ({lines_read} record(s) read)",
        request=request, username=user or "", operation="import", tag=logx.TAG_DATA,
    )
    detail = result.detail
    if lines_read == 0:
        detail = (
            "Nothing new to import — the file has not grown since the last import."
            if body.delta and checkpoint
            else "Nothing to import — the file is empty."
        )
    # `linesRead` separates the two ways a run can write nothing: no new records at all
    # (normal for a delta run) versus records that matched nothing (a real misconfiguration).
    return {"records": result.records, "detail": detail, "linesRead": lines_read}


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
