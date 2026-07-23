"""Compute-backend connection API tests — per-user filtering and the connect gate.

Drives the real backend FastAPI app (`app.main`) with an isolated security store.
The GUI proxy injects a trusted ``X-PMW-User`` header after validating the session;
these tests supply that header directly and confirm the backend only exposes and
connects the connections assigned to that user. The actual Exasol connect is
stubbed so no database is needed.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """A TestClient over the compute backend, wired to a throwaway security store."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))

    # Reload the config + security stack, then the app modules that bind to them.
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security

    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.db.manager as manager

    importlib.reload(manager)
    import app.api.connections as connections_api

    importlib.reload(connections_api)
    import app.main as main

    importlib.reload(main)

    return main.app, security_mod.store, manager.db


def _make_conn(store, **overrides):
    data = {
        "name": "Prod",
        "host": "db.example.com",
        "port": 8563,
        "username": "svc",
        "schema": "MINING",
        "password": "s3cret",
        "llmURL": "https://llm.example.com/v1",
        "llmModel": "gpt-4o",
        "llmKey": "sk-abc",
        "assignments": ["alice"],
    }
    data.update(overrides)
    return store.upsert_connection(data)


# ── Listing / per-user filtering ──────────────────────────────────────────────


def test_list_returns_only_assigned_and_strips_secrets(backend):
    app, store, _ = backend
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])
    client = TestClient(app)

    alice = client.get("/api/connections", headers={"X-PMW-User": "alice"}).json()
    assert [c["id"] for c in alice] == [conn.id]
    # user_public exposes no secrets and no assignment list.
    entry = alice[0]
    assert entry["hasLLM"] is True and entry["llmURL"] == "https://llm.example.com/v1"
    assert "password" not in entry and "assignments" not in entry
    assert "s3cret" not in str(entry) and "sk-abc" not in str(entry)

    # bob has nothing assigned.
    assert client.get("/api/connections", headers={"X-PMW-User": "bob"}).json() == []


def test_list_without_user_header_returns_all(backend):
    app, store, _ = backend
    store.create_user("alice", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])
    client = TestClient(app)
    # No header ⇒ sign-in disabled ⇒ every connection is visible.
    listed = client.get("/api/connections").json()
    assert [c["id"] for c in listed] == [conn.id]


# ── Connect authorization gate ────────────────────────────────────────────────


def test_connect_forbidden_for_unassigned_user(backend):
    app, store, db = backend
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])
    client = TestClient(app)

    called = False

    async def _fake_connect(conn_def):
        nonlocal called
        called = True
        return None

    db.connect_connection = _fake_connect  # type: ignore[method-assign]

    resp = client.post(
        f"/api/connections/{conn.id}/connect", headers={"X-PMW-User": "bob"}
    )
    assert resp.status_code == 403
    assert called is False  # the gate short-circuits before any DB work


def test_connect_allowed_for_assigned_user(backend):
    app, store, db = backend
    store.create_user("alice", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])
    client = TestClient(app)

    received: dict = {}

    async def _fake_connect(conn_def):
        received["id"] = conn_def.id
        received["password"] = conn_def.password  # backend receives decrypted secret
        db.is_connected = True
        db.is_llm_reachable = True
        db.active_profile_id = conn_def.id
        return None

    db.connect_connection = _fake_connect  # type: ignore[method-assign]

    resp = client.post(
        f"/api/connections/{conn.id}/connect", headers={"X-PMW-User": "alice"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["isConnected"] is True
    assert body["activeProfileId"] == conn.id
    # The backend connects with the decrypted secret, resolved from the store.
    assert received == {"id": conn.id, "password": "s3cret"}


def test_connect_missing_connection_is_404(backend):
    app, store, db = backend
    client = TestClient(app)
    # No user header ⇒ open access passes the gate, but the id does not exist.
    resp = client.post("/api/connections/does-not-exist/connect")
    assert resp.status_code == 404
