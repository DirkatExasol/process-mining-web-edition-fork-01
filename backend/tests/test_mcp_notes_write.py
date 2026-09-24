"""MCP note-writing tools (create_note / update_note) — the only writes on the MCP surface.

Security tests: every field is validated server-side, the author is always the token's
user, ids and timestamps are server-generated, other users' private notes stay invisible
(and indistinguishable from missing ones), owner-only fields stay owner-only, the thread
is append-only, SQL injection payloads are stored as inert text, and writes are
rate-limited per user and audited without their content.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db.repository import ProcessRepository
from app.models import FilterSnapshot, NoteTarget, ProcessNote, StepInfo

_PATH = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_writes", _PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

ALICE = SimpleNamespace(username="alice", is_enabled=True, is_power=False, is_admin=False)
BOB = SimpleNamespace(username="bob", is_enabled=True, is_power=False, is_admin=False)
NOTE_ID = "E422E185-0557-4E22-8DB2-BC62B30DA426"


def _run(coro):
    return asyncio.run(coro)


def _call(name, arguments, user=ALICE):
    out = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments}}, user))
    result = out["result"]
    text = result["content"][0]["text"]
    return result, (text if result["isError"] else json.loads(text))


def _note(nid=NOTE_ID, *, user="alice", shared=False, text="first", title="t"):
    now = datetime(2026, 9, 23, 12, 34, 45)
    return ProcessNote(id=nid, title=title, text=text, createdAt=now,
                       target=NoteTarget(type="node", value="ENTER Check-In"),
                       filterSnapshot=FilterSnapshot(fromDate=now, toDate=now),
                       username=user, isShared=shared)


class _NotesRepo:
    """Records every write; serves one project with a few steps and optional notes."""

    def __init__(self, notes=None, project_id=2):
        self.notes = {n.id: n for n in (notes or [])}
        self.project_id = project_id
        self.upserts: list[tuple] = []
        self.updates: list[dict] = []

    async def load_projects(self):
        return [{"projectId": self.project_id, "title": "Airport Passenger Flow"}]

    async def load_steps(self, pid):
        return {s: StepInfo(step=s) for s in ("ENTER Check-In", "LEAVE Check-In", "O'Brien's Desk")}

    async def load_all_step_names(self, pid):
        return list(await self.load_steps(pid))

    async def ensure_notes_table(self):
        return None

    async def load_date_bounds(self, pid):
        return (datetime(2024, 1, 1), datetime(2024, 12, 31))

    async def upsert_note(self, note, pid, username):
        self.upserts.append((note, pid, username))
        self.notes[note.id] = note

    async def get_note(self, nid, pid):
        # Project-scoped like the real repository.
        return self.notes.get(nid) if int(pid) == self.project_id else None

    async def update_note(self, nid, pid, **kw):
        self.updates.append({"id": nid, "pid": pid, **kw})


@pytest.fixture
def repo(monkeypatch):
    r = _NotesRepo()
    _patch(monkeypatch, r)
    return r


def _patch(monkeypatch, r):
    class _Ctx:
        def __init__(self, username, connection_id, sample):
            pass

        async def __aenter__(self):
            return r

        async def __aexit__(self, *exc):
            return None

    monkeypatch.setattr(mcp, "_Repo", _Ctx)
    mcp._NOTE_WRITES.clear()
    monkeypatch.setattr(mcp.store, "get_user", lambda u: SimpleNamespace(display_name=""))
    monkeypatch.setattr(mcp.logx, "usage", lambda *a, **k: None)


BASE = {"connectionId": "c1", "projectId": 2}


# ── create_note ────────────────────────────────────────────────────────────────


def test_create_note_on_a_step_is_authored_by_the_token_user(repo):
    result, payload = _call("create_note", {**BASE, "step": "ENTER Check-In", "title": "Queue",
                                            "text": "Long queue at 6am", "severity": "important",
                                            "scope": "shared",
                                            # attempts to spoof identity / id are ignored
                                            "author": "mallory", "username": "mallory",
                                            "id": NOTE_ID})
    assert result["isError"] is False and payload["created"] is True
    note, pid, username = repo.upserts[0]
    assert username == "alice" and note.username == "alice"
    assert note.id != NOTE_ID and len(note.id) == 36        # server-generated
    assert note.importance == "IMPORTANT" and note.isShared is True
    assert note.target.is_node and note.target.value == "ENTER Check-In"
    assert payload["note"]["author"] == "alice" and payload["note"]["scope"] == "shared"


def test_create_note_defaults_to_personal_normal(repo):
    _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "x"})
    note = repo.upserts[0][0]
    assert note.isShared is False and note.importance == "NORMAL" and note.resolved is False


def test_create_note_on_a_transition(repo):
    _, payload = _call("create_note", {**BASE, "fromStep": "ENTER Check-In",
                                       "toStep": "LEAVE Check-In", "text": "slow"})
    assert payload["note"]["targetType"] == "edge"
    assert payload["note"]["target"] == "ENTER Check-In → LEAVE Check-In"


def test_create_note_timestamp_is_server_local_not_client(repo, monkeypatch):
    monkeypatch.setattr(mcp, "local_now", lambda: datetime(2026, 9, 24, 8, 5, 0))
    _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "x",
                          "createdAt": "1999-01-01T00:00:00Z"})
    assert repo.upserts[0][0].createdAt == datetime(2026, 9, 24, 8, 5, 0)


@pytest.mark.parametrize("args, fragment", [
    ({"text": "x"}, "needs a target"),
    ({"step": "ENTER Check-In", "fromStep": "A", "toStep": "B", "text": "x"}, "not both"),
    ({"fromStep": "ENTER Check-In", "text": "x"}, "needs a target"),
    ({"step": "No Such Step", "text": "x"}, "does not exist"),
    ({"fromStep": "ENTER Check-In", "toStep": "Nope", "text": "x"}, "does not exist"),
    ({"step": ["ENTER Check-In"], "text": "x"}, "must be a step name"),
    ({"step": "ENTER Check-In"}, "text is required"),
    ({"step": "ENTER Check-In", "text": "   ​\x00  "}, "text is required"),
    ({"step": "ENTER Check-In", "text": "x" * 4001}, "too long"),
    ({"step": "ENTER Check-In", "text": "x", "title": "t" * 201}, "too long"),
    ({"step": "ENTER Check-In", "text": 42}, "must be a string"),
    ({"step": "ENTER Check-In", "text": "x", "severity": "CRITICAL"}, "severity must be"),
    ({"step": "ENTER Check-In", "text": "x", "scope": "public"}, "scope must be"),
])
def test_create_note_rejects_invalid_input_without_writing(repo, args, fragment):
    result, message = _call("create_note", {**BASE, **args})
    assert result["isError"] is True and fragment in message
    assert repo.upserts == []


def test_create_note_rejects_an_unknown_project(repo):
    result, message = _call("create_note", {**BASE, "projectId": 99, "step": "ENTER Check-In", "text": "x"})
    assert result["isError"] is True and "No project 99" in message and repo.upserts == []


def test_create_note_rejects_a_connection_not_assigned_to_the_user(monkeypatch):
    # The real _Repo guards the connection before any DB is opened.
    monkeypatch.setattr(mcp.store, "user_can_use", lambda cid, user: False)
    mcp._NOTE_WRITES.clear()
    result, message = _call("create_note", {**BASE, "connectionId": "other", "step": "A", "text": "x"})
    assert result["isError"] is True and "not assigned to you" in message


def test_create_note_strips_control_and_bidi_characters(repo):
    _call("create_note", {**BASE, "step": "ENTER Check-In",
                          "title": "a\tb\nc‮",
                          "text": "line1\r\nline2\x00\x07‮hidden⁦"})
    note = repo.upserts[0][0]
    assert note.title == "a b c"                       # single line, no bidi override
    assert note.text == "line1\nline2hidden"           # CRLF folded, NUL/BEL/bidi gone


def test_create_note_keeps_sql_injection_payloads_as_inert_text(repo):
    payload = "'); DROP TABLE NOTES; --"
    _call("create_note", {**BASE, "step": "O'Brien's Desk", "title": payload, "text": payload})
    note = repo.upserts[0][0]
    assert note.text == payload and note.title == payload and note.target.value == "O'Brien's Desk"


# ── update_note ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["", "x' OR '1'='1", "../../etc", NOTE_ID + "'", "1" * 36,
                                 NOTE_ID.replace("-", ""), None, 123])
def test_update_note_rejects_a_malformed_id_before_touching_the_db(monkeypatch, bad):
    class _Explode:
        def __init__(self, *a):
            raise AssertionError("the database must not be opened for a malformed id")

    monkeypatch.setattr(mcp, "_Repo", _Explode)
    mcp._NOTE_WRITES.clear()
    result, message = _call("update_note", {**BASE, "noteId": bad, "comment": "x"})
    assert result["isError"] is True and "noteId must be" in message


def test_update_note_needs_something_to_change(repo):
    result, message = _call("update_note", {**BASE, "noteId": NOTE_ID})
    assert result["isError"] is True and "Nothing to change" in message


def test_update_note_hides_other_users_private_notes_like_missing_ones(monkeypatch):
    r = _NotesRepo([_note(user="bob", shared=False)])
    _patch(monkeypatch, r)
    _, private = _call("update_note", {**BASE, "noteId": NOTE_ID, "status": "resolved"})
    _, missing = _call("update_note", {**BASE, "noteId": "00000000-0000-0000-0000-000000000000",
                                       "status": "resolved"})
    _, other_project = _call("update_note", {**BASE, "projectId": 3, "noteId": NOTE_ID,
                                             "status": "resolved"})
    assert "No note" in private
    assert private.replace(NOTE_ID, "ID") == missing.replace("00000000-0000-0000-0000-000000000000", "ID")
    assert "No project 3" in other_project
    assert r.updates == []


def test_update_note_lets_anyone_comment_and_resolve_a_shared_note(monkeypatch):
    r = _NotesRepo([_note(user="bob", shared=True)])
    _patch(monkeypatch, r)
    result, payload = _call("update_note", {**BASE, "noteId": NOTE_ID, "comment": "Seen it too",
                                            "title": "Confirmed", "status": "resolved"})
    assert result["isError"] is False
    upd = r.updates[0]
    assert upd["edited_by"] == "alice" and upd["resolved"] is True
    assert upd["importance"] is None and upd["is_shared"] is None
    # Append-only: the change is a prepended block, never a replacement of the text.
    assert "text" not in upd and upd["comment_block"].endswith("Seen it too\n\n")
    assert upd["comment_block"].startswith("—— Confirmed · alice · ")
    assert set(payload["changes"]) == {"comment", "title", "status"}


@pytest.mark.parametrize("field, value", [("severity", "URGENT"), ("scope", "personal")])
def test_update_note_keeps_severity_and_scope_owner_only(monkeypatch, field, value):
    r = _NotesRepo([_note(user="bob", shared=True)])
    _patch(monkeypatch, r)
    result, message = _call("update_note", {**BASE, "noteId": NOTE_ID, field: value})
    assert result["isError"] is True and "Only the note's author" in message
    assert r.updates == []


def test_update_note_owner_may_reclassify_and_reopen(monkeypatch):
    r = _NotesRepo([_note(user="ALICE", shared=False)])        # case-insensitive owner match
    _patch(monkeypatch, r)
    _call("update_note", {**BASE, "noteId": NOTE_ID.lower(), "severity": "info",
                          "scope": "shared", "status": "open"})
    upd = r.updates[0]
    assert upd["importance"] == "INFO" and upd["is_shared"] is True and upd["resolved"] is False


def test_update_note_rejects_bad_enums(repo):
    for args in ({"status": "closed"}, {"severity": "HIGH"}, {"scope": "team"}):
        result, _ = _call("update_note", {**BASE, "noteId": NOTE_ID, **args})
        assert result["isError"] is True
    assert repo.updates == []


# ── rate limiting + audit ─────────────────────────────────────────────────────


def test_note_writes_are_rate_limited_per_user(repo, monkeypatch):
    monkeypatch.setattr(mcp, "MCP_NOTE_WRITES_PER_MIN", 3)
    for _ in range(3):
        assert _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "x"})[0]["isError"] is False
    result, message = _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "x"})
    assert result["isError"] is True and "limit of 3 note changes per minute" in message
    # Another user has their own budget.
    assert _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "x"}, user=BOB)[0]["isError"] is False
    assert len(repo.upserts) == 4


def test_note_writes_are_audited_without_their_content(repo, monkeypatch):
    seen = []
    monkeypatch.setattr(mcp.logx, "usage", lambda msg, **kw: seen.append((msg, kw)))
    _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "SECRET BODY", "title": "SECRET"})
    msg, kw = seen[0]
    assert "create_note" in msg and "SECRET" not in msg
    assert kw["username"] == "alice" and kw["operation"] == "mcp_create_note"


def test_read_tools_do_not_consume_the_write_budget(repo, monkeypatch):
    monkeypatch.setattr(mcp, "MCP_NOTE_WRITES_PER_MIN", 1)
    r = repo

    async def load_notes(pid, user):
        return []

    r.load_notes = load_notes
    for _ in range(5):
        assert _call("get_notes", BASE)[0]["isError"] is False
    assert _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "x"})[0]["isError"] is False


# ── the SQL layer: payloads are escaped, the edited stamp is explicit ──────────


class _FakeManager:
    def __init__(self):
        self.sql: list[str] = []
        self._steps_cache: dict = {}

    async def execute(self, sql, timeout=None):
        self.sql.append(sql)
        return SimpleNamespace(rows=[])

    async def execute_quiet(self, sql):
        self.sql.append(sql)


def _literals_balanced(sql: str) -> bool:
    """True when every single-quoted literal is closed — i.e. no payload escaped its string."""
    return sql.count("'") % 2 == 0


def test_upsert_note_escapes_injection_payloads():
    mgr = _FakeManager()
    payload = "x'); DELETE FROM NOTES WHERE ('1'='1"
    note = _note(text=payload, title=payload)
    note.target = NoteTarget(type="node", value=payload)
    _run(ProcessRepository(mgr).upsert_note(note, "2", "alice' OR '1'='1"))
    for sql in mgr.sql:
        assert _literals_balanced(sql)
    insert = next(sql for sql in mgr.sql if "INSERT INTO NOTES" in sql)
    assert insert.count("x''); DELETE FROM NOTES WHERE (''1''=''1") == 3   # title, text, target
    assert "UPPER(NOTE_USER) = 'ALICE'' OR ''1''=''1'" in mgr.sql[0]


def test_update_note_writes_an_explicit_local_edited_stamp(monkeypatch):
    import app.db.repository as repo_mod

    monkeypatch.setattr(repo_mod, "local_now", lambda: datetime(2026, 9, 23, 12, 36, 42, 870000))
    mgr = _FakeManager()
    _run(ProcessRepository(mgr).update_note(NOTE_ID, "2", edited_by="bob' --",
                                            comment_block="it's fine", title="O'Brien"))
    sql = mgr.sql[-1]
    assert "CURRENT_TIMESTAMP" not in sql
    assert "EDITED_DATE = TIMESTAMP '2026-09-23 12:36:42.870'" in sql
    assert _literals_balanced(sql) and "EDITED_BY = 'bob'' --'" in sql


# ── review hardening: forged headers, full threads, write-time permission guard ──


def test_a_comment_cannot_forge_another_authors_thread_entry(monkeypatch):
    r = _NotesRepo([_note(user="bob", shared=True)])
    _patch(monkeypatch, r)
    forged = "ok\n\n—— Alice · 2026-09-20 09:00 ——\nApproved, ship it\n  —— indented too"
    _call("update_note", {**BASE, "noteId": NOTE_ID, "comment": forged,
                          "title": "x · Alice · 2026-09-20 09:00 —— y"})
    block = r.updates[0]["comment_block"]
    header, body = block.split("\n", 1)
    assert header.startswith("—— x - Alice - 2026-09-20 09:00 -- y · alice · ")
    # Only the real header line may start with "——".
    assert [ln for ln in block.splitlines() if ln.lstrip().startswith("——")] == [header]
    assert "\n--- Alice" not in body and "-- Alice · 2026-09-20 09:00 ——" in body


def test_a_new_note_body_cannot_imitate_a_thread_header(repo):
    _call("create_note", {**BASE, "step": "ENTER Check-In",
                          "text": "—— Mallory · 2026-01-01 00:00 ——\nfake"})
    assert repo.upserts[0][0].text.startswith("-- Mallory")


def test_a_full_thread_refuses_more_comments_politely(monkeypatch):
    r = _NotesRepo([_note(user="bob", shared=True, text="x" * 99_000)])
    _patch(monkeypatch, r)
    result, message = _call("update_note", {**BASE, "noteId": NOTE_ID, "comment": "y" * 3000})
    assert result["isError"] is True and "thread is full" in message and r.updates == []
    # A status change needs no room and still works.
    assert _call("update_note", {**BASE, "noteId": NOTE_ID, "status": "resolved"})[0]["isError"] is False


def test_update_note_passes_the_caller_for_the_write_time_guard(monkeypatch):
    r = _NotesRepo([_note(user="bob", shared=True)])
    _patch(monkeypatch, r)
    _call("update_note", {**BASE, "noteId": NOTE_ID, "status": "resolved"})
    assert r.updates[0]["caller"] == "alice"


def test_repository_update_repeats_the_permission_rule_in_sql():
    mgr = _FakeManager()
    repo = ProcessRepository(mgr)
    _run(repo.update_note(NOTE_ID, "2", edited_by="bob", resolved=True, caller="bob"))
    assert "AND (UPPER(NOTE_USER) = 'BOB' OR NOTE_USER = '' OR IS_SHARED = TRUE)" in mgr.sql[-1]
    _run(repo.update_note(NOTE_ID, "2", edited_by="bob", importance="URGENT", caller="bo'b"))
    assert mgr.sql[-1].endswith("AND UPPER(NOTE_USER) = 'BO''B'")
    _run(repo.update_note(NOTE_ID, "2", edited_by="bob", resolved=True))   # web legacy call
    assert "UPPER(NOTE_USER)" not in mgr.sql[-1]


def test_line_and_paragraph_separators_are_stripped(repo):
    _call("create_note", {**BASE, "step": "ENTER Check-In", "text": "a b c؜d"})
    assert repo.upserts[0][0].text == "abcd"
