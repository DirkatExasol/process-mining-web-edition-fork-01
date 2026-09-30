"""Second correctness harness — cycles & loops, against a live Exasol.

Where ``test_sandbox_correctness.py`` proves the metrics on a mostly-linear 10-step
order-to-cash log, this fixture stresses the engine's handling of **repetition**: a
30-step incident-resolution process whose journeys revisit steps through

* **self-loops** — a step immediately repeating (``C15 Monitor`` polled 13× in one
  journey, ``C18 Await Customer``),
* **2-cycles / rework loops** — review reject ``C07→C06``, smoke-test reject ``C11→C10``,
* **back-jumps** — a failed test throwing work back several steps ``C09→C06``,
* an **escalation cycle** ``C04→C17→C04`` and a **big reopen cycle**
  ``C16→C19→C02→…`` that re-enters the whole spine.

13 journeys span **295 events**; the longest visits **50 steps** (``J10``, a
"chronic flapping" incident). Every number the Suite returns is checked against an
**independent Python oracle** (``statistics`` module + plain counting, recomputed here
from the fixture — a different code path from the app's SQL), and the headline
cycle/loop facts are additionally pinned as explicit literals so a reader can follow
them in ``docs/CORRECTNESS-CYCLES-PLAN.md``.

Opt-in: skipped unless an Exasol is reachable at PMW_SANDBOX_* (default 127.0.0.1:8563,
sys/exasol). It NEVER touches existing data — it creates and drops its own schema.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import statistics
from collections import Counter
from datetime import datetime, timedelta

import pytest

from app.db import schema_ddl
from app.db.analysis import Analysis
from app.db.manager import DatabaseManager
from app.db.repository import ProcessRepository
from app.models import DatabaseServer, FilterSpec, SampleSet

HOST = os.environ.get("PMW_SANDBOX_HOST", "127.0.0.1")
PORT = int(os.environ.get("PMW_SANDBOX_PORT", "8563"))
USER = os.environ.get("PMW_SANDBOX_USER", "sys")
PW = os.environ.get("PMW_SANDBOX_PASSWORD", "exasol")
SCHEMA = "PM_SBX_CYCLES"
PID = 1

# ── 30-step incident-resolution catalog (SCORE = index; C30 is end-of-process) ──
STEPS = [f"C{i:02d}" for i in range(1, 31)]
SCORE = {s: i + 1 for i, s in enumerate(STEPS)}
END = "C30"

# Each step has a fixed processing time (seconds); a transition's duration equals the
# TARGET step's processing time. Deterministic and hand-verifiable (see the plan doc).
BASE_GAP = {
    "C01": 0, "C02": 300, "C03": 600, "C04": 900, "C05": 600, "C06": 1800,
    "C07": 1200, "C08": 600, "C09": 1800, "C10": 900, "C11": 600, "C12": 3600,
    "C13": 1800, "C14": 900, "C15": 300, "C16": 600, "C17": 1200, "C18": 3600,
    "C19": 600, "C20": 7200, "C21": 900, "C22": 1800, "C23": 3600, "C24": 1200,
    "C25": 600, "C26": 900, "C27": 600, "C28": 1800, "C29": 300, "C30": 120,
}


def _j10() -> list[str]:
    """The 50-event "chronic flapping" incident: 2 review rejects, 2 test failures,
    2 smoke failures, then a 13-poll monitor self-loop."""
    seq = ["C01", "C02", "C03", "C04", "C05", "C06"]
    seq += ["C07"] + ["C06", "C07"] * 2            # 2 review rejects
    seq += ["C08", "C09"]
    seq += ["C06", "C07", "C08", "C09"] * 2         # 2 test failures (back-jump to C06)
    seq += ["C10", "C11"]
    seq += ["C10", "C11"] * 2                        # 2 smoke failures (C11->C10)
    seq += ["C12", "C13", "C14"]
    seq += ["C15"] * 13                              # long monitor self-loop
    seq += ["C16", "C24", "C25", "C26", "C27", "C29", "C30"]
    return seq


# jid -> (path, (Priority, Team, Source)); one journey per calendar day from START.
START = datetime(2026, 1, 5, 8, 0, 0)
PATHS: dict[str, tuple[list[str], tuple[str, str, str]]] = {
    "J01": (["C01","C02","C03","C04","C05","C06","C07","C08","C09","C10","C11","C12","C13","C14","C15","C16","C24","C25","C26","C27","C28","C29","C30"], ("P2","Core","Portal")),
    "J02": (["C01","C02","C03","C04","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P3","Core","Email")),
    "J03": (["C01","C02","C03","C04","C05","C06","C07","C06","C07","C08","C09","C10","C11","C12","C13","C14","C15","C16","C24","C25","C29","C30"], ("P2","Payments","Portal")),
    "J04": (["C01","C02","C03","C04","C06","C07","C08","C09","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P1","Payments","Phone")),
    "J05": (["C01","C02","C03","C04","C06","C07","C08","C09","C10","C11","C10","C11","C12","C13","C14","C15","C16","C24","C25","C29","C30"], ("P2","Core","Email")),
    "J06": (["C01","C02","C03","C04","C17","C04","C05","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P1","Platform","Phone")),
    "J07": (["C01","C02","C03","C04","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C19","C02","C03","C04","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P2","Platform","Portal")),
    "J08": (["C01","C02","C03","C04","C18","C18","C18","C05","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P3","Core","Email")),
    "J09": (["C01","C02","C03","C04","C06","C07","C08","C09","C10","C11","C13","C14","C15","C21","C22","C14","C15","C16","C23","C24","C25","C29","C30"], ("P1","Platform","Phone")),
    "J10": (_j10(), ("P1","Payments","Portal")),
    "J11": (["C01","C02","C20","C02","C03","C04","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P3","Core","Portal")),
    "J12": (["C01","C02","C30"], ("P3","Core","Email")),
    # J13 duplicates J02's exact path — a second golden short-closure incident, so that
    # variant carries count 2 (exercises grouping across journeys).
    "J13": (["C01","C02","C03","C04","C06","C07","C08","C09","C10","C11","C13","C14","C15","C16","C24","C25","C29","C30"], ("P2","Payments","Email")),
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


def _build():
    """Expand PATHS into absolute-timed journeys: jid -> [(step, abs_time, gap)]."""
    journeys: dict[str, list[tuple[str, datetime, int]]] = {}
    day = START
    for jid, (path, _meta) in PATHS.items():
        t = day
        evs = []
        for i, step in enumerate(path):
            gap = 0 if i == 0 else BASE_GAP[step]
            t = t + timedelta(seconds=gap)
            evs.append((step, t, gap))
        journeys[jid] = evs
        day = day + timedelta(days=1)
    return journeys


# ── Independent Python oracle (statistics + counting; NOT the app's SQL) ─────────
class Oracle:
    def __init__(self, journeys):
        self.j = journeys
        self.meta = {jid: PATHS[jid][1] for jid in journeys}

    @property
    def journey_count(self):
        return len(self.j)

    @property
    def total_events(self):
        return sum(len(e) for e in self.j.values())

    @property
    def node_occ(self):
        return dict(Counter(s for evs in self.j.values() for s, _, _ in evs))

    @property
    def lengths(self):
        return {jid: len(evs) for jid, evs in self.j.items()}

    @property
    def transitions(self):
        edges: dict[tuple[str, str], list[int]] = {}
        for evs in self.j.values():
            for i in range(1, len(evs)):
                edges.setdefault((evs[i - 1][0], evs[i][0]), []).append(evs[i][2])
        out = {}
        for e, gaps in edges.items():
            out[e] = dict(occ=len(gaps), avg=statistics.mean(gaps),
                          median=statistics.median(gaps), mn=min(gaps), mx=max(gaps),
                          sd=(statistics.stdev(gaps) if len(gaps) > 1 else 0.0))
        return out

    @property
    def durations(self):
        return [(evs[-1][1] - evs[0][1]).total_seconds() for evs in self.j.values()]

    @property
    def dur_stats(self):
        d = self.durations
        return dict(avg=statistics.mean(d), median=statistics.median(d),
                    mn=min(d), mx=max(d), sd=statistics.stdev(d))

    @property
    def variants(self):
        return Counter(tuple(s for s, _, _ in evs) for evs in self.j.values())

    @property
    def self_loops(self):
        return {a: v["occ"] for (a, b), v in self.transitions.items() if a == b}

    @property
    def rework(self):
        rj, rx = Counter(), Counter()
        for evs in self.j.values():
            for s, n in Counter(s for s, _, _ in evs).items():
                if n > 1:
                    rj[s] += 1
                    rx[s] += n - 1
        return {s: (rj[s], rx[s]) for s in rj}

    @property
    def date_range(self):
        firsts = [evs[0][1] for evs in self.j.values()]
        lasts = [evs[-1][1] for evs in self.j.values()]
        return min(firsts), max(lasts)


@pytest.fixture(scope="module")
def journeys():
    return _build()


@pytest.fixture(scope="module")
def oracle(journeys):
    return Oracle(journeys)


@pytest.fixture(scope="module")
def repo(journeys):
    # 1. Fresh schema + tables.
    raw = DatabaseManager.__new__(DatabaseManager)._open(_server(), PW)
    raw.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'); raw.commit(); raw.close()
    r = asyncio.run(schema_ddl.provision_process_mining_schema(
        host=HOST, port=PORT, username=USER, password=PW, schema=SCHEMA,
        use_tls=True, cert_mode="insecure"))
    assert r["ok"], r

    # 2. Load the fixture (direct INSERTs; the sink path is covered by test #1).
    conn = DatabaseManager.__new__(DatabaseManager)._open(_server(SCHEMA), PW)
    conn.execute(f"INSERT INTO PROJECTS (PROJECT_ID, TITLE, TITLE_SHORT) VALUES ({PID}, 'SandboxCycles', 'SBXC')")
    conn.execute(f"INSERT INTO METAS (PROJECT_ID, META_1_TITLE, META_2_TITLE, META_3_TITLE) VALUES ({PID}, 'Priority', 'Team', 'Source')")
    for s in STEPS:
        conn.execute(
            f"INSERT INTO STEPS (PROJECT_ID, STEP, STEP_ID, SCORE, END_OF_PROCESS) "
            f"VALUES ({PID}, '{s}', {SCORE[s]}, {SCORE[s]}, {'TRUE' if s == END else 'FALSE'})")
    rows = []
    for jid, evs in journeys.items():
        eid = _md5(jid)
        m1, m2, m3 = PATHS[jid][1]
        for step, t, _gap in evs:
            rows.append(
                f"({PID}, '{eid}', '{step}', {SCORE[step]}, TIMESTAMP '{t:%Y-%m-%d %H:%M:%S}', "
                f"'{m1}', '{m2}', '{m3}', 'ORIGINAL')")
    for i in range(0, len(rows), 200):
        conn.execute(
            "INSERT INTO JOURNEYS (PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME, META_1, META_2, META_3, SAMPLE_SET) "
            "VALUES " + ", ".join(rows[i:i + 200]))
    conn.commit(); conn.close()

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


# ── Shape of the fixture — explicit headline literals (see the plan doc) ─────────

def test_fixture_shape(repo, oracle):
    assert oracle.journey_count == 13
    assert oracle.total_events == 295
    assert len(oracle.node_occ) == 30                       # all 30 distinct steps present
    assert max(oracle.lengths.values()) == 50               # J10 visits 50 steps
    assert oracle.lengths["J10"] == 50
    assert min(oracle.lengths.values()) == 3                # J12 (cancel)
    # The Suite agrees on the journey count and the step catalog.
    assert _run(repo.load_journey_count(str(PID), F0)) == 13


def test_node_occurrences_match_oracle(repo, oracle):
    res = _run(repo.db.execute(
        "SELECT STEP, COUNT(*) FROM JOURNEYS WHERE PROJECT_ID = 1 "
        "AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL) GROUP BY STEP"))
    got = {r[0]: int(r[1]) for r in res.rows}
    assert got == oracle.node_occ
    # A few pinned literals a reader can verify against the journey table:
    assert got["C15"] == 26      # Monitor — inflated by the 13-poll self-loop in J10
    assert got["C06"] == 19 and got["C07"] == 19            # Develop/Review — loop-inflated
    assert got["C17"] == 1 and got["C19"] == 1              # escalate / reopen — once each


# ── Every transition (occ + timing) matches the independent oracle ──────────────

def test_transitions_match_oracle(repo, oracle):
    ts = {(t.fromStep, t.toStep): t for t in _run(repo.load_transitions(str(PID), F0))}
    exp = oracle.transitions
    assert set(ts) == set(exp), (set(ts) ^ set(exp))
    for e, x in exp.items():
        t = ts[e]
        assert t.occurrences == x["occ"], e
        assert abs((t.avgSecs or 0) - x["avg"]) < 1e-6, e
        assert abs((t.medianSecs or 0) - x["median"]) < 1e-6, e
        assert abs((t.minSecs or 0) - x["mn"]) < 1e-6 and abs((t.maxSecs or 0) - x["mx"]) < 1e-6, e
        assert abs((t.stdDevSecs or 0) - x["sd"]) < 0.01, e


def test_loop_edges_pinned(repo, oracle):
    """The cycle back-edges — pinned literals a reader can trace in the journey table."""
    ts = {(t.fromStep, t.toStep): t for t in _run(repo.load_transitions(str(PID), F0))}
    # (occurrences) of each loop / back edge.
    assert ts[("C07", "C06")].occurrences == 3              # review rejects (J03,J10×2)
    assert ts[("C09", "C06")].occurrences == 3              # test-fail back-jumps (J04,J10×2)
    assert ts[("C11", "C10")].occurrences == 3              # smoke rejects (J05,J10×2)
    assert ts[("C17", "C04")].occurrences == 1              # escalation cycle (J06)
    assert ts[("C19", "C02")].occurrences == 1              # reopen cycle (J07)
    assert ts[("C16", "C19")].occurrences == 1              # verify -> reopen (J07)
    # The forward loop edge C06->C07 recurs 19× (every Code Review follows a Develop
    # Fix) — every occurrence is 1200 s, so the aggregate is exact even under heavy
    # repetition.
    assert ts[("C06", "C07")].occurrences == 19
    assert abs(ts[("C06", "C07")].avgSecs - 1200) < 1e-6
    assert abs(ts[("C06", "C07")].stdDevSecs or 0) < 1e-9


def test_self_loops(repo, oracle):
    ts = {(t.fromStep, t.toStep): t for t in _run(repo.load_transitions(str(PID), F0))}
    self_edges = {a: t.occurrences for (a, b), t in ts.items() if a == b}
    assert self_edges == oracle.self_loops
    assert self_edges == {"C15": 12, "C18": 2}              # Monitor 12 (J10), Await 2 (J08)
    # a self-loop's duration is the step's fixed poll interval
    assert abs(ts[("C15", "C15")].avgSecs - 300) < 1e-6
    assert abs(ts[("C15", "C15")].stdDevSecs or 0) < 1e-9


def test_duration_stats_match_oracle(repo, oracle):
    d = _run(repo.load_journey_duration_stats(str(PID), F0))
    x = oracle.dur_stats
    assert abs(d.avgSecs - x["avg"]) < 1e-6
    assert abs(d.medianSecs - x["median"]) < 1e-6
    assert abs(d.minSecs - x["mn"]) < 1e-6 and abs(d.maxSecs - x["mx"]) < 1e-6
    assert abs(d.stdDevSecs - x["sd"]) < 0.05
    # pinned: shortest = cancel (C01->C02->C30 = 300+120), longest = the flapping J10
    assert abs(d.minSecs - 420) < 1e-6
    assert abs(d.maxSecs - 43620) < 1e-6


def test_variants_match_oracle(repo, oracle):
    vs = _run(repo.load_journey_paths(str(PID), F0, 100))
    assert sorted(v.journeyCount for v in vs) == sorted(oracle.variants.values())
    assert len(vs) == 12                                    # 13 journeys, 12 distinct paths
    assert sorted(v.journeyCount for v in vs) == [1] * 11 + [2]   # J02==J13 share a path
    assert sum(v.journeyCount for v in vs) == 13


# ── MCP power tools: rework, self-loops, and REST↔MCP equivalence ───────────────

import importlib.util as _ilu
from pathlib import Path as _Path
from types import SimpleNamespace as _NS

_USER = _NS(username="tester", is_enabled=True, is_power=True, is_admin=True)
_ARGS = {"connectionId": "sbx", "projectId": PID}


@pytest.fixture(scope="module")
def mcpmod(repo):
    spec = _ilu.spec_from_file_location(
        "mcp_server_cycles", _Path(__file__).resolve().parents[3] / "mcp" / "server.py")
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


def test_mcp_rework_matches_oracle(repo, oracle, mcpmod):
    out = _run(mcpmod._tool_get_bottlenecks(_USER, {**_ARGS, "limit": 100}))
    rework = {r["step"]: (r["journeys"], r["extraVisits"]) for r in out["rework"]}
    assert rework == oracle.rework
    # pinned headline: Monitor repeats most (14 extra visits across 3 journeys); the
    # develop/review pair each add 7 extra visits across 4 journeys.
    assert rework["C15"] == (3, 14)
    assert rework["C06"] == (4, 7) and rework["C07"] == (4, 7)
    # self-loops reported by the same tool
    loops = {r["fromStep"]: r["occurrences"] for r in out["selfLoops"]}
    assert loops == {"C15": 12, "C18": 2}


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


def test_mcp_metadata_and_process_map(repo, oracle, mcpmod):
    md = _run(mcpmod._tool_get_metadata(_USER, dict(_ARGS)))
    assert md["metaTitles"] == {"meta1": "Priority", "meta2": "Team", "meta3": "Source"}
    assert set(md["steps"]) == set(STEPS)                   # all 30
    lo, hi = oracle.date_range
    assert md["dateRange"]["from"].startswith(lo.strftime("%Y-%m-%dT%H:%M:%S"))
    assert md["dateRange"]["to"].startswith(hi.strftime("%Y-%m-%dT%H:%M:%S"))

    g = _run(mcpmod._tool_get_process_map(_USER, dict(_ARGS)))
    assert set(g["steps"]) == set(STEPS)
    edges = {(t["fromStep"], t["toStep"]): t for t in g["transitions"]}
    assert len(edges) == len(oracle.transitions)
    # the process map surfaces the loop back-edges and self-loops
    assert ("C15", "C15") in edges and edges[("C15", "C15")]["occurrences"] == 12
    assert ("C07", "C06") in edges and ("C19", "C02") in edges


def test_mcp_get_journey_reconstructs_the_50_step_loop(repo, mcpmod):
    j = _run(mcpmod._tool_get_journey(_USER, {**_ARGS, "eventId": "J10"}))
    assert j["stepCount"] == 50
    steps = [e["step"] for e in j["events"]]
    assert steps == PATHS["J10"][0]                         # exact order incl. every loop
    assert steps.count("C15") == 13                         # the monitor self-loop run
    assert abs(j["durationSecs"] - 43620) < 1e-6


def test_power_tools_require_the_power_role(repo, mcpmod):
    plain = _NS(username="plain", is_enabled=True, is_power=False, is_admin=False)
    with pytest.raises(mcpmod.ToolError):
        _run(mcpmod._tool_get_bottlenecks(plain, dict(_ARGS)))


# ── Simulation over a cyclic graph — must terminate and stay well-formed ─────────

import random as _rnd
from collections import defaultdict as _dd
from app.services import simulation as _sim
from app.models import SimulationConfig


def test_simulation_terminates_on_cyclic_graph(repo):
    """A graph full of loops must not diverge: every seeded walk starts at C01 and
    either reaches the terminal C30 or is cut at the max-steps cap — never runs away."""
    graph = _run(repo.load_graph("1", F0))
    # Premise: the observed graph really is cyclic — it carries self-loops and back-edges.
    edges = {(t.fromStep, t.toStep) for t in graph.transitions}
    assert ("C15", "C15") in edges                           # a self-loop
    assert ("C07", "C06") in edges and ("C19", "C02") in edges  # back-edges

    _rnd.seed(20260928)
    cfg = SimulationConfig(journeyCount=300, maxStepsPerJourney=80)
    res = _sim.simulate(graph, graph.steps, cfg)

    assert res.totalJourneys == 300 and len(res.cycleTimes) == 300
    reachable = {t.toStep for t in graph.transitions} | {t.fromStep for t in graph.transitions}
    seq = _dd(list)
    for e in res.events:
        seq[e.journeyId].append((e.timestamp, e.step))
    for evs in seq.values():
        evs.sort()
        assert evs[0][1] == "C01"                            # always starts at Open
        # ends at the terminal C30, or was cut at the max-steps cap — never runs away
        assert evs[-1][1] == "C30" or len(evs) == cfg.maxStepsPerJourney + 1
        assert all(step in reachable for _, step in evs)      # only observed steps
    assert res.minCycleTimeSecs > 0
    assert res.minCycleTimeSecs <= res.avgCycleTimeSecs <= res.maxCycleTimeSecs
    assert res.stdDevCycleTimeSecs >= 0
