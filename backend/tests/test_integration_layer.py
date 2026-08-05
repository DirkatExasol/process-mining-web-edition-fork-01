"""Integration abstraction-layer tests: the extractor push API, status tracking,
the in-memory target and the SQL generation of the Exasol-oriented backend."""

from __future__ import annotations

import asyncio

import pytest

from app.integration import (
    AbstractionLayer,
    ColumnType,
    ExtractResult,
    ExtractorInfo,
    InMemoryIngestBackend,
    IngestError,
    LayerState,
    SqlIngestBackend,
)
from app.integration.backends import valid_identifier


def _run(coro):
    return asyncio.run(coro)


class _Extractor:
    def __init__(self, fn, id="demo-source"):
        self.info = ExtractorInfo(id=id, name="Demo", version="1.0", description="d")
        self._fn = fn

    def run(self, session):
        return self._fn(session)


# ── registry ──────────────────────────────────────────────────────────────────


def test_register_and_list_extractors():
    layer = AbstractionLayer()
    layer.register(_Extractor(lambda s: ExtractResult()))
    assert [i.id for i in layer.extractors()] == ["demo-source"]
    assert layer.extractors()[0].public()["name"] == "Demo"


def test_duplicate_registration_is_rejected():
    layer = AbstractionLayer()
    layer.register(_Extractor(lambda s: ExtractResult()))
    with pytest.raises(ValueError):
        layer.register(_Extractor(lambda s: ExtractResult()))


def test_bad_extractor_id_is_rejected():
    layer = AbstractionLayer()
    with pytest.raises(ValueError):
        layer.register(_Extractor(lambda s: ExtractResult(), id="Not A Slug"))


# ── running an extractor + status ─────────────────────────────────────────────


def _push_two(session):
    session.define_table("EVENTS", {"ID": ColumnType.INT, "NAME": ColumnType.STRING})
    session.log("starting")
    n = session.push("EVENTS", [{"ID": 1, "NAME": "a"}, {"ID": 2, "NAME": "b"}])
    return ExtractResult(records=n, tables=("EVENTS",))


def test_run_pushes_records_and_reports_completed_status():
    layer = AbstractionLayer()
    layer.register(_Extractor(_push_two))
    mem = InMemoryIngestBackend()

    result = _run(layer.run(user="alice", extractor="demo-source", backend=mem,
                            schema="PMW_STAGE", connection_id="c1"))
    assert result.records == 2

    st = layer.status_for("alice").public()
    assert st["state"] == LayerState.COMPLETED.value
    assert st["recordsPushed"] == 2
    assert st["tablesTouched"] == ["EVENTS"]
    assert st["schema"] == "PMW_STAGE"
    assert st["connectionId"] == "c1"
    assert st["lastError"] is None
    assert "starting" in st["messages"]
    # Rows actually landed in the target.
    assert mem.tables["PMW_STAGE"]["EVENTS"]["rows"] == [
        {"ID": 1, "NAME": "a"}, {"ID": 2, "NAME": "b"}]


def test_run_failure_is_captured_in_status():
    layer = AbstractionLayer()

    def boom(session):
        session.define_table("T", {"ID": ColumnType.INT})
        raise RuntimeError("source unreachable")

    layer.register(_Extractor(boom))
    with pytest.raises(RuntimeError):
        _run(layer.run(user="bob", extractor="demo-source",
                       backend=InMemoryIngestBackend(), schema="S"))
    st = layer.status_for("bob").public()
    assert st["state"] == LayerState.FAILED.value
    assert "source unreachable" in st["lastError"]


def test_status_is_per_user_and_starts_idle():
    layer = AbstractionLayer()
    assert layer.status_for("carol").public()["state"] == LayerState.IDLE.value


def test_run_unknown_extractor_raises():
    layer = AbstractionLayer()
    with pytest.raises(IngestError):
        _run(layer.run(user="x", extractor="nope",
                       backend=InMemoryIngestBackend(), schema="S"))


# ── ingest-session semantics ──────────────────────────────────────────────────


def test_push_before_define_table_raises():
    layer = AbstractionLayer()
    layer.register(_Extractor(lambda s: s.push("T", [{"ID": 1}])))
    with pytest.raises(IngestError):
        _run(layer.run(user="x", extractor="demo-source",
                       backend=InMemoryIngestBackend(), schema="S"))


def test_push_unknown_column_raises():
    layer = AbstractionLayer()

    def extra(session):
        session.define_table("T", {"ID": ColumnType.INT})
        session.push("T", [{"ID": 1, "GHOST": 9}])

    layer.register(_Extractor(extra))
    with pytest.raises(IngestError):
        _run(layer.run(user="x", extractor="demo-source",
                       backend=InMemoryIngestBackend(), schema="S"))


def test_missing_column_becomes_null():
    mem = InMemoryIngestBackend()
    layer = AbstractionLayer()

    def partial(session):
        session.define_table("T", {"ID": ColumnType.INT, "NAME": ColumnType.STRING})
        session.push("T", [{"ID": 1}])
        return ExtractResult()

    layer.register(_Extractor(partial))
    _run(layer.run(user="x", extractor="demo-source", backend=mem, schema="S"))
    assert mem.tables["S"]["T"]["rows"] == [{"ID": 1, "NAME": None}]


# ── SQL backend generation + safety ───────────────────────────────────────────


def test_sql_backend_generates_ddl_and_escaped_dml():
    sql: list[str] = []
    b = SqlIngestBackend(run_sql=lambda q: sql.append(q))
    b.create_table("PMW_STAGE", "EVENTS",
                   {"ID": ColumnType.INT, "NAME": ColumnType.STRING}, [])
    b.insert("PMW_STAGE", "EVENTS", ["ID", "NAME"], [[1, "O'Brien"], [2, None]])
    assert sql[0] == (
        'CREATE TABLE IF NOT EXISTS "PMW_STAGE"."EVENTS" '
        '("ID" DECIMAL(18,0), "NAME" VARCHAR(2000000))'
    )
    # Single quotes doubled, NULL rendered, schema/table quoted.
    assert sql[1] == (
        'INSERT INTO "PMW_STAGE"."EVENTS" ("ID", "NAME") '
        "VALUES (1, 'O''Brien'), (2, NULL)"
    )


def test_sql_backend_rejects_bad_identifiers():
    b = SqlIngestBackend(run_sql=lambda q: None)
    with pytest.raises(IngestError):
        b.create_table("PMW_STAGE", "EVENTS; DROP TABLE X", {"ID": ColumnType.INT}, [])
    with pytest.raises(IngestError):
        b.insert('S"X', "T", ["ID"], [[1]])


def test_valid_identifier_helper():
    assert valid_identifier("PMW_STAGE") == "PMW_STAGE"
    for bad in ("1abc", "a-b", 'a"b', "a b", "a;b", ""):
        with pytest.raises(IngestError):
            valid_identifier(bad)


def test_sql_backend_batches_large_inserts():
    sql: list[str] = []
    b = SqlIngestBackend(run_sql=lambda q: sql.append(q))
    b.insert("S", "T", ["ID"], [[i] for i in range(2500)])
    # 2500 rows / 1000 per batch → 3 INSERT statements.
    assert len(sql) == 3


# ── status endpoint ───────────────────────────────────────────────────────────


class _Req:
    def __init__(self, user=None):
        self.headers = {"x-pmw-user": user} if user else {}


def test_status_endpoint_reports_idle_and_registration_count():
    from app.api import integration as integ_api

    body = integ_api.integration_status(_Req("dave"))
    assert body["state"] == "idle"
    assert body["connected"] is False  # no live DB in the test process
    assert "registeredExtractors" in body
    assert "activeSchema" in body


def test_extractors_endpoint_returns_a_list():
    from app.api import integration as integ_api

    assert isinstance(integ_api.integration_extractors(), list)


def test_sql_backend_existing_keys_reads_and_stringifies():
    calls: list[str] = []
    def run(sql):
        calls.append(sql)
        return [["P1", "login"], ["P1", "view"]] if sql.startswith("SELECT") else []
    b = SqlIngestBackend(run_sql=run)
    keys = b.existing_keys("MINING", "STEPS", ["PROJECT_ID", "STEP"])
    assert keys == {("P1", "login"), ("P1", "view")}
    assert calls[0] == 'SELECT "PROJECT_ID", "STEP" FROM "MINING"."STEPS"'


def test_inmemory_existing_keys():
    b = InMemoryIngestBackend()
    b.create_table("S", "STEPS", {"PROJECT_ID": ColumnType.STRING, "STEP": ColumnType.STRING}, [])
    b.insert("S", "STEPS", ["PROJECT_ID", "STEP"], [["P", "a"], ["P", "b"]])
    assert b.existing_keys("S", "STEPS", ["PROJECT_ID", "STEP"]) == {("P", "a"), ("P", "b")}
    assert b.existing_keys("S", "MISSING", ["X"]) == set()
