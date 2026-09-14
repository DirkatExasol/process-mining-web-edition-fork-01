"""Write JSON journey entries posted to an AI Agent Logging Sink into a connection's
``JOURNEYS`` table, creating any unknown ``STEP`` on the fly.

This reuses the same building blocks as the File extractor — :class:`SqlIngestBackend`
and the JOURNEYS/PROJECTS/STEPS column maps + colour/shape/MD5 helpers — but writes
directly (a sink handles many small POSTs, so it does not go through the abstraction
layer's one-run-per-user model). One project per sink: entries land in the project with
the sink's ``TITLE_SHORT`` code (allocated/reused like the demo + File-import paths).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from ..db.schema_ddl import PROCESS_MINING_TABLES, _quote_ident
from .backends import IngestBackend, valid_identifier
from .contract import IngestError
from .extractors import (
    _JOURNEYS_COLUMNS,
    _PROJECTS_COLUMNS,
    _STEPS_COLUMNS,
    _md5,
    _step_color,
    _step_shape,
)

RunSql = Callable[[str], Any]


# ── per-sink bearer token (only the hash is ever stored) ──────────────────────


def hash_sink_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_sink_token(token: str, digest: str) -> bool:
    if not token or not digest:
        return False
    return hmac.compare_digest(hash_sink_token(token), digest)


# ── schema + write ────────────────────────────────────────────────────────────


def ensure_schema(run_sql: RunSql, schema: str) -> None:
    """Create ``schema`` and the process-mining tables if they don't exist (idempotent).
    Called once when a sink server opens its connection, so posts can assume the tables."""
    valid_identifier(schema)
    ident = _quote_ident(schema)
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {ident}")
    run_sql(f"OPEN SCHEMA {ident}")
    for _name, ddl in PROCESS_MINING_TABLES:
        run_sql(ddl)


def _parse_time(value: Any) -> datetime:
    """A posted eventTime → naive datetime (seconds). Missing/blank → server 'now';
    an ISO-8601 string (with optional trailing 'Z') is accepted."""
    if value in (None, ""):
        return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, microsecond=0)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise IngestError(f"Invalid eventTime {value!r} (want ISO-8601).") from exc
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0)


def _clean(value: Any) -> str:
    return "" if value is None else str(value)


def ingest_entries(
    backend: IngestBackend,
    commit: Callable[[], None],
    *,
    schema: str,
    title_short: str,
    entries: Iterable[dict],
) -> dict:
    """Write ``entries`` (each a JSON object with at least ``eventId`` and ``step``, and
    optionally a ``description`` written onto the STEP record) into ``schema``.JOURNEYS
    under the project coded ``title_short``. Unknown steps are added to STEPS with a
    freshly allocated activity id and the posted description. Returns
    ``{ingested, newSteps, projectId}``.

    The caller owns the connection; ``commit`` is invoked once the write succeeds. The
    JOURNEYS/PROJECTS/STEPS tables are (idempotently) defined here too, so this works
    against a fresh in-memory backend as well as a schema already provisioned on Exasol.
    """
    backend.create_table(schema, "JOURNEYS", _JOURNEYS_COLUMNS, ["PROJECT_ID", "EVENT_ID", "STEP"])
    backend.create_table(schema, "PROJECTS", _PROJECTS_COLUMNS, ["PROJECT_ID"])
    backend.create_table(schema, "STEPS", _STEPS_COLUMNS, ["PROJECT_ID", "STEP"])

    # Resolve the target project id (reuse by TITLE_SHORT code, else next free SMALLINT).
    projects = backend.existing_project_ids(schema)
    project_id = projects.get(title_short, max(projects.values(), default=0) + 1)

    # Seed the activity-id map so repeat step names reuse their id; new ones continue up.
    step_ids = backend.existing_step_ids(schema)
    next_step_id = max(step_ids.values(), default=0) + 1

    def activity_id(step: str) -> int:
        nonlocal next_step_id
        sid = step_ids.get(step)
        if sid is None:
            sid = next_step_id
            step_ids[step] = sid
            next_step_id += 1
        return sid

    journey_cols = list(_JOURNEYS_COLUMNS)
    rows: list[list[Any]] = []
    seen: set[str] = set()
    # First non-empty `description` seen for each step name → written onto the STEP record
    # (STEPS.DESCRIPTION), which is where a step's human label lives. A step (a KIND like
    # SKILL / DATABASE / WEB) is created once per project, so its description is taken from
    # the first event that introduces it.
    step_desc: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise IngestError("Each journey entry must be a JSON object.")
        event_id = _clean(entry.get("eventId") or entry.get("event_id")).strip()
        step = _clean(entry.get("step")).strip()
        if not event_id or not step:
            raise IngestError("Each entry needs a non-empty 'eventId' and 'step'.")
        seen.add(step)
        description = _clean(entry.get("description")).strip()
        if description and step not in step_desc:
            step_desc[step] = description
        rows.append([
            project_id,
            _md5(event_id),  # 32-char hex → HASHTYPE(16 BYTE)
            step,
            activity_id(step),
            _parse_time(entry.get("eventTime") or entry.get("event_time")),
            _clean(entry.get("meta1") or entry.get("meta_1")),
            _clean(entry.get("meta2") or entry.get("meta_2")),
            _clean(entry.get("meta3") or entry.get("meta_3")),
            "ORIGINAL",
        ])
    if not rows:
        return {"ingested": 0, "newSteps": [], "projectId": project_id}

    backend.insert(schema, "JOURNEYS", journey_cols, rows)

    # Ensure the PROJECTS row exists.
    if (str(project_id),) not in backend.existing_keys(schema, "PROJECTS", ["PROJECT_ID"]):
        backend.insert(schema, "PROJECTS", list(_PROJECTS_COLUMNS), [
            [project_id, title_short, "", title_short],
        ])

    # Create any step seen for the first time (deterministic colour/shape, zero score),
    # carrying the posted `description` onto the STEP's DESCRIPTION column.
    existing_steps = backend.existing_keys(schema, "STEPS", ["PROJECT_ID", "STEP"])
    new_steps = [s for s in sorted(seen) if (str(project_id), s) not in existing_steps]
    if new_steps:
        backend.insert(schema, "STEPS", list(_STEPS_COLUMNS), [
            [project_id, s, activity_id(s), step_desc.get(s, ""), _step_color(s), "#ffffff", 0,
             _step_shape(s), False, None]
            for s in new_steps
        ])

    commit()
    return {"ingested": len(rows), "newSteps": new_steps, "projectId": project_id}
