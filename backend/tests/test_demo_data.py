"""Tests for the demo-data generators (app.db.demo_data): the retail (Online
Bookstore) and finance (Online Credit Application) datasets.

The event-log generators are pure (seedable RNG) so structure and determinism are
asserted directly; the loader is driven with a fake connection that records SQL.
"""

from __future__ import annotations

import asyncio
import random
from collections import defaultdict

from app.db import demo_data as d
from app.db import manager


class FakeConn:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.committed = False
        self.closed = False

    def execute(self, sql: str) -> None:
        self.calls.append(sql)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def _run(monkeypatch, conn, dataset="retail", **overrides):
    monkeypatch.setattr(manager.DatabaseManager, "_open", lambda self, server, pw: conn)
    kwargs = dict(
        dataset=dataset, host="h", port=8563, username="u", password="p", schema="PM", journeys=2
    )
    kwargs.update(overrides)
    return asyncio.run(d.generate_demo_content(**kwargs))


def _by_journey(rows):
    grouped: dict[str, list] = defaultdict(list)
    for r in rows:
        grouped[r.event_id].append(r)
    return grouped


# ── retail: Online Bookstore ──────────────────────────────────────────────────


def test_retail_journeys_start_with_login_and_are_ordered():
    grouped = _by_journey(d.generate_retail_rows(40, random.Random(1)))
    assert len(grouped) == 40
    for events in grouped.values():
        assert events[0].step == "Login"
        assert [e.step_id for e in events] == list(range(1, len(events) + 1))
        assert events[0].meta1 in {"Credit Card", "PayPal", "Bank Transfer"}


def test_retail_step_defs_and_determinism():
    assert len(d._RETAIL_STEP_DEFS) == 24
    a = d.generate_retail_rows(8, random.Random(5))
    b = d.generate_retail_rows(8, random.Random(5))
    assert [(r.event_id, r.step) for r in a] == [(r.event_id, r.step) for r in b]


# ── finance: Online Credit Application ────────────────────────────────────────


def test_finance_entry_and_exit_points_and_metas():
    grouped = _by_journey(d.generate_finance_rows(600, random.Random(2)))
    for events in grouped.values():
        # Entry points are the "Bank"/"Affiliate" steps; exits are Payment/Rejected.
        assert events[0].step in {"Bank", "Affiliate"}
        assert events[-1].step in {"Payment", "Rejected"}
        # meta3 mirrors the channel; metas are constant within a journey.
        assert events[0].meta3 == events[0].step
        assert len({e.meta3 for e in events}) == 1
    # Meta titles as specified.
    assert d.DATASETS["finance"].meta_titles == ("Applied Credit Sum", "Income Class", "Channel")


def test_finance_flow_features_present():
    rows = d.generate_finance_rows(2000, random.Random(9))
    seen = {r.step for r in rows}
    # Assessment naming, agent-review + senior-approval loops, and the accept path.
    for step in (
        "Application Checked",
        "Additional Information Requested",  # 20% rework loop
        "Credit Assessment",
        "Credit Check",
        "Agent Review",  # 75–90% score band
        "Senior Agent Approval",  # >10.000 EUR extra agent
        "Accepted",
        "Payment to Applicant",
    ):
        assert step in seen, step
    # A rework loop means some journeys hit "Application Checked" more than once.
    grouped = _by_journey(rows)
    assert any(
        sum(1 for e in v if e.step == "Application Checked") >= 2 for v in grouped.values()
    )


def test_finance_affiliate_pays_out_faster_than_bank():
    grouped = _by_journey(d.generate_finance_rows(3000, random.Random(11)))
    paid = [v for v in grouped.values() if v[-1].step == "Payment"]

    def cycle(v):
        return (v[-1].event_time - v[0].event_time).total_seconds()

    bank = [cycle(v) for v in paid if v[0].step == "Bank"]
    affiliate = [cycle(v) for v in paid if v[0].step == "Affiliate"]
    assert sum(affiliate) / len(affiliate) < sum(bank) / len(bank)


# ── loader ────────────────────────────────────────────────────────────────────


def test_loader_provisions_and_loads_retail(monkeypatch):
    conn = FakeConn()
    res = _run(monkeypatch, conn, dataset="retail", journeys=3)
    assert res["ok"] and res["journeys"] == 3
    assert res["project"] == "Online Bookstore" and res["dataset"] == "retail"
    joined = "\n".join(conn.calls)
    assert conn.calls[0] == 'CREATE SCHEMA IF NOT EXISTS "PM"'
    for tbl in ("PROJECTS", "JOURNEYS", "STEPS", "METAS", "NOTES"):
        assert f"CREATE TABLE IF NOT EXISTS {tbl}" in joined
    assert "PROJECT_ID = 'BOOKSTORE'" in joined and "Online Bookstore" in joined
    assert joined.count("INSERT INTO STEPS") == 24
    assert conn.committed and conn.closed


def test_loader_provisions_and_loads_finance(monkeypatch):
    conn = FakeConn()
    res = _run(monkeypatch, conn, dataset="finance", journeys=3)
    assert res["ok"] and res["project"] == "Online Credit Application"
    joined = "\n".join(conn.calls)
    assert "PROJECT_ID = 'CREDIT'" in joined
    assert "Applied Credit Sum" in joined  # META titles inserted
    assert joined.count("INSERT INTO STEPS") == len(d._FINANCE_STEP_DEFS)
    assert "INSERT INTO JOURNEYS" in joined


def test_loader_touches_only_the_dataset_project(monkeypatch):
    conn = FakeConn()
    _run(monkeypatch, conn, dataset="finance", journeys=1)
    for verb in ("DELETE FROM PROJECTS", "DELETE FROM METAS", "DELETE FROM JOURNEYS"):
        stmts = [c for c in conn.calls if c.startswith(verb)]
        assert stmts and all("PROJECT_ID = 'CREDIT'" in s for s in stmts)


def test_loader_rejects_unknown_dataset(monkeypatch):
    conn = FakeConn()
    res = _run(monkeypatch, conn, dataset="nope")
    assert res["ok"] is False and "nope" in res["error"]
    assert conn.calls == []


def test_loader_clamps_journeys(monkeypatch):
    seen: dict = {}

    def _fake(count, rng=None):
        seen["count"] = count
        return []

    monkeypatch.setattr(d.DATASETS["retail"], "generate", _fake)
    conn = FakeConn()
    res = _run(monkeypatch, conn, dataset="retail", journeys=10_000_000)
    assert seen["count"] == d.MAX_JOURNEYS and res["journeys"] == d.MAX_JOURNEYS


def test_loader_validates_schema_and_count(monkeypatch):
    conn = FakeConn()
    assert _run(monkeypatch, conn, schema="  ", journeys=10)["ok"] is False
    assert conn.calls == []
    conn2 = FakeConn()
    assert _run(monkeypatch, conn2, journeys=0)["ok"] is False


def test_loader_reports_a_friendly_error(monkeypatch):
    class BoomConn(FakeConn):
        def execute(self, sql: str) -> None:
            super().execute(sql)
            if "INSERT INTO JOURNEYS" in sql:
                raise RuntimeError("insufficient privileges: INSERT denied")

    conn = BoomConn()
    res = _run(monkeypatch, conn, journeys=2)
    assert res["ok"] is False and "insufficient privileges" in res["error"]
    assert conn.closed
