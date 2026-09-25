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


# ── Filters (F1–F14): count + variant multiset per surviving set ────────────────

from datetime import datetime as _dt

def _fs(**kw):
    return FilterSpec(sampleSet=SampleSet.original, **kw)

# name -> (FilterSpec, expected journey count, sorted variant-count multiset)
FILTERS = {
    "F1_fromDate":   (_fs(fromDate=_dt(2026, 2, 1)),                 4, [1, 1, 1, 1]),
    "F2_toDate":     (_fs(toDate=_dt(2026, 1, 31)),                  2, [2]),
    "F3_incl_S03":   (_fs(includedSteps=["S03"]),                    4, [1, 3]),
    "F4_excl_S03":   (_fs(excludedSteps=["S03"]),                    2, [1, 1]),
    "F5_incl_S07":   (_fs(includedSteps=["S07"]),                    5, [1, 1, 3]),
    "F6_meta1_EU":   (_fs(meta1="EU"),                               3, [1, 2]),
    "F7_meta3_App":  (_fs(meta3="App"),                              3, [1, 1, 1]),
    "F8_minSteps10": (_fs(minSteps=10),                              4, [1, 3]),
    "F9_maxSteps9":  (_fs(maxSteps=9),                               2, [1, 1]),
    "F10_minTime":   (_fs(minJourneyTime=5000),                      5, [1, 1, 3]),
    "F11_maxTime":   (_fs(maxJourneyTime=5700),                      4, [1, 1, 2]),
    "F12_minScore":  (_fs(minScore=55),                              4, [1, 3]),
    "F13_maxScore":  (_fs(maxScore=52),                              2, [1, 1]),
    "F14_date_meta": (_fs(fromDate=_dt(2026, 2, 1), meta1="EU"),     2, [1, 1]),
}


@pytest.mark.parametrize("name", list(FILTERS))
def test_filter_count_and_variants(repo, name):
    spec, exp_count, exp_variants = FILTERS[name]
    assert _run(repo.load_journey_count(str(PID), spec)) == exp_count, f"{name} count"
    variants = _run(repo.load_journey_paths(str(PID), spec, 50))
    assert sorted(v.journeyCount for v in variants) == exp_variants, f"{name} variants"


def test_filter_worked_duration_stats(repo):
    # F3 (includedSteps=[S03] -> P1,P2,P3,P5): durations {5100,5640,6240,6600}.
    d = _run(repo.load_journey_duration_stats(str(PID), _fs(includedSteps=["S03"])))
    assert abs(d.minSecs - 5100) < 1e-6 and abs(d.maxSecs - 6600) < 1e-6
    assert abs(d.avgSecs - 5895) < 1e-6 and abs(d.medianSecs - 5940) < 1e-6
    assert abs(d.stdDevSecs - 661.59) < 0.05
    # F1 (date window -> P3,P4,P5,P6, whole journeys): durations {6240,5640,6600,960}.
    d2 = _run(repo.load_journey_duration_stats(str(PID), _fs(fromDate=_dt(2026, 2, 1))))
    assert abs(d2.minSecs - 960) < 1e-6 and abs(d2.maxSecs - 6600) < 1e-6
    assert abs(d2.avgSecs - 4860) < 1e-6 and abs(d2.medianSecs - 5940) < 1e-6


# ── MCP-surface equivalence (REST == MCP through the tool handlers) ─────────────

import importlib.util as _ilu
from pathlib import Path as _Path
from types import SimpleNamespace as _NS

_USER = _NS(username="tester", is_enabled=True, is_power=True, is_admin=True)


@pytest.fixture(scope="module")
def mcpmod(repo):
    spec = _ilu.spec_from_file_location(
        "mcp_server_it", _Path(__file__).resolve().parents[3] / "mcp" / "server.py")
    m = _ilu.module_from_spec(spec); spec.loader.exec_module(m)

    class _Ctx:
        def __init__(self, username, connection_id, sample):
            self._sample = sample
        async def __aenter__(self):
            repo.active_sample_set = self._sample
            return repo
        async def __aexit__(self, *exc):
            return None
    m._Repo = _Ctx
    return m


_ARGS = {"connectionId": "sbx", "projectId": PID}


def test_mcp_transitions_equal_rest(repo, mcpmod):
    mcp_rows = _run(mcpmod._tool_get_transition_metrics(_USER, dict(_ARGS)))
    rest = {(t.fromStep, t.toStep): t for t in _run(repo.load_transitions(str(PID), F0))}
    assert len(mcp_rows) == len(rest)
    for row in mcp_rows:
        t = rest[(row["fromStep"], row["toStep"])]
        assert row["occurrences"] == t.occurrences
        assert abs(row["avgSecs"] - t.avgSecs) < 1e-6
        assert abs((row["medianSecs"] or 0) - (t.medianSecs or 0)) < 1e-6
        assert abs((row["stdDevSecs"] or 0) - (t.stdDevSecs or 0)) < 1e-6


def test_mcp_statistics_equal_rest_raw_goodness(repo, mcpmod):
    stats = _run(mcpmod._tool_get_statistics(_USER, dict(_ARGS)))
    assert stats["journeyCount"] == _run(repo.load_journey_count(str(PID), F0))
    raw, _ = _run(repo.load_process_goodness(str(PID), F0))
    # MCP get_statistics returns the RAW goodness (no coverage penalty) — §11 finding.
    assert abs(stats["processGoodness"] - raw) < 1e-6
    d = _run(repo.load_journey_duration_stats(str(PID), F0))
    assert abs(stats["durations"]["medianSecs"] - d.medianSecs) < 1e-6


def test_mcp_variants_equal_rest_under_filter(repo, mcpmod):
    args = {**_ARGS, "includedSteps": ["S03"]}
    mcp_v = _run(mcpmod._tool_get_variants(_USER, args))
    rest_v = _run(repo.load_journey_paths(str(PID), _fs(includedSteps=["S03"]), 100))
    assert sorted(v["journeyCount"] for v in mcp_v) == sorted(v.journeyCount for v in rest_v)
    assert sum(v["journeyCount"] for v in mcp_v) == 4


# ── Deeper-analysis power tools (MCP-only; exact values from §5) ─────────────────

def test_mcp_bottlenecks(repo, mcpmod):
    out = _run(mcpmod._tool_get_bottlenecks(_USER, dict(_ARGS)))
    assert abs(out["totalWaitSecs"] - 30180) < 1e-6                 # Σ = Σ journey durations
    wait = {(r["fromStep"], r["toStep"]): r["totalWaitSecs"] for r in out["byTotalWaitTime"]}
    assert wait[("S08", "S09")] == 18000                            # invoice→payment dominates
    assert out["byTotalWaitTime"][0]["fromStep"] == "S08"          # ranked #1
    for edge, w in {("S01", "S02"): 1800, ("S03", "S04"): 1800, ("S04", "S05"): 1800,
                    ("S07", "S08"): 1500, ("S05", "S06"): 900}.items():
        assert wait[edge] == w, edge
    rework = {r["step"]: (r["journeys"], r["extraVisits"]) for r in out["rework"]}
    assert rework == {"S02": (1, 1)}                                # S02 repeats once, in P5
    assert out["selfLoops"] == []


def test_mcp_trend_by_month(repo, mcpmod):
    out = _run(mcpmod._tool_get_trend(_USER, {**_ARGS, "granularity": "month"}))
    by = {p["period"]: p for p in out["periods"]}
    exp = {"2026-01-01": (2, 5370, 5370), "2026-02-01": (2, 5940, 5940),
           "2026-03-01": (2, 3780, 3780)}
    assert set(by) == set(exp)
    for period, (n, avg, med) in exp.items():
        p = by[period]
        assert p["journeys"] == n
        assert abs(p["avgDurationSecs"] - avg) < 1e-6
        assert abs(p["medianDurationSecs"] - med) < 1e-6


def test_mcp_outcome_drivers_reach_ship(repo, mcpmod):
    # minSupport=1: the default (30) would filter out every factor on a 6-journey fixture.
    out = _run(mcpmod._tool_get_outcome_drivers(
        _USER, {**_ARGS, "outcomeSteps": ["S07"], "minSupport": 1}))
    assert out["journeys"] == 6 and out["outcomeJourneys"] == 5
    assert abs(out["outcomeRate"] - 0.8333) < 1e-4
    ups = {a["value"]: a for a in out["raisesOutcome"]["attributes"]}
    downs = {a["value"]: a for a in out["lowersOutcome"]["attributes"]}
    assert abs(ups["EU"]["outcomeRate"] - 1.0) < 1e-6 and abs(ups["EU"]["lift"] - 1.2) < 1e-3
    assert abs(downs["US"]["outcomeRate"] - 0.6667) < 1e-4 and abs(downs["US"]["lift"] - 0.8) < 1e-3


def test_mcp_check_conformance(repo, mcpmod):
    rules = [
        {"type": "forbidden", "step": "S03"},
        {"type": "requires", "step": "S04"},
        {"type": "precedes", "before": "S03", "after": "S04"},
        {"type": "max_duration", "maxSecs": 6000},
        {"type": "max_gap", "fromStep": "S08", "toStep": "S09", "maxSecs": 3000},
    ]
    out = _run(mcpmod._tool_check_conformance(_USER, {**_ARGS, "rules": rules}))
    assert out["journeysChecked"] == 6
    got = [r["violations"] for r in out["rules"]]
    assert got == [4, 1, 1, 2, 5]


def test_mcp_compare_segments_eu_vs_us(repo, mcpmod):
    out = _run(mcpmod._tool_compare_segments(_USER, {
        **_ARGS, "segmentA": {"meta1": "EU", "label": "EU"},
        "segmentB": {"meta1": "US", "label": "US"}}))
    eu, us = out["segments"]
    assert eu["label"] == "EU" and eu["journeyCount"] == 3
    assert abs(eu["durations"]["avgSecs"] - 5980) < 1e-6
    assert abs(eu["durations"]["medianSecs"] - 6240) < 1e-6
    assert us["label"] == "US" and us["journeyCount"] == 3
    assert abs(us["durations"]["avgSecs"] - 4080) < 1e-6
    assert abs(us["durations"]["medianSecs"] - 5640) < 1e-6


def test_power_tools_require_the_power_role(repo, mcpmod):
    plain = _NS(username="plain", is_enabled=True, is_power=False, is_admin=False)
    for tool in ("_tool_get_bottlenecks", "_tool_get_trend", "_tool_compare_segments"):
        with pytest.raises(mcpmod.ToolError):
            _run(getattr(mcpmod, tool)(plain, dict(_ARGS)))


# ── "Everyone" tools + node occurrences ─────────────────────────────────────────

def test_node_occurrences(repo):
    res = _run(repo.db.execute(
        "SELECT STEP, COUNT(*) FROM JOURNEYS WHERE PROJECT_ID = 1 "
        "AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL) GROUP BY STEP"))
    got = {r[0]: int(r[1]) for r in res.rows}
    assert got == {"S01": 6, "S02": 7, "S03": 4, "S04": 5, "S05": 5,
                   "S06": 5, "S07": 5, "S08": 5, "S09": 5, "S10": 6}


def test_mcp_metadata(repo, mcpmod):
    md = _run(mcpmod._tool_get_metadata(_USER, dict(_ARGS)))
    assert md["metaTitles"] == {"meta1": "Region", "meta2": "Segment", "meta3": "Channel"}
    assert set(md["steps"]) == {f"S{i:02d}" for i in range(1, 11)}
    assert md["dateRange"]["from"].startswith("2026-01-05T09:00:00")
    assert md["dateRange"]["to"].startswith("2026-03-01T10:50:00")   # P5 closes last


def test_mcp_attribute_values(repo, mcpmod):
    out = _run(mcpmod._tool_get_attribute_values(_USER, {**_ARGS, "meta": "all"}))
    by_meta = {a["meta"]: {v["value"]: v["journeys"] for v in a["values"]} for a in out["attributes"]}
    assert by_meta["meta1"] == {"EU": 3, "US": 3}
    assert by_meta["meta2"] == {"Gold": 3, "Silver": 3}
    assert by_meta["meta3"] == {"Web": 3, "App": 3}


def test_mcp_process_map(repo, mcpmod):
    g = _run(mcpmod._tool_get_process_map(_USER, dict(_ARGS)))
    assert set(g["steps"]) == {f"S{i:02d}" for i in range(1, 11)}
    edges = {(t["fromStep"], t["toStep"]): t for t in g["transitions"]}
    assert len(edges) == 12
    assert edges[("S08", "S09")]["occurrences"] == 5
    assert abs(edges[("S08", "S09")]["avgSecs"] - 3600) < 1e-6
    assert edges[("S01", "S02")]["occurrences"] == 6


def test_mcp_get_journey(repo, mcpmod):
    j = _run(mcpmod._tool_get_journey(_USER, {**_ARGS, "eventId": "P5"}))
    assert j["stepCount"] == 11
    assert abs(j["durationSecs"] - 6600) < 1e-6
    assert j["meta"] == {"Region": "EU", "Segment": "Gold", "Channel": "App"}
    steps = [e["step"] for e in j["events"]]
    assert steps == ["S01", "S02", "S03", "S02", "S04", "S05", "S06", "S07", "S08", "S09", "S10"]


def test_mcp_find_journey(repo, mcpmod, monkeypatch):
    monkeypatch.setattr(mcpmod.store, "connections_for_user",
                        lambda u: [_NS(id="sbx", name="Sandbox")])
    out = _run(mcpmod._tool_find_journey(_USER, {"eventId": "P5"}))
    assert len(out["matches"]) == 1
    m = out["matches"][0]
    assert m["projectId"] == 1 and m["stepCount"] == 11
    assert abs(m["durationSecs"] - 6600) < 1e-6
    # An id that exists nowhere → no matches.
    none = _run(mcpmod._tool_find_journey(_USER, {"eventId": "NOPE-999"}))
    assert none["matches"] == []
