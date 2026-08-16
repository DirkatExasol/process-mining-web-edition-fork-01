"""Aggregates — collapse a connected set of steps into a Σ super-step.

Developer-only. Given a source project and a set of member steps, materialise:
  * a high-level project where each journey's member run is one Σ event, and
  * a detail project holding only the member steps' events (for drill-down),
into a chosen (possibly new) schema/connection, then record the Σ→detail link so the
app can offer drill-down.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db.manager import current_user, friendly_error
from ..db.materialize import Target, materialize_aggregate
from ..store.security import store as security_store

router = APIRouter(prefix="/api", tags=["aggregates"])


class _OutputTarget(BaseModel):
    name: str
    targetConnectionId: str = ""  # empty → the source connection
    targetSchema: str = ""  # empty → the target connection's own schema


class AggregateBody(BaseModel):
    connectionId: str  # source connection
    members: list[str]
    sigmaName: str = "Σ Aggregate"
    highLevel: _OutputTarget
    detail: _OutputTarget


# ── authorisation ────────────────────────────────────────────────────────────


def _require_developer() -> None:
    """Creating aggregates is limited to developers (and admins as superusers)."""
    username = current_user()
    user = security_store.get_user(username) if username else None
    if user is None or not user.is_enabled or not (user.is_admin or user.is_developer):
        raise HTTPException(
            status_code=403,
            detail="Designing aggregates is available to developers and administrators only.",
        )


def _require_assigned(connection_id: str) -> None:
    if not security_store.user_can_use((connection_id or "").strip(), current_user()):
        raise HTTPException(status_code=403, detail="This connection is not available to you.")


def _resolve(conn_id: str):
    conn = security_store.get_connection((conn_id or "").strip(), with_secrets=True)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found.")
    return conn


def _schema_of(body_schema: str, conn) -> str:
    schema = (body_schema or "").strip() or (conn.schema or "").strip()
    if not schema:
        raise HTTPException(status_code=400, detail="A target schema is required.")
    return schema


@router.post("/projects/{project_id}/aggregate")
async def create_aggregate(project_id: str, body: AggregateBody) -> dict[str, Any]:
    _require_developer()

    # The source and BOTH targets must be connections assigned to the caller (IDOR).
    _require_assigned(body.connectionId)
    hi_conn_id = (body.highLevel.targetConnectionId or body.connectionId).strip()
    det_conn_id = (body.detail.targetConnectionId or body.connectionId).strip()
    _require_assigned(hi_conn_id)
    _require_assigned(det_conn_id)

    members = {m.strip() for m in body.members if m and m.strip()}
    if len(members) < 2:
        raise HTTPException(status_code=400, detail="Select at least two connected steps to aggregate.")
    sigma = (body.sigmaName or "").strip() or "Σ Aggregate"
    if not body.highLevel.name.strip() or not body.detail.name.strip():
        raise HTTPException(status_code=400, detail="Both the high-level and detail project names are required.")

    src = _resolve(body.connectionId)
    hi_conn = _resolve(hi_conn_id)
    det_conn = _resolve(det_conn_id)

    hi_pid = f"agg_{uuid.uuid4().hex[:12]}"
    det_pid = f"aggd_{uuid.uuid4().hex[:12]}"

    try:
        await materialize_aggregate(
            source_connection=src,
            source_project_id=project_id,
            members=members,
            sigma=sigma,
            high_level=Target(hi_conn, _schema_of(body.highLevel.targetSchema, hi_conn), True, hi_pid, body.highLevel.name.strip()),
            detail=Target(det_conn, _schema_of(body.detail.targetSchema, det_conn), True, det_pid, body.detail.name.strip()),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a bad connection/schema is a 400, not a 500
        raise HTTPException(status_code=400, detail=f"Could not build the aggregate: {friendly_error(exc)}") from exc

    link = security_store.add_aggregate_link(
        {
            "connectionId": hi_conn.id,
            "projectId": hi_pid,
            "sigmaStep": sigma,
            "detailConnectionId": det_conn.id,
            "detailProjectId": det_pid,
        }
    )
    return {
        "highLevelProjectId": hi_pid,
        "highLevelConnectionId": hi_conn.id,
        "detailProjectId": det_pid,
        "detailConnectionId": det_conn.id,
        "sigmaStep": sigma,
        "link": link,
    }


@router.get("/projects/{project_id}/aggregates")
async def list_aggregates(project_id: str, connectionId: str = "") -> dict[str, Any]:
    """Aggregate links whose high-level project is this (connection, project) — feeds the
    app's Σ 'drill down'. Any user assigned to the connection may read them."""
    _require_assigned(connectionId)
    return {"aggregates": security_store.aggregates_for(connectionId, project_id)}
