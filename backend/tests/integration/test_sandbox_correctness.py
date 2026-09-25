"""First harness slice — process-mining correctness against a live Exasol.

Provisions a throwaway schema on a disposable Exasol (Exasol Nano — ARM64/x86), ingests the
10-step order-to-cash fixture from docs/CORRECTNESS-TEST-PLAN.md, and asserts the calibrated
baseline (F0, no filter) through the real ProcessRepository (the REST path). Filters, the full
metric matrix and the MCP-surface equivalence come in later slices.

Opt-in: skipped unless a Exasol is reachable at PMW_SANDBOX_DSN (default 127.0.0.1:8563,
sys/exasol). It NEVER touches existing data — it creates and drops its own schema.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta

import pytest

from app.db import schema_ddl
from app.db.manager import DatabaseManager
from app.db.repository import ProcessRepository
from app.models import DatabaseServer, FilterSpec, HappyPath, HappyPathNode, SampleSet
from app.services.analytics import happy_path_conformance

HOST = os.environ.get("PMW_SANDBOX_HOST", "127.0.0.1")
PORT = int(os.environ.get("PMW_SANDBOX_PORT", "8563"))
USER = os.environ.get("PMW_SANDBOX_USER", "sys")
PW = os.environ.get("PMW_SANDBOX_PASSWORD", "exasol")
SCHEMA = "PM_SBX_TEST"
PID = 1

STEPS = [f"S{i:02d}" for i in range(1, 11)]           # S01..S10
SCORE = {s: i + 1 for i, s in enumerate(STEPS)}       # S01->1 .. S10->10
END = "S10"

# (start, [(step, gap_seconds_from_previous)])
BASE = datetime(2026, 1, 5, 9, 0, 0)
CASES = {
    "P1": (datetime(2026, 1, 5, 9, 0), [("S01", 0), ("S02", 60), ("S03", 180), ("S04", 300), ("S05", 120), ("S06", 180), ("S07", 240), ("S08", 300), ("S09", 3600), ("S10", 120)], ("EU", "Gold", "Web")),
    "P2": (datetime(2026, 1, 5, 10, 0), [("S01", 0), ("S02", 120), ("S03", 240), ("S04", 600), ("S05", 240), ("S06", 180), ("S07", 240), ("S08", 300), ("S09", 3600), ("S10", 120)], ("US", "Silver", "App")),
    "P3": (datetime(2026, 2, 10, 9, 0), [("S01", 0), ("S02", 180), ("S03", 360), ("S04", 900), ("S05", 360), ("S06", 180), ("S07", 240), ("S08", 300), ("S09", 3600), ("S10", 120)], ("EU", "Silver", "Web")),
    "P4": (datetime(2026, 2, 10, 10, 0), [("S01", 0), ("S02", 240), ("S04", 480), ("S05", 480), ("S06", 180), ("S07", 240), ("S08", 300), ("S09", 3600), ("S10", 120)], ("US", "Gold", "App")),
    "P5": (datetime(2026, 3, 1, 9, 0), [("S01", 0), ("S02", 300), ("S03", 420), ("S02", 120), ("S04", 720), ("S05", 600), ("S06", 180), ("S07", 240), ("S08", 300), ("S09", 3600), ("S10", 120)], ("EU", "Gold", "App")),
    "P6": (datetime(2026, 3, 1, 10, 0), [("S01", 0), ("S02", 900), ("S10", 60)], ("US", "Silver", "Web")),
}


def _md5(case: str) -> str:
    return hashlib.md5(case.encode("utf-8")).hexdigest()


def _reachable() -> bool:
    import socket
    try:
        with socket.create_connection((HOST, PORT), timeout=2):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _reachable(), reason=f"no Exasol at {HOST}:{PORT}"),
]


def _server(schema: str = "") -> DatabaseServer:
    return DatabaseServer(host=HOST, port=PORT, username=USER, useTLS=True,
                          certModeRaw="insecure", **{"schema": schema})


@pytest.fixture(scope="module")
def repo():
    # 1. Fresh schema + tables (drop any leftover first).
    import pyexasol
    raw = DatabaseManager.__new__(DatabaseManager)._open(_server(), PW)
    raw.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
    raw.commit()
    raw.close()
    r = asyncio.run(schema_ddl.provision_process_mining_schema(
        host=HOST, port=PORT, username=USER, password=PW, schema=SCHEMA,
        use_tls=True, cert_mode="insecure"))
    assert r["ok"], r

    # 2. Load the fixture (direct INSERTs; the /ingest sink path is a later slice).
    conn = DatabaseManager.__new__(DatabaseManager)._open(_server(SCHEMA), PW)
    conn.execute(f"INSERT INTO PROJECTS (PROJECT_ID, TITLE, TITLE_SHORT) VALUES ({PID}, 'Sandbox', 'SBX')")
    conn.execute(f"INSERT INTO METAS (PROJECT_ID, META_1_TITLE, META_2_TITLE, META_3_TITLE) VALUES ({PID}, 'Region', 'Segment', 'Channel')")
    for s in STEPS:
        conn.execute(
            f"INSERT INTO STEPS (PROJECT_ID, STEP, STEP_ID, SCORE, END_OF_PROCESS) "
            f"VALUES ({PID}, '{s}', {SCORE[s]}, {SCORE[s]}, {'TRUE' if s == END else 'FALSE'})")
    rows = []
    for case, (start, seq, meta) in CASES.items():
        eid = _md5(case)
        t = start
        for step, gap in seq:
            t = t + timedelta(seconds=gap)
            m1, m2, m3 = meta
            rows.append(
                f"({PID}, '{eid}', '{step}', {SCORE[step]}, TIMESTAMP '{t:%Y-%m-%d %H:%M:%S}', "
                f"'{m1}', '{m2}', '{m3}', 'ORIGINAL')")
    conn.execute(
        "INSERT INTO JOURNEYS (PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME, META_1, META_2, META_3, SAMPLE_SET) "
        "VALUES " + ", ".join(rows))
    conn.commit()
    conn.close()

    # 3. A ProcessRepository pointed at the schema.
    mgr = DatabaseManager(load_legacy_active=False)
    server = _server(SCHEMA)
    mgr._conn = mgr._open(server, PW)
    mgr.is_connected = True
    mgr._reopen_server = server
    mgr._active_password = PW
    mgr.use_materialized_transitions = False
    rp = ProcessRepository(mgr)
    rp.active_sample_set = SampleSet.original
    yield rp

    # 4. Teardown.
    try:
        mgr._conn.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'); mgr._conn.commit()
    finally:
        mgr._conn.close()


def _run(coro):
    return asyncio.run(coro)


F0 = FilterSpec(sampleSet=SampleSet.original)


def test_journey_count(repo):
    assert _run(repo.load_journey_count(str(PID), F0)) == 6


def test_variants(repo):
    variants = _run(repo.load_journey_paths(str(PID), F0, 50))
    by_count = sorted(((v.path, v.journeyCount) for v in variants), key=lambda x: -x[1])
    counts = sorted(v.journeyCount for v in variants)
    assert counts == [1, 1, 1, 3]                      # full 3, skip/rework/cancel 1 each
    assert by_count[0][1] == 3                          # dominant = full happy path
    assert sum(v.journeyCount for v in variants) == 6


def test_transition_metrics(repo):
    ts = {(t.fromStep, t.toStep): t for t in _run(repo.load_transitions(str(PID), F0))}
    exp = {  # (occ, avg, median, min, max, sigma-sample)
        ("S01", "S02"): (6, 300, 210, 60, 900, 305.94),
        ("S02", "S03"): (4, 300, 300, 180, 420, 109.54),
        ("S03", "S04"): (3, 600, 600, 300, 900, 300.00),
        ("S03", "S02"): (1, 120, 120, 120, 120, 0.00),
        ("S02", "S04"): (2, 600, 600, 480, 720, 169.71),
        ("S04", "S05"): (5, 360, 360, 120, 600, 189.74),
        ("S05", "S06"): (5, 180, 180, 180, 180, 0.00),
        ("S08", "S09"): (5, 3600, 3600, 3600, 3600, 0.00),
        ("S02", "S10"): (1, 60, 60, 60, 60, 0.00),
    }
    for edge, (occ, avg, med, mn, mx, sd) in exp.items():
        t = ts[edge]
        assert t.occurrences == occ, edge
        assert abs(t.avgSecs - avg) < 1e-6, edge
        assert abs(t.medianSecs - med) < 1e-6, edge
        assert abs(t.minSecs - mn) < 1e-6 and abs(t.maxSecs - mx) < 1e-6, edge
        assert abs((t.stdDevSecs or 0.0) - sd) < 0.01, edge


def test_duration_stats(repo):
    d = _run(repo.load_journey_duration_stats(str(PID), F0))
    assert abs(d.minSecs - 960) < 1e-6 and abs(d.maxSecs - 6600) < 1e-6
    assert abs(d.avgSecs - 5030) < 1e-6
    assert abs(d.medianSecs - 5640) < 1e-6
    assert abs(d.stdDevSecs - 2061.21) < 0.05


def test_process_goodness_raw(repo):
    raw, filtered = _run(repo.load_process_goodness(str(PID), F0))
    assert filtered == 6
    assert abs(raw - (-34.5996)) < 0.01


def test_happy_path_conformance(repo):
    variants = _run(repo.load_journey_paths(str(PID), F0, 50))
    hp = HappyPath(name="full", nodes=[HappyPathNode(step=s) for s in STEPS])
    assert abs(happy_path_conformance(hp, variants) - 0.7963) < 0.001
