"""Store-level tests for notification rules + run state: CRUD, the per-project toggle,
state upsert, and the cascade that removes a connection's rules when it is deleted."""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401

    import app.store.security as security_mod

    importlib.reload(security_mod)
    return security_mod.store


def _conn(store, name="Cust", assignments=("alice",)):
    return store.upsert_connection({
        "name": name, "host": "db.example.com", "port": 8563, "username": "svc",
        "schema": "MINING", "password": "s3cret", "llmURL": "", "llmModel": "", "llmKey": "",
        "assignments": list(assignments),
    }).id


def _add(store, cid, *, project_id=1, enabled=True, name="r"):
    return store.add_rule(
        connection_id=cid, project_id=project_id, project_title="Orders", kind="transition_metric",
        name=name, severity="URGENT", interval_secs=300, enabled=enabled,
        config=json.dumps({"fromStep": "A", "toStep": "B", "metric": "Avg Time",
                            "comparator": ">", "threshold": 7200.0}),
        created_by="alice",
    )


def test_add_list_and_visibility_by_connection(store):
    c1 = _conn(store, "One", ["alice"])
    c2 = _conn(store, "Two", ["bob"])
    r1 = _add(store, c1)
    _add(store, c2)
    # A user assigned only to c1 sees only c1's rule.
    visible = store.list_rules_for_connections([c1])
    assert [r.id for r in visible] == [r1.id]
    assert store.list_rules_for_connections([]) == []
    # The engine sees all rules.
    assert len(store.list_all_notification_rules()) == 2


def test_update_resets_state_and_config(store):
    cid = _conn(store)
    rule = _add(store, cid)
    store.set_rule_state(rule.id, last_value=9000.0, triggered=True,
                         triggered_at="2026-01-01T00:00:00+00:00", cleared_at="")
    assert store.get_rule_state(rule.id)["triggered"] is True
    updated = store.update_rule(
        rule.id, project_id=1, project_title="Orders", kind="transition_metric", name="r2",
        severity="INFO", interval_secs=3600, enabled=True,
        config=json.dumps({"fromStep": "A", "toStep": "C", "metric": "Count",
                            "comparator": "<", "threshold": 5}),
    )
    assert updated.name == "r2" and updated.severity == "INFO"
    assert updated.config_dict()["toStep"] == "C"
    # Editing a rule clears its stale run state so the next tick re-evaluates.
    assert store.get_rule_state(rule.id) is None


def test_toggle_single_and_per_project(store):
    cid = _conn(store)
    a = _add(store, cid, project_id=1, name="a")
    b = _add(store, cid, project_id=1, name="b")
    other = _add(store, cid, project_id=2, name="c")
    store.set_rule_enabled(a.id, False)
    assert store.get_rule(a.id).enabled is False
    # Per-tile toggle flips every rule on that project, not others.
    changed = store.set_rules_enabled_for_project(cid, 1, False)
    assert changed == 2
    assert store.get_rule(a.id).enabled is False and store.get_rule(b.id).enabled is False
    assert store.get_rule(other.id).enabled is True


def test_state_upsert_and_batch_read(store):
    cid = _conn(store)
    r = _add(store, cid)
    store.set_rule_state(r.id, last_value=100.0, triggered=True,
                         triggered_at="2026-02-02T00:00:00+00:00", cleared_at="")
    store.set_rule_state(r.id, last_value=50.0, triggered=False,
                         triggered_at="", cleared_at="2026-02-02T01:00:00+00:00")
    st = store.get_rule_states([r.id])[r.id]
    assert st["triggered"] is False and st["lastValue"] == 50.0
    assert st["clearedAt"].startswith("2026-02-02")


def test_delivery_config_roundtrips(store):
    cid = _conn(store)
    rule = store.add_rule(
        connection_id=cid, project_id=1, project_title="Orders", kind="transition_metric",
        name="r", severity="URGENT", interval_secs=300, enabled=True,
        config=json.dumps({"fromStep": "A", "toStep": "B", "metric": "Avg Time",
                           "comparator": ">", "threshold": 7200}),
        delivery=json.dumps({"webpush": True}), created_by="alice",
    )
    assert store.get_rule(rule.id).delivery_dict() == {"webpush": True}
    store.update_rule(rule.id, project_id=1, project_title="Orders", kind="transition_metric",
                      name="r", severity="URGENT", interval_secs=300, enabled=True,
                      config=rule.config, delivery=json.dumps({}))
    assert store.get_rule(rule.id).delivery_dict() == {}


def test_push_subscriptions_and_connection_recipients(store):
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    cid = _conn(store, assignments=("alice", "bob"))
    store.add_push_subscription("alice", "https://push/a", "pa", "aa")
    store.add_push_subscription("bob", "https://push/b", "pb", "ab")
    # Re-subscribing the same endpoint updates, not duplicates.
    store.add_push_subscription("alice", "https://push/a", "pa2", "aa2")
    assert len(store.list_push_subscriptions("alice")) == 1
    assert store.list_push_subscriptions("alice")[0]["p256dh"] == "pa2"
    recipients = store.subscriptions_for_users(store.usernames_for_connection(cid))
    assert {s["endpoint"] for s in recipients} == {"https://push/a", "https://push/b"}
    store.delete_push_subscription("https://push/a", "alice")
    assert store.list_push_subscriptions("alice") == []


def test_vapid_keys_are_stable(store):
    pub1, priv1 = store.vapid_keys()
    pub2, priv2 = store.vapid_keys()
    assert pub1 == pub2 and priv1 == priv2  # generated once, then persisted
    assert priv1.startswith(b"-----BEGIN PRIVATE KEY-----")


def test_delete_rule_and_cascade_on_connection_delete(store):
    cid = _conn(store)
    r = _add(store, cid)
    store.set_rule_state(r.id, last_value=1.0, triggered=False, triggered_at="", cleared_at="")
    assert store.delete_rule(r.id) is True
    assert store.get_rule(r.id) is None
    assert store.get_rule_state(r.id) is None
    # Deleting the connection removes any remaining rules + their state.
    r2 = _add(store, cid)
    store.set_rule_state(r2.id, last_value=1.0, triggered=True,
                         triggered_at="2026-03-03T00:00:00+00:00", cleared_at="")
    store.delete_connection(cid)
    assert store.list_all_notification_rules() == []
    assert store.get_rule_state(r2.id) is None
