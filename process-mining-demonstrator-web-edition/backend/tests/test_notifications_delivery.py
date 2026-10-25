"""Remote delivery: the channel dispatch (web push to a connection's subscribers, dropping
gone endpoints) and the engine's edge logic (deliver once, on the transition into triggered,
only for an enabled rule with channels). The actual push send is faked — no network."""

from __future__ import annotations

import asyncio
import importlib
import json

import pytest


@pytest.fixture
def mods(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401

    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.notifications.delivery as delivery

    importlib.reload(delivery)
    import app.notifications.engine as engine

    importlib.reload(engine)
    return security_mod.store, delivery, engine


def _conn(store, users):
    for u in users:  # assignments only persist for existing users
        if store.get_user(u) is None:
            store.create_user(u, "pw", is_admin=False)
    return store.upsert_connection({
        "name": "Cust", "host": "h", "port": 8563, "username": "svc", "schema": "S",
        "password": "p", "llmURL": "", "llmModel": "", "llmKey": "", "assignments": list(users),
    }).id


def _rule(store, cid, *, delivery=True, enabled=True):
    return store.add_rule(
        connection_id=cid, project_id=1, project_title="Orders", kind="transition_metric",
        name="Slow", severity="URGENT", interval_secs=300, enabled=enabled,
        config=json.dumps({"fromStep": "A", "toStep": "B", "metric": "Avg Time",
                           "comparator": ">", "threshold": 7200}),
        delivery=json.dumps({"webpush": True} if delivery else {}), created_by="alice",
    )


def test_deliver_pushes_to_every_connection_subscriber(mods, monkeypatch):
    store, delivery, _ = mods
    cid = _conn(store, ["alice", "bob"])
    store.add_push_subscription("alice", "https://push/a", "pa", "aa")
    store.add_push_subscription("bob", "https://push/b", "pb", "ab")
    rule = _rule(store, cid)

    sent = []

    async def _fake_send(sub, body, **kw):
        sent.append((sub["endpoint"], body))

    monkeypatch.setattr("app.notifications.webpush.send", _fake_send)
    asyncio.run(delivery.deliver(rule, 9000.0))

    assert {e for e, _ in sent} == {"https://push/a", "https://push/b"}
    payload = json.loads(sent[0][1].decode())
    assert payload["ruleId"] == rule.id and "Slow" in payload["title"]


def test_deliver_removes_gone_subscriptions(mods, monkeypatch):
    store, delivery, _ = mods
    cid = _conn(store, ["alice"])
    store.add_push_subscription("alice", "https://push/dead", "p", "a")
    rule = _rule(store, cid)

    from app.notifications import webpush

    async def _fake_send(sub, body, **kw):
        raise webpush.PushGone(sub["endpoint"])

    monkeypatch.setattr("app.notifications.webpush.send", _fake_send)
    asyncio.run(delivery.deliver(rule, 9000.0))
    assert store.list_push_subscriptions("alice") == []  # dead endpoint pruned


def test_maybe_deliver_fires_only_on_the_triggered_edge(mods, monkeypatch):
    store, delivery, engine = mods
    cid = _conn(store, ["alice"])
    store.add_push_subscription("alice", "https://push/a", "p", "a")
    rule = _rule(store, cid)

    calls = {"n": 0}

    async def _fake_deliver(r, v):
        calls["n"] += 1

    monkeypatch.setattr(delivery, "deliver", _fake_deliver)

    # Not-triggered → triggered: fires.
    asyncio.run(engine._maybe_deliver(rule, None, True, 9000.0))
    assert calls["n"] == 1
    # Already triggered: does not fire again.
    asyncio.run(engine._maybe_deliver(rule, {"triggered": True}, True, 9000.0))
    assert calls["n"] == 1
    # Not triggered: does not fire.
    asyncio.run(engine._maybe_deliver(rule, None, False, 100.0))
    assert calls["n"] == 1


def _smtp_rule(store, cid, recipients):
    return store.add_rule(
        connection_id=cid, project_id=1, project_title="Orders", kind="transition_metric",
        name="Slow", severity="URGENT", interval_secs=300, enabled=True,
        config=json.dumps({"fromStep": "A", "toStep": "B", "metric": "Avg Time",
                           "comparator": ">", "threshold": 7200}),
        delivery=json.dumps({"smtp": {"recipients": recipients}}), created_by="alice",
    )


def test_smtp_uses_explicit_recipients(mods, monkeypatch):
    store, delivery, _ = mods
    store.set_smtp_settings({"host": "smtp.test", "from": "a@test", "security": "none"})
    cid = _conn(store, ["alice"])
    rule = _smtp_rule(store, cid, ["ops@team.com", "boss@team.com"])

    sent = {}

    def _fake_send(settings, recipients, subject, body):
        sent["to"] = recipients
        sent["subject"] = subject

    monkeypatch.setattr("app.notifications.smtp.send_email", _fake_send)
    asyncio.run(delivery.deliver(rule, 9000.0))
    assert sent["to"] == ["ops@team.com", "boss@team.com"] and "Slow" in sent["subject"]


def test_smtp_falls_back_to_connection_user_emails(mods, monkeypatch):
    store, delivery, _ = mods
    store.set_smtp_settings({"host": "smtp.test", "from": "a@test", "security": "none"})
    cid = _conn(store, ["alice", "bob"])
    for u, e in (("alice", "alice@team.com"), ("bob", "bob@team.com")):
        store._conn.execute("UPDATE users SET email = ? WHERE username = ?", (e, u))
    store._conn.commit()
    rule = _smtp_rule(store, cid, [])  # no explicit recipients → connection users

    sent = {}
    monkeypatch.setattr("app.notifications.smtp.send_email",
                        lambda s, r, sub, b: sent.update(to=r))
    asyncio.run(delivery.deliver(rule, 9000.0))
    assert set(sent["to"]) == {"alice@team.com", "bob@team.com"}


def test_smtp_skipped_when_not_configured(mods, monkeypatch):
    store, delivery, _ = mods
    cid = _conn(store, ["alice"])
    rule = _smtp_rule(store, cid, ["ops@team.com"])
    called = {"n": 0}
    monkeypatch.setattr("app.notifications.smtp.send_email",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    asyncio.run(delivery.deliver(rule, 9000.0))  # SMTP not configured → no send, no error
    assert called["n"] == 0


def test_maybe_deliver_skips_disabled_or_no_channel(mods, monkeypatch):
    store, delivery, engine = mods
    cid = _conn(store, ["alice"])
    calls = {"n": 0}

    async def _fake_deliver(r, v):
        calls["n"] += 1

    monkeypatch.setattr(delivery, "deliver", _fake_deliver)

    disabled = _rule(store, cid, enabled=False)
    asyncio.run(engine._maybe_deliver(disabled, None, True, 9000.0))
    no_channel = _rule(store, cid, delivery=False)
    asyncio.run(engine._maybe_deliver(no_channel, None, True, 9000.0))
    assert calls["n"] == 0
