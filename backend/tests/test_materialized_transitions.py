"""Pre-materialised transitions (backlog #3): the query-path selection in
ProcessRepository.load_transitions, its graceful fallback, and a proof that the
materialised pairs yield exactly the same directly-follows graph as the live
LEAD() query (run on SQLite, whose window functions match Exasol's here).
"""

from __future__ import annotations

import asyncio
import sqlite3

from app.db.repository import ProcessRepository
from app.models import FilterSpec


class _FakeTransDB:
    """Captures the SQL load_transitions runs and can fail the first call."""

    is_connected = True

    def __init__(self, use_mat: bool, *, fail_first: bool = False, rows=None):
        self.use_materialized_transitions = use_mat
        self.executed: list[str] = []
        self._fail_first = fail_first
        self._rows = rows or []

    async def execute(self, sql, *a, **k):
        self.executed.append(sql)
        if self._fail_first and len(self.executed) == 1:
            raise RuntimeError("object TRANSITIONS_RAW not found")
        return type("R", (), {"rows": self._rows})()


_ONE_EDGE = [["A", "B", 5, 1.0, 1.0, 1.0, 0.0]]


def test_reads_materialized_table_when_enabled():
    db = _FakeTransDB(True, rows=_ONE_EDGE)
    r = ProcessRepository(db)
    out = asyncio.run(r.load_transitions("P", FilterSpec()))
    assert len(db.executed) == 1
    assert "TRANSITIONS_RAW" in db.executed[0] and "LEAD(" not in db.executed[0]
    assert out[0].fromStep == "A" and out[0].occurrences == 5
    assert r.last_transitions_mode == "materialized"  # reported to the UI


def test_falls_back_to_live_when_materialized_missing():
    db = _FakeTransDB(True, fail_first=True, rows=_ONE_EDGE)
    r = ProcessRepository(db)
    out = asyncio.run(r.load_transitions("P", FilterSpec()))
    # Tried the materialised table first, then fell back to the live LEAD() query.
    assert len(db.executed) == 2
    assert "TRANSITIONS_RAW" in db.executed[0]
    assert "LEAD(" in db.executed[1]
    assert out[0].occurrences == 5
    # Enabled but the table is missing → reported as 'fallback' (not plain 'live'),
    # so the UI can tell the user their setting is on but a rebuild is pending.
    assert r.last_transitions_mode == "fallback"


def test_uses_live_query_when_disabled():
    db = _FakeTransDB(False, rows=[])
    r = ProcessRepository(db)
    asyncio.run(r.load_transitions("P", FilterSpec()))
    assert len(db.executed) == 1
    assert "LEAD(" in db.executed[0] and "TRANSITIONS_RAW" not in db.executed[0]
    assert r.last_transitions_mode == "live"


def test_materialized_dfg_matches_live_query():
    """Building TRANSITIONS_RAW then aggregating it must equal the live LEAD()
    aggregation, pair-for-pair with identical count/avg/min/max timings."""
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE JOURNEYS(PROJECT_ID,EVENT_ID,STEP,STEP_ID,EVENT_TIME,SAMPLE_SET)"
    )
    con.executemany(
        "INSERT INTO JOURNEYS VALUES(?,?,?,?,?,?)",
        [
            ("P", "e1", "Login", 0, "2024-01-01 09:00:00", "ORIGINAL"),
            ("P", "e1", "Search", 1, "2024-01-01 09:05:00", "ORIGINAL"),
            ("P", "e1", "Pay", 2, "2024-01-01 09:20:00", "ORIGINAL"),
            ("P", "e2", "Login", 0, "2024-01-02 10:00:00", "ORIGINAL"),
            ("P", "e2", "Pay", 1, "2024-01-02 10:10:00", "ORIGINAL"),
            ("P", "e3", "Login", 0, "2024-01-03 08:00:00", "ORIGINAL"),
            ("P", "e3", "Search", 1, "2024-01-03 08:02:00", "ORIGINAL"),
            ("P", "e3", "Search", 2, "2024-01-03 08:09:00", "ORIGINAL"),
        ],
    )

    # Build the pairs like rebuild_materialized_transitions does — via CREATE
    # TABLE AS SELECT so column types are inherited from JOURNEYS (the fix for the
    # Exasol "Incomparable Types" HASHTYPE vs VARCHAR failure).
    con.execute(
        """
        CREATE TABLE TRANSITIONS_RAW AS
        SELECT PROJECT_ID, EVENT_ID, FROM_STEP, TO_STEP, FROM_TIME, TO_TIME,
               (strftime('%s',TO_TIME) - strftime('%s',FROM_TIME)) AS DUR_SECS, SAMPLE_SET
        FROM (
            SELECT PROJECT_ID, EVENT_ID, SAMPLE_SET, STEP AS FROM_STEP, EVENT_TIME AS FROM_TIME,
                   LEAD(STEP)       OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_STEP,
                   LEAD(EVENT_TIME) OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_TIME
            FROM JOURNEYS
        ) WHERE TO_STEP IS NOT NULL
        """
    )

    live = con.execute(
        """
        SELECT FROM_STEP, TO_STEP, COUNT(*), AVG(DUR), MIN(DUR), MAX(DUR) FROM (
            SELECT FROM_STEP, TO_STEP,
                   (strftime('%s',TO_TIME) - strftime('%s',FROM_TIME)) AS DUR
            FROM (
                SELECT STEP AS FROM_STEP, EVENT_TIME AS FROM_TIME,
                       LEAD(STEP)       OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_STEP,
                       LEAD(EVENT_TIME) OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_TIME
                FROM JOURNEYS
            ) WHERE TO_STEP IS NOT NULL
        ) GROUP BY FROM_STEP, TO_STEP ORDER BY FROM_STEP, TO_STEP
        """
    ).fetchall()

    mat = con.execute(
        """
        SELECT FROM_STEP, TO_STEP, COUNT(*), AVG(DUR_SECS), MIN(DUR_SECS), MAX(DUR_SECS)
        FROM TRANSITIONS_RAW GROUP BY FROM_STEP, TO_STEP ORDER BY FROM_STEP, TO_STEP
        """
    ).fetchall()

    assert len(mat) > 0
    assert mat == live
