"""MCP lookup tools (get_attribute_values, find_journey, stepDetails in get_metadata) and
the power-user analysis tools (compare_segments, get_bottlenecks, get_trend,
get_outcome_drivers, check_conformance): role gating, argument validation, result
shaping, and the safety of the SQL the analysis layer generates."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db.analysis import Analysis, Rule
from app.db.repository import ProcessRepository
from app.models import DurationStats, FilterSpec, ProcessTransition, StepInfo

_PATH = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_analysis", _PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

PLAIN = SimpleNamespace(username="carol", is_enabled=True, is_power=False, is_admin=False)
POWER = SimpleNamespace(username="dirk", is_enabled=True, is_power=True, is_admin=False)
ADMIN = SimpleNamespace(username="root", is_enabled=True, is_power=False, is_admin=True)
BASE = {"connectionId": "c1", "projectId": 1}
POWER_TOOLS = {
    "compare_segments": {"segmentA": {"meta1": "Bank"}, "segmentB": {"meta1": "PayPal"}},
    "get_bottlenecks": {},
    "get_trend": {},
    "get_outcome_drivers": {"outcomeSteps": ["Rejected"]},
    "check_conformance": {"rules": [{"type": "forbidden", "step": "Rejected"}]},
}


def _run(coro):
    return asyncio.run(coro)


def _call(name, arguments, user=POWER):
    out = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments}}, user))
    result = out["result"]
    text = result["content"][0]["text"]
    return result, (text if result["isError"] else json.loads(text))


def _t(a, b, occ, avg, median=None):
    return ProcessTransition(fromStep=a, toStep=b, occurrences=occ, avgSecs=avg,
                             medianSecs=avg if median is None else median)


class _FakeAnalysis:
    """Stands in for app.db.analysis.Analysis at the MCP layer."""

    def __init__(self, repo):
        self.repo = repo

    async def attribute_values(self, pid, meta, spec, limit):
        return {"meta1": (3, [("Credit Card", 900), ("PayPal", 700)])}.get(meta, (0, []))

    async def journey_lookup(self, pid, stored):
        return self.repo.journeys.get((str(pid), stored))

    async def end_steps(self, pid, spec, limit=25):
        return [("Delivered", 80), ("Payment Failed", 20)] if spec.meta1 == "Bank" else [("Delivered", 95), ("Payment Failed", 5)]

    async def rework(self, pid, spec, limit):
        return [{"step": "Payment Retry", "journeys": 40, "extraVisits": 55}]

    async def trend(self, pid, spec, unit, outcome, limit):
        return [{"period": "2024-01-01", "journeys": 10, "avgDurationSecs": 5.0,
                 "medianDurationSecs": 4.0, **({"outcomeJourneys": 2, "outcomeRate": 0.2} if outcome else {})}]

    async def outcome_drivers(self, pid, spec, outcome, min_support):
        return {"total": 1000, "hits": 100,
                "meta": [("meta2", "Low", 200, 60), ("meta2", "High", 300, 9)],
                "steps": [("Agent Review", 400, 80), ("Bank", 500, 20)]}

    async def conformance(self, pid, spec, rules, examples):
        return 500, [(25, ["abc"] * min(examples, 2)) for _ in rules]


class _Repo:
    def __init__(self):
        self.journeys = {}

    async def load_projects(self):
        return [{"projectId": 1, "title": "Online Bookstore"}, {"projectId": 5, "title": "Flights"}]

    async def load_meta_titles(self, pid):
        return ("Payment Method", "Customer Segment", "Order Value")

    async def load_all_step_names(self, pid):
        return ["Checkout", "Delivered", "Payment Failed"]

    async def load_steps(self, pid):
        return {"Checkout": StepInfo(step="Checkout", description="Customer checks out", score=2,
                                     belongsTo="Order"),
                "Delivered": StepInfo(step="Delivered", description="Parcel delivered", score=15,
                                      endOfProcess=True, belongsTo="Fulfilment")}

    async def load_date_bounds(self, pid):
        return (datetime(2024, 1, 1), datetime(2024, 12, 31))

    async def load_journey_count(self, pid, spec):
        return 100

    async def load_journey_duration_stats(self, pid, spec):
        return DurationStats(avgSecs=60.0)

    async def load_process_goodness(self, pid, spec):
        return (1.5, 100)

    async def load_transitions(self, pid, spec):
        slow = 400.0 if spec.meta1 == "Bank" else 100.0
        return [_t("Checkout", "Payment", 100, 30.0), _t("Payment", "Delivered", 100, slow),
                _t("Payment Retry", "Payment Retry", 45, 20.0), _t("Rare", "Thing", 2, 9999.0)]


def _patch(monkeypatch, repos):
    class _Ctx:
        def __init__(self, username, connection_id, sample):
            self.cid = connection_id

        async def __aenter__(self):
            found = repos[self.cid]
            if isinstance(found, Exception):
                raise found
            return found

        async def __aexit__(self, *exc):
            return None

    monkeypatch.setattr(mcp, "_Repo", _Ctx)
    monkeypatch.setattr(mcp, "Analysis", _FakeAnalysis)


# ── role gating ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("tool", sorted(POWER_TOOLS))
def test_power_tools_politely_refuse_an_ordinary_user_without_touching_the_db(monkeypatch, tool):
    class _Explode:
        def __init__(self, *a):
            raise AssertionError("no database access for a refused call")

    monkeypatch.setattr(mcp, "_Repo", _Explode)
    result, message = _call(tool, {**BASE, **POWER_TOOLS[tool]}, user=PLAIN)
    assert result["isError"] is True
    assert message.startswith("Sorry") and "power users" in message and tool in message
    assert "carol" in message and "administrator" in message


@pytest.mark.parametrize("user", [POWER, ADMIN])
@pytest.mark.parametrize("tool", sorted(POWER_TOOLS))
def test_power_tools_run_for_power_users_and_admins(monkeypatch, tool, user):
    _patch(monkeypatch, {"c1": _Repo()})
    result, _ = _call(tool, {**BASE, **POWER_TOOLS[tool]}, user=user)
    assert result["isError"] is False


def test_power_tools_are_labelled_in_tools_list():
    out = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, PLAIN))
    tools = {t["name"]: t for t in out["result"]["tools"]}
    for name in POWER_TOOLS:
        assert tools[name]["description"].startswith("POWER USERS ONLY")
    for name in ("create_note", "update_note"):
        assert tools[name]["description"].startswith("WRITE:")
    assert len(tools) == 19


# ── lookups ───────────────────────────────────────────────────────────────────


def test_get_attribute_values_lists_values_with_titles(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, payload = _call("get_attribute_values", {**BASE, "meta": "meta1"}, user=PLAIN)
    attr = payload["attributes"][0]
    assert attr["title"] == "Payment Method" and attr["distinctValues"] == 3
    assert attr["values"][0] == {"value": "Credit Card", "journeys": 900}
    assert attr["truncated"] is True


def test_get_attribute_values_defaults_to_all_and_rejects_bad_meta(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, payload = _call("get_attribute_values", BASE, user=PLAIN)
    assert [a["meta"] for a in payload["attributes"]] == ["meta1", "meta2", "meta3"]
    result, message = _call("get_attribute_values", {**BASE, "meta": "META_1; DROP"}, user=PLAIN)
    assert result["isError"] is True and "meta must be" in message


def test_find_journey_searches_every_connection_and_project(monkeypatch):
    stored = ProcessRepository._normalize_event_id("CRA-000123")
    finance = _Repo()
    finance.journeys[("5", stored)] = {"startDate": datetime(2024, 6, 12, 9, 59, 28),
                                       "endDate": datetime(2024, 6, 12, 11, 1, 11),
                                       "durationSecs": 3703.0, "stepCount": 5}
    monkeypatch.setattr(mcp.store, "connections_for_user", lambda u: [
        SimpleNamespace(id="c1", name="02 - Air Travel"),
        SimpleNamespace(id="c2", name="03 - Finance"),
        SimpleNamespace(id="c3", name="Offline"),
    ])
    _patch(monkeypatch, {"c1": _Repo(), "c2": finance, "c3": mcp.ToolError("timeout")})
    _, payload = _call("find_journey", {"eventId": "CRA-000123"}, user=PLAIN)
    assert payload["storedEventId"] == stored
    assert payload["matches"] == [{
        "connectionId": "c2", "connectionName": "03 - Finance", "projectId": 5,
        "title": "Flights", "startDate": "2024-06-12T09:59:28",
        "endDate": "2024-06-12T11:01:11", "durationSecs": 3703.0, "stepCount": 5}]
    assert payload["searched"] == {"connections": 3, "projects": 4}
    assert payload["unreachable"][0]["connectionName"] == "Offline"


def test_find_journey_not_found_and_validation(monkeypatch):
    monkeypatch.setattr(mcp.store, "connections_for_user", lambda u: [SimpleNamespace(id="c1", name="A")])
    _patch(monkeypatch, {"c1": _Repo()})
    _, payload = _call("find_journey", {"eventId": "NOPE-1"}, user=PLAIN)
    assert payload["matches"] == [] and "No journey" in payload["message"]
    assert _call("find_journey", {}, user=PLAIN)[0]["isError"] is True
    assert _call("find_journey", {"eventId": "x" * 600}, user=PLAIN)[0]["isError"] is True
    result, message = _call("find_journey", {"eventId": "A", "connectionId": "zz"}, user=PLAIN)
    assert result["isError"] is True and "not assigned" in message


def test_get_metadata_includes_step_details(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, payload = _call("get_metadata", BASE, user=PLAIN)
    details = {d["step"]: d for d in payload["stepDetails"]}
    assert payload["steps"] == ["Checkout", "Delivered", "Payment Failed"]
    assert details["Delivered"]["endOfProcess"] is True and details["Delivered"]["score"] == 15
    assert details["Checkout"]["belongsTo"] == "Order"
    assert details["Payment Failed"]["description"] is None   # no STEPS row → name only


# ── power tools: shaping and validation ───────────────────────────────────────


def test_compare_segments_reports_differences_b_minus_a(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, p = _call("compare_segments", {**BASE, "segmentA": {"meta1": "Bank", "label": "Bank"},
                                      "segmentB": {"meta1": "PayPal", "label": "PayPal"}})
    assert [s["label"] for s in p["segments"]] == ["Bank", "PayPal"]
    ends = {d["step"]: d for d in p["differences"]["endSteps"]}
    assert ends["Payment Failed"]["deltaPoints"] == -15.0
    top = p["differences"]["transitionTime"][0]
    assert (top["fromStep"], top["toStep"], top["deltaSecs"]) == ("Payment", "Delivered", -300.0)
    # Transitions below minOccurrences in either segment are left out.
    assert all(r["fromStep"] != "Rare" for r in p["differences"]["transitionTime"])


def test_compare_segments_requires_two_filter_objects(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    result, message = _call("compare_segments", {**BASE, "segmentA": "Bank", "segmentB": {}})
    assert result["isError"] is True and "segmentA must be an object" in message


def test_get_bottlenecks_ranks_by_total_wait(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, p = _call("get_bottlenecks", BASE)
    first = p["byTotalWaitTime"][0]
    assert (first["fromStep"], first["totalWaitSecs"]) == ("Rare", 19998.0)
    # The median ranking ignores the rare transition.
    assert p["slowestTypicalTransitions"][0]["fromStep"] == "Payment"
    assert p["selfLoops"][0]["fromStep"] == "Payment Retry"
    assert p["rework"][0]["extraVisits"] == 55


def test_get_trend_validates_granularity_and_passes_outcomes(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    result, message = _call("get_trend", {**BASE, "granularity": "hour"})
    assert result["isError"] is True and "granularity" in message
    _, p = _call("get_trend", {**BASE, "granularity": "week", "outcomeSteps": ["Rejected"]})
    assert p["granularity"] == "week" and p["periods"][0]["outcomeRate"] == 0.2


def test_get_outcome_drivers_splits_raising_and_lowering_factors(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, p = _call("get_outcome_drivers", {**BASE, "outcomeSteps": "Rejected"})
    assert p["outcomeRate"] == 0.1
    up = p["raisesOutcome"]["attributes"][0]
    assert (up["value"], up["outcomeRate"], up["deltaPoints"], up["lift"]) == ("Low", 0.3, 20.0, 3.0)
    assert up["title"] == "Customer Segment" and up["rateWithout"] == 0.05
    assert p["lowersOutcome"]["steps"][0]["step"] == "Bank"
    result, message = _call("get_outcome_drivers", BASE)
    assert result["isError"] is True and "outcomeSteps is required" in message


@pytest.mark.parametrize("rules, fragment", [
    (None, "rules is required"),
    ([], "rules is required"),
    ([{"type": "forbidden", "step": "A"}] * 11, "At most 10"),
    (["forbidden"], "must be an object"),
    ([{"type": "teleport"}], "unknown rule type"),
    ([{"type": "precedes", "before": "A"}], "needs 'after'"),
    ([{"type": "max_duration", "maxSecs": "soon"}], "numeric 'maxSecs'"),
    ([{"type": "max_duration", "maxSecs": -1}], "between 0"),
    ([{"type": "requires", "step": ["A"]}], "must be a step name"),
])
def test_check_conformance_validates_rules(monkeypatch, rules, fragment):
    _patch(monkeypatch, {"c1": _Repo()})
    result, message = _call("check_conformance", {**BASE, "rules": rules})
    assert result["isError"] is True and fragment in message


def test_check_conformance_reports_rates_examples_and_unknown_steps(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    _, p = _call("check_conformance", {**BASE, "examples": 2, "rules": [
        {"type": "precedes", "before": "Checkout", "after": "Delivered"},
        {"type": "forbidden", "step": "Teleport"}]})
    first = p["rules"][0]
    assert first["violations"] == 25 and first["violationRate"] == 0.05
    assert first["conformanceRate"] == 0.95 and first["exampleEventIds"] == ["abc", "abc"]
    assert first["rule"] == "'Checkout' must happen before 'Delivered'"
    assert p["unknownSteps"] == ["Teleport"] and "warning" in p


# ── the SQL the analysis layer generates ─────────────────────────────────────


class _Mgr:
    def __init__(self, rows=None):
        self.sql: list[str] = []
        self._steps_cache: dict = {}
        self.rows = rows if rows is not None else []

    async def execute(self, sql, timeout=None):
        self.sql.append(sql)
        return SimpleNamespace(rows=self.rows)


def _balanced(sql: str) -> bool:
    return sql.count("'") % 2 == 0


EVIL = "x' OR '1'='1'); DROP TABLE JOURNEYS; --"


def test_rule_sql_escapes_step_names():
    for raw in ({"type": "requires", "step": EVIL, "ifStep": EVIL},
                {"type": "forbidden", "step": EVIL},
                {"type": "precedes", "before": EVIL, "after": EVIL},
                {"type": "max_gap", "fromStep": EVIL, "toStep": EVIL, "maxSecs": 60}):
        sql = Rule.parse(raw).violation_sql()
        assert _balanced(sql) and "x'' OR ''1''=''1''); DROP TABLE JOURNEYS; --" in sql


def test_rule_numbers_are_coerced():
    sql = Rule.parse({"type": "max_duration", "maxSecs": "3600"}).violation_sql()
    assert sql.endswith("> 3600.0")


def test_analysis_queries_escape_filters_and_outcomes():
    mgr = _Mgr()
    an = Analysis(ProcessRepository(mgr))
    spec = FilterSpec(meta1=EVIL, includedSteps=[EVIL])
    _run(an.attribute_values("1", "meta2", spec, 10))
    _run(an.end_steps("1", spec))
    _run(an.rework("1", spec, 10))
    _run(an.trend("1", spec, "week", [EVIL], 10))
    _run(an.outcome_drivers("1", spec, [EVIL], 5))
    _run(an.conformance("1", spec, [Rule.parse({"type": "forbidden", "step": EVIL})], 3))
    _run(an.journey_lookup("1", EVIL))
    assert mgr.sql and all(_balanced(s) for s in mgr.sql)
    # The payload only ever appears in its escaped form.
    assert all("x' OR" not in s.replace("x'' OR", "") for s in mgr.sql)
    # Column and unit come from closed maps.
    assert "META_2" in mgr.sql[0] and "TRUNC(ST, 'IW')" in "".join(mgr.sql)


def test_analysis_rejects_unknown_meta_and_unit():
    an = Analysis(ProcessRepository(_Mgr()))
    with pytest.raises(KeyError):
        _run(an.attribute_values("1", "META_1 --", FilterSpec(), 10))
    with pytest.raises(KeyError):
        _run(an.trend("1", FilterSpec(), "hour", [], 10))


def test_project_id_is_coerced_to_an_integer():
    an = Analysis(ProcessRepository(_Mgr()))
    with pytest.raises(ValueError):
        _run(an.end_steps("1 OR 1=1", FilterSpec()))


# ── review hardening: bounded filters, batch cap, whole-journey analyses ──────


def test_filter_accepts_a_single_step_string_as_one_step():
    assert mcp._filter_spec({"includedSteps": "Approve"}).includedSteps == ["Approve"]


@pytest.mark.parametrize("args, fragment", [
    ({"includedSteps": ["A"] * 201}, "at most 200"),
    ({"excludedSteps": [""]}, "non-empty"),
    ({"excludedSteps": [{"x": 1}]}, "non-empty"),
    ({"meta1": "x" * 257}, "at most 256"),
    ({"meta2": ["Bank"]}, "must be a string"),
    ({"fromDate": "yesterday"}, "ISO dates"),
])
def test_filter_bounds_are_enforced(args, fragment):
    with pytest.raises(mcp.ToolError) as ei:
        mcp._filter_spec(args)
    assert fragment in str(ei.value)


def test_segment_filters_are_bounded_too(monkeypatch):
    _patch(monkeypatch, {"c1": _Repo()})
    result, message = _call("compare_segments", {**BASE, "segmentA": {"includedSteps": ["A"] * 500},
                                                 "segmentB": {}})
    assert result["isError"] is True and "at most 200" in message


def test_json_rpc_batches_are_capped(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setattr(type(mcp.store), "mcp_enabled", property(lambda self: True))

    async def _auth(request):
        return PLAIN

    monkeypatch.setattr(mcp, "_authenticate", _auth)
    client = TestClient(mcp.app)
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    ok = client.post("/mcp", json=[ping] * 20)
    assert ok.status_code == 200 and len(ok.json()) == 20
    too_many = client.post("/mcp", json=[ping] * 21)
    assert too_many.status_code == 400 and "at most 20" in too_many.json()["error"]["message"]
    junk = client.post("/mcp", json=[ping, "not-a-message", 7])
    assert junk.status_code == 200 and len(junk.json()) == 1


def test_per_journey_analyses_keep_whole_journeys_in_the_window():
    """A date window must not cut journeys: conformance/trend/ends see all their events."""
    mgr = _Mgr()
    an = Analysis(ProcessRepository(mgr))
    spec = FilterSpec(fromDate=datetime(2024, 3, 1), toDate=datetime(2024, 3, 31))
    _run(an.conformance("1", spec, [Rule.parse({"type": "requires", "step": "A"})], 0))
    _run(an.end_steps("1", spec))
    _run(an.trend("1", spec, "day", [], 10))
    for sql in mgr.sql:
        # journey-level: "active in window" inside the EVENT_ID qualifier …
        assert "MAX(CASE WHEN EVENT_TIME >= TIMESTAMP '2024-03-01 00:00:00'" in sql
        # … and no row-level cut of the journey's events.
        assert "\n                AND EVENT_TIME >= TIMESTAMP" not in sql
    # attribute values stay row-level (values seen inside the window)
    _run(an.attribute_values("1", "meta1", spec, 10))
    assert "\n                AND EVENT_TIME >= TIMESTAMP '2024-03-01 00:00:00'" in mgr.sql[-1]


def test_trend_keeps_the_most_recent_periods_when_capped():
    mgr = _Mgr(rows=[[datetime(2024, 3, 3), 5, 1.0, 1.0, 0], [datetime(2024, 3, 2), 4, 1.0, 1.0, 0]])
    an = Analysis(ProcessRepository(mgr))
    points = _run(an.trend("1", FilterSpec(), "day", [], 2))
    assert "ORDER BY PERIOD_START DESC" in mgr.sql[-1]
    assert [p["period"] for p in points] == ["2024-03-02", "2024-03-03"]   # oldest first
