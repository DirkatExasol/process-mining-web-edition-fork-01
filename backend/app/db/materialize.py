"""Materialise an aggregate: copy a project into new high-level + detail projects.

Given a source project and a set of **member** step names, this builds two new
projects on a chosen (possibly new) schema/connection:

* **high-level** — a full copy of the source where each journey's maximal *run* of
  member steps is collapsed into a single ``Σ`` event (keeping the run's first entry
  time). The normal DFG engine then computes the Σ node's black-box metrics for free:
  internal transitions vanish, and incoming/outgoing edges connect the Σ node to the
  rest of the map.
* **detail** — only the member steps' events, so the sub-process can be opened
  standalone and drilled into.

The copy is read-then-reinsert (rows are read from the source into memory, then
inserted into the destination), so it works uniformly whether the target is the same
schema, a new schema, or a different connection/database.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .demo_data import _insert_journeys_sql as _demo_insert_journeys  # noqa: F401 (kept for parity)
from .demo_data import _sq

_BATCH = 1000


@dataclass
class SourceEvent:
    event_id: str
    step: str
    step_id: int | None
    event_time: str  # 'YYYY-MM-DD HH:MM:SS' (already formatted on read)
    meta1: str | None
    meta2: str | None
    meta3: str | None


@dataclass
class StepRow:
    step: str
    description: str
    bg_color: str
    fg_color: str
    score: int | None
    shape: str
    end_of_process: bool
    belongs_to: str


# ── pure transforms (unit-testable, no DB) ────────────────────────────────────


def collapse_high_level(
    events: list[SourceEvent], members: set[str], sigma: str
) -> list[SourceEvent]:
    """Collapse each journey's maximal consecutive run of member steps into ONE Σ event.

    Assumes ``events`` are ordered by (event_id, event_time, step_id). Non-member events
    pass through unchanged; a Σ event keeps the run's first event's time/step_id/meta."""
    out: list[SourceEvent] = []
    last_eid: str | None = None
    in_run = False
    for e in events:
        if e.event_id != last_eid:
            last_eid = e.event_id
            in_run = False
        if e.step in members:
            if in_run:
                continue  # same run — folded into the Σ event already emitted
            in_run = True
            out.append(
                SourceEvent(e.event_id, sigma, e.step_id, e.event_time, e.meta1, e.meta2, e.meta3)
            )
        else:
            in_run = False
            out.append(e)
    return out


def filter_detail(events: list[SourceEvent], members: set[str]) -> list[SourceEvent]:
    """Only the member steps' events — the partial sub-process."""
    return [e for e in events if e.step in members]


def sigma_step_row(sigma: str, members: set[str], steps: list[StepRow]) -> StepRow:
    """A synthetic STEPS row for the Σ super-step; score = sum of member scores."""
    total = sum((s.score or 0) for s in steps if s.step in members)
    return StepRow(
        step=sigma,
        description=f"Aggregate of {len(members)} steps.",
        bg_color="#5b6bff",
        fg_color="#ffffff",
        score=total or None,
        shape="rectangle",
        end_of_process=False,
        belongs_to="",
    )


# ── SQL helpers ───────────────────────────────────────────────────────────────


def _steps_insert_sqls(project_id: str, steps: list[StepRow]) -> list[str]:
    out: list[str] = []
    for s in steps:
        eop = "TRUE" if s.end_of_process else "FALSE"
        score = "NULL" if s.score is None else str(int(s.score))
        out.append(
            "INSERT INTO STEPS (PROJECT_ID, STEP, DESCRIPTION, BG_COLOR, FG_COLOR, SCORE, "
            "SHAPE, END_OF_PROCESS, BELONGS_TO) VALUES "
            f"('{_sq(project_id)}', '{_sq(s.step)}', '{_sq(s.description or '')}', "
            f"'{_sq(s.bg_color or '')}', '{_sq(s.fg_color or '')}', {score}, "
            f"'{_sq(s.shape or 'rectangle')}', {eop}, '{_sq(s.belongs_to or '')}')"
        )
    return out


def _journeys_insert_sql(project_id: str, rows: list[SourceEvent]) -> str:
    vals = ",\n  ".join(
        f"('{_sq(project_id)}', '{_sq(r.event_id)}', '{_sq(r.step)}', "
        f"{'NULL' if r.step_id is None else int(r.step_id)}, "
        f"TIMESTAMP '{r.event_time}', "
        f"{_lit(r.meta1)}, {_lit(r.meta2)}, {_lit(r.meta3)})"
        for r in rows
    )
    return (
        "INSERT INTO JOURNEYS (PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME, "
        f"META_1, META_2, META_3) VALUES\n  {vals}"
    )


def _lit(value: str | None) -> str:
    return "NULL" if value is None else f"'{_sq(str(value))}'"


# ── read the source ───────────────────────────────────────────────────────────


def _read_source(run_sql, schema: str, project_id: str) -> tuple[list[SourceEvent], list[StepRow], tuple[str, str, str]]:
    from .schema_ddl import _quote_ident

    run_sql(f"OPEN SCHEMA {_quote_ident(schema)}")
    ev_rows = run_sql(
        "SELECT EVENT_ID, STEP, STEP_ID, "
        "TO_CHAR(EVENT_TIME, 'YYYY-MM-DD HH24:MI:SS'), META_1, META_2, META_3 "
        f"FROM JOURNEYS WHERE PROJECT_ID = '{_sq(project_id)}' "
        "AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL) "
        "ORDER BY EVENT_ID, EVENT_TIME, STEP_ID"
    )
    events = [
        SourceEvent(str(r[0]), str(r[1]), None if r[2] is None else int(r[2]),
                    str(r[3]), r[4], r[5], r[6])
        for r in ev_rows
    ]
    st_rows = run_sql(
        "SELECT STEP, DESCRIPTION, BG_COLOR, FG_COLOR, SCORE, SHAPE, END_OF_PROCESS, BELONGS_TO "
        f"FROM STEPS WHERE PROJECT_ID = '{_sq(project_id)}'"
    )
    steps = [
        StepRow(str(r[0]), r[1] or "", r[2] or "", r[3] or "",
                None if r[4] is None else int(r[4]), r[5] or "rectangle",
                bool(r[6]), r[7] or "")
        for r in st_rows
    ]
    meta_rows = run_sql(
        "SELECT META_1_TITLE, META_2_TITLE, META_3_TITLE "
        f"FROM METAS WHERE PROJECT_ID = '{_sq(project_id)}'"
    )
    titles = (
        (str(meta_rows[0][0] or ""), str(meta_rows[0][1] or ""), str(meta_rows[0][2] or ""))
        if meta_rows
        else ("", "", "")
    )
    return events, steps, titles


# ── write a destination project ───────────────────────────────────────────────


def _write_project(
    run_sql,
    *,
    schema: str,
    provision: bool,
    project_id: str,
    title: str,
    description: str,
    meta_titles: tuple[str, str, str],
    steps: list[StepRow],
    events: list[SourceEvent],
) -> None:
    from .schema_ddl import PROCESS_MINING_TABLES, _quote_ident

    ident = _quote_ident(schema)
    if provision:
        run_sql(f"CREATE SCHEMA IF NOT EXISTS {ident}")
    run_sql(f"OPEN SCHEMA {ident}")
    if provision:
        for _name, ddl in PROCESS_MINING_TABLES:
            run_sql(ddl)

    # Replace any pre-existing rows for this fresh project id (idempotent re-run).
    for table in ("JOURNEYS", "STEPS", "METAS", "PROJECTS"):
        run_sql(f"DELETE FROM {table} WHERE PROJECT_ID = '{_sq(project_id)}'")

    run_sql(
        "INSERT INTO PROJECTS (PROJECT_ID, TITLE, DESCRIPTION) VALUES "
        f"('{_sq(project_id)}', '{_sq(title)}', '{_sq(description)}')"
    )
    run_sql(
        "INSERT INTO METAS (PROJECT_ID, META_1_TITLE, META_2_TITLE, META_3_TITLE) VALUES "
        f"('{_sq(project_id)}', '{_sq(meta_titles[0])}', '{_sq(meta_titles[1])}', "
        f"'{_sq(meta_titles[2])}')"
    )
    for sql in _steps_insert_sqls(project_id, steps):
        run_sql(sql)
    for offset in range(0, len(events), _BATCH):
        run_sql(_journeys_insert_sql(project_id, events[offset : offset + _BATCH]))


@dataclass
class Target:
    connection: object  # a Connection with secrets
    schema: str
    provision: bool  # create the schema + tables first
    project_id: str
    title: str


def _open_conn(conn):
    """Open a stored connection with **autocommit ON** and return ``(raw, run_sql)``.

    Autocommit must stay ON: the destination writes run ``CREATE SCHEMA`` / ``CREATE
    TABLE`` DDL, and on Exasol DDL held inside a never-committed transaction blocks
    forever ("waiting for commit of transaction …") against any concurrent session.
    This mirrors the proven demo-provisioning path (``generate_demo_content``), which
    also opens with the driver's default autocommit and issues one commit at the end.
    """
    from ..db.manager import DatabaseManager
    from ..models import DatabaseServer

    server = DatabaseServer(
        id="aggregate", host=conn.host, port=conn.port, username=conn.username,
        useTLS=conn.use_tls, certModeRaw=conn.cert_mode, fingerprint=conn.fingerprint,
        minRSAKeySizeBits=conn.min_rsa_bits, **{"schema": conn.schema or ""},
    )
    mgr = DatabaseManager.__new__(DatabaseManager)  # no store side effects
    raw = mgr._open(server, conn.password)  # default autocommit (ON)

    def run_sql(sql: str):
        st = raw.execute(sql)
        return [list(r) for r in st.fetchall()] if st.result_type == "resultSet" else []

    return raw, run_sql


async def materialize_aggregate(
    *,
    source_connection: object,
    source_project_id: str,
    members: set[str],
    sigma: str,
    high_level: Target,
    detail: Target,
) -> dict:
    """Read the source project once, then write the collapsed high-level project and the
    member-only detail project to their targets. Runs off the event loop."""

    def _run() -> None:
        # 1) read the whole source project into memory.
        src_raw, src_run = _open_conn(source_connection)
        try:
            events, steps, meta_titles = _read_source(
                src_run, source_connection.schema or "", source_project_id
            )
        finally:
            src_raw.close()

        hi_events = collapse_high_level(events, members, sigma)
        hi_steps = [s for s in steps if s.step not in members]
        hi_steps.append(sigma_step_row(sigma, members, steps))
        det_events = filter_detail(events, members)
        det_steps = [s for s in steps if s.step in members]

        # 2) write high-level and detail to their (possibly different) destinations.
        for tgt, ev, st in ((high_level, hi_events, hi_steps), (detail, det_events, det_steps)):
            raw, run = _open_conn(tgt.connection)
            try:
                _write_project(
                    run,
                    schema=tgt.schema,
                    provision=tgt.provision,
                    project_id=tgt.project_id,
                    title=tgt.title,
                    description="",
                    meta_titles=meta_titles,
                    steps=st,
                    events=ev,
                )
                raw.commit()
            finally:
                raw.close()

    await asyncio.to_thread(_run)
    return {
        "highLevelProjectId": high_level.project_id,
        "detailProjectId": detail.project_id,
    }
