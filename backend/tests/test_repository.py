"""Repository helper tests — the pure SQL-building and coercion logic that runs
without a database connection.

The clause builders in ProcessRepository are exercised through a stub manager;
no query is ever sent. This mirrors how the Swift app's SQL fragments were
implicitly validated by the queries that consumed them.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.models import FilterSpec, SampleSet
from app.db.repository import (
    ProcessRepository,
    as_bool,
    as_float,
    as_int,
    dur_label,
    esc,
    parse_date,
)


class _StubManager:
    """Stands in for DatabaseManager — the clause builders never call it."""

    is_connected = False


def repo(sample_set: SampleSet = SampleSet.original) -> ProcessRepository:
    r = ProcessRepository(_StubManager())  # type: ignore[arg-type]
    r.active_sample_set = sample_set
    return r


# ── Coercion helpers ──────────────────────────────────────────────────────────


def test_esc_doubles_single_quotes():
    assert esc("O'Brien") == "O''Brien"
    assert esc("plain") == "plain"


def test_as_int_handles_driver_types():
    assert as_int(5) == 5
    assert as_int(5.9) == 5
    assert as_int(Decimal("7")) == 7
    assert as_int("12") == 12
    assert as_int(None, default=3) == 3
    assert as_int("nonsense", default=1) == 1


def test_as_float_handles_driver_types():
    assert as_float(1) == 1.0
    assert as_float(Decimal("2.5")) == 2.5
    assert as_float("3.25") == 3.25
    assert as_float(None) is None
    assert as_float("nope") is None


def test_as_bool_handles_driver_types():
    assert as_bool(True) is True
    assert as_bool(1) is True
    assert as_bool(0) is False
    assert as_bool("TRUE") is True
    assert as_bool("f") is False
    assert as_bool(None) is False


def test_parse_date_accepts_multiple_formats():
    assert parse_date("2024-01-02 03:04:05") == datetime(2024, 1, 2, 3, 4, 5)
    assert parse_date("2024-01-02") == datetime(2024, 1, 2)
    assert parse_date(datetime(2024, 1, 2)) == datetime(2024, 1, 2)
    assert parse_date(date(2024, 1, 2)) == datetime(2024, 1, 2)
    assert parse_date(None) is None
    assert parse_date("not a date") is None


def test_dur_label_scales_units():
    # Below 10 units the Swift label keeps one decimal; at/above 10 it rounds.
    assert dur_label(30) == "30s"
    assert dur_label(300) == "5.0m"
    assert dur_label(900) == "15m"
    assert dur_label(7200) == "2.0h"
    assert dur_label(172800) == "2.0d"


# ── Clause builders ───────────────────────────────────────────────────────────


def test_sample_clause_uses_active_set():
    assert "SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL" in repo()._sample_clause()
    assert "SAMPLE_SET = 'SAMPLE_1'" in repo(SampleSet.sample1)._sample_clause()


def test_date_clause_bounds():
    clause = repo()._date_clause(datetime(2024, 1, 1), datetime(2024, 1, 31))
    assert "EVENT_TIME >= TIMESTAMP '2024-01-01 00:00:00'" in clause
    assert "EVENT_TIME <= TIMESTAMP '2024-01-31 23:59:59'" in clause
    assert repo()._date_clause(None, None) == ""


def test_step_clause_include_and_exclude():
    clause = repo()._step_clause(["Login"], ["Return"], "PID")
    assert "EVENT_ID IN" in clause and "STEP IN ('Login')" in clause
    assert "EVENT_ID NOT IN" in clause and "STEP IN ('Return')" in clause
    assert repo()._step_clause([], [], "PID") == ""


def test_step_clause_escapes_values():
    clause = repo()._step_clause(["O'Neil"], [], "PID")
    assert "'O''Neil'" in clause


def test_score_clause_only_when_bounded():
    assert repo()._score_clause(-9223372036854775808, 9223372036854775807, "PID") == ""
    clause = repo()._score_clause(-5, 20, "PID")
    assert "BETWEEN -5 AND 20" in clause


def test_all_filters_combines_clauses():
    f = FilterSpec(
        fromDate=datetime(2024, 1, 1),
        toDate=datetime(2024, 1, 31),
        includedSteps=["Login"],
        minSteps=2,
        maxScore=100,
    )
    sql = repo()._all_filters("PID", f, date_only=True)
    assert "SAMPLE_SET" in sql
    assert "EVENT_TIME >= TIMESTAMP '2024-01-01 00:00:00'" in sql
    assert "STEP IN ('Login')" in sql
    assert "COUNT(*) >= 2" in sql


# ── Note authorization scoping (security: cross-user write/delete) ─────────────


class _CapturingManager:
    """Captures the SQL the repository would run, and can return canned rows."""

    is_connected = True

    def __init__(self, rows=()):
        self.executed: list[str] = []
        self._rows = list(rows)

    async def execute(self, sql, *a, **k):
        self.executed.append(sql)
        return type("R", (), {"rows": self._rows})()

    async def execute_quiet(self, sql, *a, **k):
        self.executed.append(sql)


def _cap_repo(rows=()):
    r = ProcessRepository(_CapturingManager(rows))  # type: ignore[arg-type]
    return r, r.db  # type: ignore[return-value]


import asyncio

from app.models import NoteTarget, ProcessNote, FilterSnapshot


def test_delete_note_is_scoped_to_owner():
    r, mgr = _cap_repo()
    asyncio.run(r.delete_note("n-1", "proj", "Alice"))
    sql = mgr.executed[-1]
    # Must not delete another user's note: owner (or unowned/legacy) predicate present.
    assert "DELETE FROM NOTES" in sql
    assert "ID = 'n-1'" in sql
    assert "UPPER(NOTE_USER) = 'ALICE'" in sql
    assert "NOTE_USER = ''" in sql


def test_upsert_note_predelete_is_scoped_to_owner():
    r, mgr = _cap_repo()
    note = ProcessNote(
        id="n-2",
        text="hi",
        createdAt=datetime(2026, 1, 1),
        target=NoteTarget(type="node", value="A"),
        filterSnapshot=FilterSnapshot(fromDate=datetime(2026, 1, 1), toDate=datetime(2026, 1, 2)),
        username="Bob",
    )
    asyncio.run(r.upsert_note(note, "proj", "Bob"))
    predelete = mgr.executed[0]
    assert predelete.startswith("DELETE FROM NOTES") or "DELETE FROM NOTES" in predelete
    assert "ID = 'n-2'" in predelete
    assert "UPPER(NOTE_USER) = 'BOB'" in predelete  # can't clobber another user's ID


def test_note_owner_returns_author_or_none():
    r, _ = _cap_repo(rows=[["Carol"]])
    assert asyncio.run(r.note_owner("n-3")) == "Carol"
    r2, _ = _cap_repo(rows=[])
    assert asyncio.run(r2.note_owner("missing")) is None
