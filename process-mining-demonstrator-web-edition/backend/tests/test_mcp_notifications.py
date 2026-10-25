"""MCP notification tools: list_notifications (read) and set_notification_enabled (write).

Covers the feature gate, per-connection assignment (no cross-tenant leakage / no id
enumeration), the power-user gate on the write, ruleId validation, the rate limit, and the
urgency+time ordering. The store is faked — no SQLite, no Exasol."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parents[2] / "mcp" / "server.py"
_spec = importlib.util.spec_from_file_location("mcp_server_notifs", _PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

ALICE = SimpleNamespace(username="alice", is_enabled=True, is_power=True, is_admin=False)
PLAIN = SimpleNamespace(username="pat", is_enabled=True, is_power=False, is_admin=False)
RID = "a" * 32
RID2 = "b" * 32


def _run(coro):
    return asyncio.run(coro)


def _call(name, arguments, user=ALICE):
    out = _run(mcp._dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments}}, user))
    result = out["result"]
    text = result["content"][0]["text"]
    return result, (text if result["isError"] else json.loads(text))


def _rule(rid, *, cid="c1", pid=1, enabled=True, severity="INFO",
          metric="Avg Time", comparator=">", threshold=7200, name=""):
    cfg = {"fromStep": "A", "toStep": "B", "metric": metric,
           "comparator": comparator, "threshold": threshold}
    return SimpleNamespace(
        id=rid, connection_id=cid, project_id=pid, project_title="Orders",
        kind="transition_metric", name=name, severity=severity, interval_secs=300,
        enabled=enabled, config_dict=lambda cfg=cfg: cfg,
    )


class _FakeStore:
    def __init__(self, rules, states, assignments):
        self.rules = {r.id: r for r in rules}
        self.states = states
        self.assignments = assignments  # cid -> set(usernames)
        self.toggles: list[tuple[str, bool]] = []

    def user_can_use(self, cid, username):
        return username in self.assignments.get(cid, set())

    def list_rules_for_connections(self, cids):
        return [r for r in self.rules.values() if r.connection_id in cids]

    def get_rule_states(self, ids):
        return {i: self.states[i] for i in ids if i in self.states}

    def get_rule(self, rid):
        return self.rules.get(rid)

    def get_rule_state(self, rid):
        return self.states.get(rid)

    def set_rule_enabled(self, rid, enabled):
        self.toggles.append((rid, enabled))
        if rid in self.rules:
            self.rules[rid].enabled = enabled
        return rid in self.rules


@pytest.fixture
def store(monkeypatch):
    rules = [
        _rule(RID, severity="URGENT", enabled=True),
        _rule(RID2, severity="INFO", enabled=True, pid=2),
    ]
    states = {
        RID: {"triggered": True, "triggeredAt": "2026-09-14T10:00:00+00:00",
              "lastValue": 9000.0, "lastRunAt": "2026-09-14T10:00:00+00:00", "lastError": None},
        RID2: {"triggered": False, "triggeredAt": None, "lastValue": 100.0,
               "lastRunAt": "2026-09-14T10:00:00+00:00", "lastError": None},
    }
    fake = _FakeStore(rules, states, {"c1": {"alice", "pat"}})
    # notifications_enabled is read as mcp.store.notifications_enabled — a plain attr on the fake.
    fake.notifications_enabled = True
    monkeypatch.setattr(mcp, "store", fake)
    monkeypatch.setattr(mcp.logx, "usage", lambda *a, **k: None)
    mcp._NOTE_WRITES.clear()
    return fake


def test_list_returns_rules_with_state_sorted_triggered_first(store):
    result, payload = _call("list_notifications", {"connectionId": "c1"})
    assert result["isError"] is False
    assert payload["summary"] == {"total": 2, "triggered": 1}
    # URGENT + triggered first.
    assert payload["rules"][0]["id"] == RID
    assert payload["rules"][0]["triggered"] is True
    assert payload["rules"][0]["lastValue"] == 9000.0
    assert payload["rules"][0]["fromStep"] == "A" and payload["rules"][0]["metric"] == "Avg Time"


def test_list_project_filter(store):
    _, payload = _call("list_notifications", {"connectionId": "c1", "projectId": 2})
    assert [r["id"] for r in payload["rules"]] == [RID2]


def test_list_triggered_only(store):
    _, payload = _call("list_notifications", {"connectionId": "c1", "triggeredOnly": True})
    assert [r["id"] for r in payload["rules"]] == [RID]


def test_list_rejects_unassigned_connection(store):
    result, text = _call("list_notifications", {"connectionId": "c1"}, user=SimpleNamespace(
        username="mallory", is_enabled=True, is_power=True, is_admin=False))
    assert result["isError"] is True and "not assigned" in text


def test_list_disabled_feature(store):
    store.notifications_enabled = False
    result, text = _call("list_notifications", {"connectionId": "c1"})
    assert result["isError"] is True and "not enabled" in text


def test_set_enabled_toggles_for_power_user(store):
    result, payload = _call("set_notification_enabled", {"ruleId": RID, "enabled": False})
    assert result["isError"] is False
    assert payload["updated"] is True and payload["rule"]["enabled"] is False
    assert store.toggles == [(RID, False)]


def test_set_enabled_requires_a_manager_role(store):
    # Plain user (no power / developer / admin) is refused.
    result, text = _call("set_notification_enabled", {"ruleId": RID, "enabled": False}, user=PLAIN)
    assert result["isError"] is True and "power users" in text
    assert store.toggles == []
    # A developer may toggle.
    dev = SimpleNamespace(username="dev", is_enabled=True, is_power=False, is_developer=True)
    store.assignments["c1"].add("dev")
    result, _ = _call("set_notification_enabled", {"ruleId": RID, "enabled": False}, user=dev)
    assert result["isError"] is False and store.toggles == [(RID, False)]
    # An administrator may too.
    admin = SimpleNamespace(username="root", is_enabled=True, is_power=False, is_admin=True)
    store.assignments["c1"].add("root")
    result, _ = _call("set_notification_enabled", {"ruleId": RID, "enabled": True}, user=admin)
    assert result["isError"] is False and store.toggles == [(RID, False), (RID, True)]


def test_set_enabled_validates_rule_id(store):
    result, text = _call("set_notification_enabled", {"ruleId": "not-a-uuid", "enabled": True})
    assert result["isError"] is True and "ruleId" in text


def test_set_enabled_unknown_rule_is_indistinguishable(store):
    result, text = _call("set_notification_enabled", {"ruleId": "c" * 32, "enabled": True})
    assert result["isError"] is True and "not found" in text


def test_set_enabled_on_unassigned_connection_is_not_found(store):
    # A rule that exists but on a connection the caller can't use → same "not found".
    store.rules[RID].connection_id = "cX"
    result, text = _call("set_notification_enabled", {"ruleId": RID, "enabled": True})
    assert result["isError"] is True and "not found" in text


def test_set_enabled_is_rate_limited(store):
    # Exhaust the per-user write window, then the next attempt is refused.
    for _ in range(mcp.MCP_NOTE_WRITES_PER_MIN):
        _call("set_notification_enabled", {"ruleId": RID, "enabled": True})
    result, text = _call("set_notification_enabled", {"ruleId": RID, "enabled": True})
    assert result["isError"] is True and "limit" in text.lower()
