"""Integration abstraction-layer endpoints.

Read-only for now: the console polls the layer *status* and lists the *registered
extractors*. Triggering a run and managing extractors is built on top of this in a
later stage (the layer already exposes ``run``; it just isn't wired to an endpoint
yet). Reached by the integration console through its `/api` proxy; the signed-in
user arrives in the trusted ``X-PMW-User`` header the proxy injects.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..db.manager import current_db
from ..integration import layer
from ..integration.parsing import ROLES, detect_fields, regex_from_segment
from ..store.security import store as security_store

router = APIRouter(prefix="/api/integration", tags=["integration"])

USER_HEADER = "x-pmw-user"


def _request_user(request: Request) -> str | None:
    value = request.headers.get(USER_HEADER)
    return value.strip() if value and value.strip() else None


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
