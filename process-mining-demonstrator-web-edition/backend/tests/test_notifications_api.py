"""Compute-backend notification endpoints: the admin feature gate, the manage-role gate
(power/developer/admin), the per-connection assignment IDOR guard, rule CRUD, and the
single-rule / per-project enable toggles. No Exasol — rule CRUD is DB-free."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401

    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.db.manager as manager

    importlib.reload(manager)
    import app.api.connections as connections_api

    importlib.reload(connections_api)
    import app.api.notifications as notifications_api

    importlib.reload(notifications_api)
    import app.main as main

    importlib.reload(main)
    security_mod.store.set_notifications_enabled(True)
    return main.app, security_mod.store


def _user(store, name, *, power=False, developer=False, admin=False):
    store.create_user(name, "pw", is_admin=admin)
    if power:
        store.set_power(name, True)
    if developer:
        store.set_developer(name, True)


def _conn(store, *, name="Cust", assignments):
    return store.upsert_connection({
        "name": name, "host": "db.example.com", "port": 8563, "username": "svc",
        "schema": "MINING", "password": "s3cret", "llmURL": "", "llmModel": "", "llmKey": "",
        "assignments": list(assignments),
    }).id


def _rule_body(cid, **over):
    body = {
        "connectionId": cid, "projectId": 1, "projectTitle": "Orders",
        "kind": "transition_metric", "name": "Slow A→B", "severity": "URGENT",
        "intervalSecs": 300, "enabled": True,
        "config": {"fromStep": "A", "toStep": "B", "metric": "Avg Time",
                   "comparator": ">", "threshold": 7200},
    }
    body.update(over)
    return body


def _h(user):
    return {"X-PMW-User": user}


def test_feature_gate_returns_403_when_disabled(backend):
    app, store = backend
    store.set_notifications_enabled(False)
    _user(store, "alice", power=True)
    _conn(store, assignments=["alice"])
    client = TestClient(app)
    assert client.get("/api/notifications", headers=_h("alice")).status_code == 403
    assert client.post("/api/notifications", json=_rule_body("x"),
                       headers=_h("alice")).status_code == 403


def test_plain_user_can_view_but_not_manage(backend):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "pat")  # plain standard user
    cid = _conn(store, assignments=["alice", "pat"])
    client = TestClient(app)
    # Power user creates a rule.
    created = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice"))
    assert created.status_code == 200, created.text
    # Plain user sees it (shared per connection) but canManage is false.
    listed = client.get("/api/notifications", headers=_h("pat")).json()
    assert len(listed["rules"]) == 1 and listed["canManage"] is False
    assert listed["rules"][0]["state"] == {}
    # …and cannot create.
    assert client.post("/api/notifications", json=_rule_body(cid),
                       headers=_h("pat")).status_code == 403


def test_admin_can_manage(backend):
    app, store = backend
    _user(store, "root", admin=True)
    cid = _conn(store, assignments=["root"])
    client = TestClient(app)
    assert client.get("/api/notifications", headers=_h("root")).json()["canManage"] is True
    assert client.post("/api/notifications", json=_rule_body(cid),
                       headers=_h("root")).status_code == 200


def test_developer_can_manage(backend):
    app, store = backend
    _user(store, "dev", developer=True)
    cid = _conn(store, assignments=["dev"])
    client = TestClient(app)
    assert client.get("/api/notifications", headers=_h("dev")).json()["canManage"] is True
    assert client.post("/api/notifications", json=_rule_body(cid),
                       headers=_h("dev")).status_code == 200


def test_create_rejects_unassigned_connection(backend):
    app, store = backend
    _user(store, "alice", power=True)
    _conn(store, name="Alice", assignments=["alice"])
    other = _conn(store, name="BobOnly", assignments=["bob"])
    client = TestClient(app)
    # Alice is a manager but not assigned to Bob's connection — IDOR guard.
    r = client.post("/api/notifications", json=_rule_body(other), headers=_h("alice"))
    assert r.status_code == 403


def test_bad_config_is_400(backend):
    app, store = backend
    _user(store, "dev", developer=True)
    cid = _conn(store, assignments=["dev"])
    client = TestClient(app)
    bad = _rule_body(cid, config={"fromStep": "A", "toStep": "B",
                                  "metric": "Nope", "comparator": ">", "threshold": 1})
    assert client.post("/api/notifications", json=bad, headers=_h("dev")).status_code == 400


def test_crud_and_toggles(backend):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)

    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]

    # Edit it.
    edit = _rule_body(cid, name="Renamed", severity="INFO", intervalSecs=3600)
    up = client.put(f"/api/notifications/{rid}", json=edit, headers=_h("alice")).json()
    assert up["name"] == "Renamed" and up["severity"] == "INFO" and up["intervalSecs"] == 3600

    # Toggle a single rule off.
    t = client.post(f"/api/notifications/{rid}/enabled", json={"enabled": False}, headers=_h("alice"))
    assert t.json()["enabled"] is False
    assert store.get_rule(rid).enabled is False

    # Per-project toggle back on.
    pt = client.post("/api/notifications/project-toggle",
                     json={"connectionId": cid, "projectId": 1, "enabled": True},
                     headers=_h("alice"))
    assert pt.json()["changed"] == 1 and store.get_rule(rid).enabled is True

    # Delete.
    d = client.delete(f"/api/notifications/{rid}", headers=_h("alice"))
    assert d.json()["deleted"] is True
    assert store.get_rule(rid) is None


def test_create_rule_stores_delivery(backend):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    body = _rule_body(cid)
    body["delivery"] = {"webpush": True}
    created = TestClient(app).post("/api/notifications", json=body, headers=_h("alice")).json()
    assert created["delivery"] == {"webpush": True}


def _fire(store, rid, at):
    """Mark a rule's run state as currently triggered, as the engine would."""
    store.set_rule_state(rid, last_value=9000.0, triggered=True, triggered_at=at, cleared_at="")


def test_acknowledge_hides_until_the_alert_retriggers(backend):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]

    # The alert fires; it is not acknowledged yet.
    _fire(store, rid, "2026-10-20T10:00:00+00:00")
    assert store.get_rule_state(rid)["acknowledged"] is False

    # Acknowledge it → acknowledged for THIS trigger episode.
    acked = client.post(f"/api/notifications/{rid}/ack", headers=_h("alice")).json()
    assert acked["state"]["acknowledged"] is True

    # A later evaluation that keeps the same triggered-at (still the same episode) stays ack'd.
    _fire(store, rid, "2026-10-20T10:00:00+00:00")
    assert store.get_rule_state(rid)["acknowledged"] is True

    # It clears, then fires afresh with a NEW triggered-at → the acknowledgement lapses.
    store.set_rule_state(rid, last_value=100.0, triggered=False, triggered_at="", cleared_at="x")
    _fire(store, rid, "2026-10-20T12:30:00+00:00")
    assert store.get_rule_state(rid)["acknowledged"] is False


def test_acknowledge_is_a_noop_when_not_triggered(backend):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    store.set_rule_state(rid, last_value=100.0, triggered=False, triggered_at="", cleared_at="")
    body = client.post(f"/api/notifications/{rid}/ack", headers=_h("alice")).json()
    assert body["state"]["acknowledged"] is False


def test_acknowledge_rejects_unassigned_user(backend):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "mallory")
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    _fire(store, rid, "2026-10-20T10:00:00+00:00")
    assert client.post(f"/api/notifications/{rid}/ack", headers=_h("mallory")).status_code == 403


def test_push_key_subscribe_and_unsubscribe(backend):
    app, store = backend
    _user(store, "alice", power=True)
    client = TestClient(app)
    key = client.get("/api/notifications/push/key", headers=_h("alice")).json()
    assert isinstance(key["publicKey"], str) and len(key["publicKey"]) > 50
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "P", "auth": "A"}}
    assert client.post("/api/notifications/push/subscribe", json=sub,
                       headers=_h("alice")).json()["subscribed"] is True
    assert len(store.list_push_subscriptions("alice")) == 1
    client.post("/api/notifications/push/unsubscribe", json={"endpoint": sub["endpoint"]},
                headers=_h("alice"))
    assert store.list_push_subscriptions("alice") == []


def _subscribe(client, user="alice", endpoint="https://push.example.com/x"):
    client.post("/api/notifications/push/subscribe",
                json={"endpoint": endpoint, "keys": {"p256dh": "P", "auth": "A"}},
                headers=_h(user))


def test_push_test_without_subscription_reports_it(backend):
    app, store = backend
    _user(store, "alice", power=True)
    r = TestClient(app).post("/api/notifications/push/test", headers=_h("alice")).json()
    assert r["sent"] == 0 and r["errors"]


def test_push_test_sends_to_the_users_devices(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    client = TestClient(app)
    _subscribe(client)
    import app.notifications.webpush as wp

    async def _ok(sub, body, **kw):
        return None

    monkeypatch.setattr(wp, "send", _ok)
    r = client.post("/api/notifications/push/test", headers=_h("alice")).json()
    assert r == {"sent": 1, "failed": 0, "errors": []}


def test_push_test_surfaces_the_push_service_error(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    client = TestClient(app)
    _subscribe(client)
    import app.notifications.webpush as wp

    async def _boom(sub, body, **kw):
        raise RuntimeError("push service returned 403: BadJwtToken")

    monkeypatch.setattr(wp, "send", _boom)
    r = client.post("/api/notifications/push/test", headers=_h("alice")).json()
    assert r["sent"] == 0 and r["failed"] == 1 and any("403" in e for e in r["errors"])


def test_push_subscribe_rejects_insecure_endpoint(backend):
    app, store = backend
    _user(store, "alice")
    bad = {"endpoint": "http://insecure/x", "keys": {"p256dh": "P", "auth": "A"}}
    assert TestClient(app).post("/api/notifications/push/subscribe", json=bad,
                                headers=_h("alice")).status_code == 400


def test_toggle_requires_manager(backend):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "pat")
    cid = _conn(store, assignments=["alice", "pat"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    r = client.post(f"/api/notifications/{rid}/enabled", json={"enabled": False}, headers=_h("pat"))
    assert r.status_code == 403


# ── the "Test now" endpoint ───────────────────────────────────────────────────


class _FakeMgr:
    err: str | None = None

    def __init__(self, *a, **k):
        self.use_materialized_transitions = False

    async def connect_connection(self, conn):
        return type(self).err

    async def disconnect(self):
        return None


def _patch_eval(monkeypatch, result, *, connect_err=None):
    import app.api.notifications as napi
    import app.notifications.engine as neng

    _FakeMgr.err = connect_err
    monkeypatch.setattr(napi, "DatabaseManager", _FakeMgr)

    async def _fake(repo, project_id, kind, config):
        return result

    monkeypatch.setattr(neng, "evaluate_rule", _fake)


def test_test_endpoint_reports_measured_value(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    _patch_eval(monkeypatch, (9000.0, True, "", None))
    r = TestClient(app).post("/api/notifications/test", json=_rule_body(cid), headers=_h("alice"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": True, "value": 9000.0, "triggered": True, "hasData": True, "error": None}


def test_test_endpoint_reports_no_data(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    _patch_eval(monkeypatch, (None, False, "", None))
    body = TestClient(app).post("/api/notifications/test", json=_rule_body(cid),
                                headers=_h("alice")).json()
    assert body["hasData"] is False and body["triggered"] is False and body["ok"] is True


def test_test_endpoint_handles_connect_failure_without_500(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    _patch_eval(monkeypatch, (0.0, False, ""), connect_err="boom")
    r = TestClient(app).post("/api/notifications/test", json=_rule_body(cid), headers=_h("alice"))
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["hasData"] is False


def _patch_check(monkeypatch, state):
    import app.notifications.engine as neng

    async def _fake(rule):
        return state

    monkeypatch.setattr(neng, "check_rule", _fake)


def test_check_now_returns_fresh_state(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    _patch_check(monkeypatch, {"triggered": True, "triggeredAt": "2026-09-14T10:00:00+00:00",
                               "lastValue": 1234.0, "lastRunAt": "x", "lastError": None,
                               "clearedAt": None})
    r = client.post(f"/api/notifications/{rid}/check", headers=_h("alice"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == rid
    assert body["state"]["triggered"] is True and body["state"]["lastValue"] == 1234.0


def test_check_now_available_to_any_assigned_user(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "pat")  # plain user, assigned
    cid = _conn(store, assignments=["alice", "pat"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    _patch_check(monkeypatch, {"triggered": False, "lastRunAt": "x"})
    assert client.post(f"/api/notifications/{rid}/check", headers=_h("pat")).status_code == 200


def test_check_now_rejects_unassigned(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "mallory")
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    assert client.post(f"/api/notifications/{rid}/check", headers=_h("mallory")).status_code == 403


def _patch_check_all(monkeypatch, recorder=None):
    import app.notifications.engine as neng

    async def _fake(rules):
        if recorder is not None:
            recorder["ids"] = [r.id for r in rules]

    monkeypatch.setattr(neng, "check_rules", _fake)


def test_check_all_re_evaluates_and_returns_the_list(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    cid = _conn(store, assignments=["alice"])
    client = TestClient(app)
    rid = client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice")).json()["id"]
    rec = {}
    _patch_check_all(monkeypatch, rec)
    r = client.post("/api/notifications/check-all", headers=_h("alice"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["id"] for x in body["rules"]] == [rid] and body["canManage"] is True
    assert rec["ids"] == [rid]  # every visible rule was re-evaluated


def test_check_all_available_to_any_assigned_user(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "pat")  # plain user
    cid = _conn(store, assignments=["alice", "pat"])
    client = TestClient(app)
    client.post("/api/notifications", json=_rule_body(cid), headers=_h("alice"))
    _patch_check_all(monkeypatch)
    resp = client.post("/api/notifications/check-all", headers=_h("pat"))
    assert resp.status_code == 200 and resp.json()["canManage"] is False


def test_check_all_gated_when_disabled(backend):
    app, store = backend
    store.set_notifications_enabled(False)
    _user(store, "alice", power=True)
    _conn(store, assignments=["alice"])
    assert TestClient(app).post("/api/notifications/check-all",
                                headers=_h("alice")).status_code == 403


def test_test_endpoint_is_gated(backend, monkeypatch):
    app, store = backend
    _user(store, "alice", power=True)
    _user(store, "pat")
    cid = _conn(store, assignments=["alice", "pat"])
    client = TestClient(app)
    # Non-manager is refused before any DB work.
    assert client.post("/api/notifications/test", json=_rule_body(cid),
                       headers=_h("pat")).status_code == 403
    # Bad config is a 400, also before the DB.
    bad = _rule_body(cid, config={"fromStep": "A", "toStep": "B", "metric": "Nope",
                                  "comparator": ">", "threshold": 1})
    assert client.post("/api/notifications/test", json=bad,
                       headers=_h("alice")).status_code == 400
