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
    # Only the author may delete — owner-only, no unowned/other-user fallback.
    assert "DELETE FROM NOTES" in sql
    assert "ID = 'n-1'" in sql
    assert "UPPER(NOTE_USER) = 'ALICE'" in sql
    assert "OR NOTE_USER = ''" not in sql


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


def test_upsert_note_whitelists_importance():
    r, mgr = _cap_repo()
    note = ProcessNote(
        id="n-8",
        text="hi",
        createdAt=datetime(2026, 1, 1),
        target=NoteTarget(type="node", value="A"),
        filterSnapshot=FilterSnapshot(fromDate=datetime(2026, 1, 1), toDate=datetime(2026, 1, 2)),
        username="Bob",
        importance="URGENT",
    )
    asyncio.run(r.upsert_note(note, "proj", "Bob"))
    insert = mgr.executed[-1]
    assert "IMPORTANCE" in insert and "'URGENT'" in insert

    # A bogus importance (or an injection attempt) is coerced to NORMAL.
    note.importance = "evil'; DROP TABLE NOTES; --"
    asyncio.run(r.upsert_note(note, "proj", "Bob"))
    assert "'NORMAL'" in mgr.executed[-1]
    assert "DROP TABLE" not in mgr.executed[-1]


def test_note_owner_returns_author_or_none():
    r, _ = _cap_repo(rows=[["Carol"]])
    assert asyncio.run(r.note_owner("n-3")) == "Carol"
    r2, _ = _cap_repo(rows=[])
    assert asyncio.run(r2.note_owner("missing")) is None


# ── Note update: comment append + resolved; owner-only reclassification ────────


def test_update_note_builds_partial_update_sql():
    r, mgr = _cap_repo()
    asyncio.run(
        r.update_note(
            "n-9",
            "proj",
            edited_by="Bob",
            comment_block="—— Bob · 2026-07-25 ——\nlooks fixed\n\n",
            resolved=True,
            importance="URGENT",
            is_shared=True,
        )
    )
    sql = mgr.executed[-1]
    assert sql.startswith("UPDATE NOTES SET")
    assert "|| NOTE" in sql and "looks fixed" in sql  # prepended (newest on top)
    assert "RESOLVED = TRUE" in sql
    assert "IMPORTANCE = 'URGENT'" in sql
    assert "IS_SHARED = TRUE" in sql
    assert "EDITED_BY = 'Bob'" in sql
    assert "ID = 'n-9'" in sql and "PROJECT_ID = 'proj'" in sql


def test_update_note_omits_untouched_fields():
    r, mgr = _cap_repo()
    asyncio.run(r.update_note("n-9", "proj", edited_by="Bob", resolved=False))
    sql = mgr.executed[-1]
    assert "RESOLVED = FALSE" in sql
    assert "|| NOTE" not in sql  # no comment prepended
    assert "IMPORTANCE" not in sql and "IS_SHARED" not in sql


def test_note_meta_returns_owner_and_shared():
    r, _ = _cap_repo(rows=[["alice", True]])
    assert asyncio.run(r.note_meta("n-1")) == ("alice", True)
    r2, _ = _cap_repo(rows=[])
    assert asyncio.run(r2.note_meta("missing")) is None


# ── update_note endpoint: per-field authorization ─────────────────────────────


class _EndpointRepo:
    def __init__(self, meta):
        self._meta = meta
        self.update_kwargs = None

    async def ensure_notes_table(self):
        pass

    async def note_meta(self, note_id):
        return self._meta

    async def update_note(self, note_id, project_id, **kw):
        self.update_kwargs = kw

    async def get_note(self, note_id, project_id):
        return ProcessNote(
            id=note_id,
            text="hi",
            createdAt=datetime(2026, 1, 1),
            target=NoteTarget(type="node", value="A"),
            filterSnapshot=FilterSnapshot(
                fromDate=datetime(2026, 1, 1), toDate=datetime(2026, 1, 2)
            ),
            username=self._meta[0] if self._meta else "",
        )


def _run_update(monkeypatch, *, caller, meta, body):
    from app.api import features

    repo = _EndpointRepo(meta)
    monkeypatch.setattr(features, "require_connection", lambda: None)
    monkeypatch.setattr(features, "repo", lambda: repo)
    monkeypatch.setattr(features, "current_user", lambda: caller)
    monkeypatch.setattr(features, "_note_display_name", lambda u: u)
    result = asyncio.run(features.update_note("proj", "n1", body))
    return repo, result


def test_endpoint_owner_can_reclassify(monkeypatch):
    from app.api.features import NoteUpdateBody

    repo, _ = _run_update(
        monkeypatch,
        caller="alice",
        meta=("alice", False),
        body=NoteUpdateBody(comment="more", resolved=True, importance="URGENT", isShared=True),
    )
    assert "more" in repo.update_kwargs["comment_block"]
    assert repo.update_kwargs["resolved"] is True
    assert repo.update_kwargs["importance"] == "URGENT"
    assert repo.update_kwargs["is_shared"] is True


def test_endpoint_non_owner_can_comment_but_not_reclassify(monkeypatch):
    from app.api.features import NoteUpdateBody

    repo, _ = _run_update(
        monkeypatch,
        caller="bob",
        meta=("alice", True),  # alice's shared note → bob may comment + resolve
        body=NoteUpdateBody(comment="fixed", resolved=True, importance="URGENT", isShared=False),
    )
    assert "fixed" in repo.update_kwargs["comment_block"]
    assert repo.update_kwargs["resolved"] is True
    assert repo.update_kwargs["importance"] is None  # ignored for non-owner
    assert repo.update_kwargs["is_shared"] is None


def test_endpoint_non_owner_private_note_is_403(monkeypatch):
    from fastapi import HTTPException

    from app.api.features import NoteUpdateBody

    with __import__("pytest").raises(HTTPException) as ei:
        _run_update(
            monkeypatch,
            caller="bob",
            meta=("alice", False),  # not shared → bob can't even see it
            body=NoteUpdateBody(comment="peek"),
        )
    assert ei.value.status_code == 403


def test_endpoint_missing_note_is_404(monkeypatch):
    from fastapi import HTTPException

    from app.api.features import NoteUpdateBody

    with __import__("pytest").raises(HTTPException) as ei:
        _run_update(monkeypatch, caller="bob", meta=None, body=NoteUpdateBody(comment="x"))
    assert ei.value.status_code == 404


# ── Security hardening (6th review): comment cap, create-only PUT, fail-closed ──


def test_note_comment_length_is_capped():
    from pydantic import ValidationError

    from app.api.features import NoteUpdateBody

    NoteUpdateBody(comment="x" * 4000)  # at the limit — accepted
    with __import__("pytest").raises(ValidationError):
        NoteUpdateBody(comment="x" * 4001)  # over the limit — rejected


def test_load_notes_is_fail_closed_for_empty_user():
    r, mgr = _cap_repo(rows=[])
    asyncio.run(r.load_notes("proj", ""))
    sql = mgr.executed[-1]
    # An unknown/empty user still only sees unowned or shared notes — never all.
    assert "IS_SHARED = TRUE" in sql
    assert "NOTE_USER = ''" in sql


def _run_save(monkeypatch, *, caller, existing_owner):
    from app.api import features

    class _Repo:
        def __init__(self):
            self.upserted = False

        async def ensure_notes_table(self):
            pass

        async def note_owner(self, note_id):
            return existing_owner  # None ⇒ brand-new note

        async def upsert_note(self, note, project_id, author):
            self.upserted = True

    repo = _Repo()
    monkeypatch.setattr(features, "require_connection", lambda: None)
    monkeypatch.setattr(features, "repo", lambda: repo)
    monkeypatch.setattr(features, "current_user", lambda: caller)
    monkeypatch.setattr(features, "_note_display_name", lambda u: u)
    note = ProcessNote(
        id="n1",
        text="hi",
        createdAt=datetime(2026, 1, 1),
        target=NoteTarget(type="node", value="A"),
        filterSnapshot=FilterSnapshot(fromDate=datetime(2026, 1, 1), toDate=datetime(2026, 1, 2)),
    )
    return repo, asyncio.run(features.save_note("proj", note))


def test_save_note_creates_a_new_note(monkeypatch):
    repo, result = _run_save(monkeypatch, caller="alice", existing_owner=None)
    assert repo.upserted is True
    assert result.username == "alice"


def test_save_note_rejects_existing_note_id(monkeypatch):
    from fastapi import HTTPException

    # PUT on an existing note is refused (409) so it can't overwrite the thread —
    # edits go through the append-only update endpoint instead.
    with __import__("pytest").raises(HTTPException) as ei:
        _run_save(monkeypatch, caller="bob", existing_owner="alice")
    assert ei.value.status_code == 409


# ── Note titles (subject shown separately in the overview / editor) ────────────


def test_upsert_note_includes_title():
    r, mgr = _cap_repo()
    note = ProcessNote(
        id="n-7",
        title="Bottleneck here",
        text="hi",
        createdAt=datetime(2026, 1, 1),
        target=NoteTarget(type="node", value="A"),
        filterSnapshot=FilterSnapshot(fromDate=datetime(2026, 1, 1), toDate=datetime(2026, 1, 2)),
        username="Bob",
    )
    asyncio.run(r.upsert_note(note, "proj", "Bob"))
    insert = mgr.executed[-1]
    assert "TITLE" in insert and "'Bottleneck here'" in insert


def test_update_note_sets_title():
    r, mgr = _cap_repo()
    asyncio.run(r.update_note("n-9", "proj", edited_by="Bob", title="New subject"))
    assert "TITLE = 'New subject'" in mgr.executed[-1]


def test_endpoint_comment_title_updates_note_title(monkeypatch):
    from app.api.features import NoteUpdateBody

    repo, _ = _run_update(
        monkeypatch,
        caller="alice",
        meta=("alice", False),
        body=NoteUpdateBody(title="Bottleneck", comment="we see delays here"),
    )
    # The comment's title becomes the note's shown title and appears in the header.
    assert repo.update_kwargs["title"] == "Bottleneck"
    assert "Bottleneck" in repo.update_kwargs["comment_block"]
