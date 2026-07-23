"""Admin-interface API tests — the connection management endpoints.

Drives the real admin FastAPI app (`admin/server.py`) with an isolated security
store, verifying the admin guard, connection CRUD, per-user assignments, and the
connection-test endpoint. The test endpoint's database/LLM probes are stubbed so
no network access is needed.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def admin(tmp_path, monkeypatch):
    """A TestClient over the admin server, wired to a throwaway security store."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))

    # Reload config + security stack against the temp data dir.
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security

    import app.store.security as security_mod

    importlib.reload(security_mod)

    # Load admin/server.py fresh (it lives outside the app package; its module name
    # `server` collides with the GUI server, so drop any cached copy first).
    admin_dir = Path(config.PROJECT_ROOT) / "admin"
    sys.path.insert(0, str(admin_dir))
    for name in ("server", "pages"):
        sys.modules.pop(name, None)
    server = importlib.import_module("server")
    importlib.reload(server)

    return server, security_mod.store


def _login(server) -> TestClient:
    """A client signed in as the seeded administrator."""
    client = TestClient(server.app)
    resp = client.post(
        "/login",
        data={"username": "Administrator", "password": "Administrator"},
        follow_redirects=False,
    )
    assert resp.status_code in (200, 303)
    assert server.COOKIE in client.cookies
    return client


def _connection_body(**overrides) -> dict:
    body = {
        "name": "Prod Exasol",
        "comment": "primary",
        "host": "db.example.com",
        "port": 8563,
        "username": "svc",
        "schema": "MINING",
        "password": "s3cret",
        "useTLS": False,
        "llmURL": "https://llm.example.com/v1",
        "llmModel": "gpt-4o",
        "llmKey": "sk-abc",
        "assignments": [],
    }
    body.update(overrides)
    return body


# ── Auth guard ────────────────────────────────────────────────────────────────


def test_connection_endpoints_require_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.get("/api/connections").status_code == 401
    assert client.post("/api/connections", json=_connection_body()).status_code == 401


# ── CRUD ──────────────────────────────────────────────────────────────────────


def test_create_lists_and_hides_secrets(admin):
    server, store = admin
    client = _login(server)

    assert client.get("/api/connections").json() == []

    created = client.post("/api/connections", json=_connection_body()).json()
    assert created["hasPassword"] is True and created["hasLLMKey"] is True
    # The response never echoes the secret values.
    assert "s3cret" not in str(created) and "sk-abc" not in str(created)

    listed = client.get("/api/connections").json()
    assert [c["id"] for c in listed] == [created["id"]]
    assert listed[0]["name"] == "Prod Exasol"


def test_assignments_roundtrip_and_filtering(admin):
    server, store = admin
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    client = _login(server)

    conn = client.post(
        "/api/connections", json=_connection_body(assignments=["alice"])
    ).json()
    assert conn["assignments"] == ["alice"]

    # Reassign through the dedicated endpoint.
    resp = client.post(
        f"/api/connections/{conn['id']}/assignments", json={"assignments": ["bob"]}
    )
    assert resp.status_code == 200 and resp.json() == {"ok": True}

    # The store now reflects the new assignment for the backend to enforce.
    assert store.user_can_use(conn["id"], "bob") is True
    assert store.user_can_use(conn["id"], "alice") is False


def test_update_preserves_password_when_omitted(admin):
    server, store = admin
    client = _login(server)
    conn = client.post("/api/connections", json=_connection_body()).json()

    # Update without a password field — the stored secret must survive.
    body = _connection_body(id=conn["id"], name="Renamed")
    del body["password"]
    del body["llmKey"]
    updated = client.post("/api/connections", json=body).json()
    assert updated["name"] == "Renamed"
    assert updated["hasPassword"] is True and updated["hasLLMKey"] is True
    assert store.get_connection(conn["id"], with_secrets=True).password == "s3cret"


def test_delete_connection(admin):
    server, store = admin
    client = _login(server)
    conn = client.post("/api/connections", json=_connection_body()).json()

    resp = client.request("DELETE", f"/api/connections/{conn['id']}")
    assert resp.status_code == 200
    assert client.get("/api/connections").json() == []
    assert store.get_connection(conn["id"]) is None


# ── Test-connection endpoint ──────────────────────────────────────────────────


def test_connection_test_reports_db_and_llm(admin, monkeypatch):
    server, _ = admin
    client = _login(server)

    import app.db.manager as manager

    async def _fake_test_db(**kwargs):
        return None  # database reachable

    async def _fake_llm_reachable(llm):
        return True

    monkeypatch.setattr(manager, "test_db_connection", _fake_test_db)
    monkeypatch.setattr(manager, "check_llm_reachable", _fake_llm_reachable)
    monkeypatch.setattr(
        "app.services.llm.list_models",
        _make_async(["gpt-4o", "gpt-4o-mini"]),
    )

    resp = client.post(
        "/api/connections/test",
        json={
            "host": "db.example.com",
            "port": 8563,
            "username": "svc",
            "password": "s3cret",
            "schema": "MINING",
            "llmURL": "https://llm.example.com/v1",
            "llmKey": "sk-abc",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"dbError", "llmError", "llmModels"}
    assert body["dbError"] is None and body["llmError"] is None
    assert body["llmModels"] == ["gpt-4o", "gpt-4o-mini"]


def test_connection_test_surfaces_db_error(admin, monkeypatch):
    server, _ = admin
    client = _login(server)

    import app.db.manager as manager

    async def _fake_test_db(**kwargs):
        return "Connection refused"

    monkeypatch.setattr(manager, "test_db_connection", _fake_test_db)

    resp = client.post(
        "/api/connections/test",
        json={"host": "nope.invalid", "port": 8563, "username": "u", "password": "p"},
    )
    body = resp.json()
    assert body["dbError"] == "Connection refused"
    # No LLM URL supplied → LLM is not probed.
    assert body["llmError"] is None and body["llmModels"] == []


def _make_async(return_value):
    async def _coro(*args, **kwargs):
        return return_value

    return _coro


# ── LDAP / directory endpoints ────────────────────────────────────────────────


def test_ldap_config_roundtrip_hides_password(admin):
    server, store = admin
    client = _login(server)

    assert client.get("/api/ldap").json()["enabled"] is False

    saved = client.post(
        "/api/ldap",
        json={
            "enabled": True,
            "serverURI": "ldap://dir.example.com:389",
            "bindDN": "cn=svc,dc=example,dc=com",
            "bindPassword": "s3cret",
            "baseDN": "ou=people,dc=example,dc=com",
            "userFilter": "(uid={username})",
        },
    ).json()
    assert saved["enabled"] is True and saved["hasBindPassword"] is True
    assert "s3cret" not in str(saved)

    # Re-save without the password field keeps it (hasBindPassword stays true).
    again = client.post(
        "/api/ldap", json={"enabled": True, "serverURI": "ldap://dir.example.com:389"}
    ).json()
    assert again["hasBindPassword"] is True
    assert store.ldap_settings().bind_password == "s3cret"


def test_ldap_test_endpoint_uses_stub(admin, monkeypatch):
    server, _ = admin
    client = _login(server)

    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(
        ldap_auth,
        "test_settings",
        lambda settings, u, p: {"ok": True, "error": None, "userOk": bool(u and p)},
    )
    r = client.post(
        "/api/ldap/test",
        json={"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x",
              "testUsername": "alice", "testPassword": "pw"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "error": None, "userOk": True}


def test_ldap_endpoints_require_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.get("/api/ldap").status_code == 401
    assert client.post("/api/ldap", json={"enabled": True}).status_code == 401


# ── Admin panel login: admins only (local or LDAP-tagged) ─────────────────────


def test_admin_login_rejects_non_admin_local(admin):
    server, store = admin
    store.create_user("bob", "pw", is_admin=False)
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "bob", "password": "pw"}, follow_redirects=False)
    assert resp.status_code == 401
    assert server.COOKIE not in resp.cookies


def test_admin_login_accepts_ldap_tagged_admin(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    import app.services.ldap_auth as ldap_auth
    from app.services.ldap_auth import LdapUser

    monkeypatch.setattr(
        ldap_auth, "authenticate",
        lambda s, u, p: LdapUser(username="ldapadmin") if (u == "ldapadmin" and p == "dirpw") else None,
    )
    client = TestClient(server.app)
    # First attempt: JIT-provisioned as a plain user → not an admin → refused.
    r1 = client.post("/login", data={"username": "ldapadmin", "password": "dirpw"}, follow_redirects=False)
    assert r1.status_code == 401
    assert store.get_user("ldapadmin") is not None and store.get_user("ldapadmin").is_admin is False

    # A local admin tags them Admin → now they may enter the admin panel.
    store.set_admin("ldapadmin", True)
    r2 = client.post("/login", data={"username": "ldapadmin", "password": "dirpw"}, follow_redirects=False)
    assert r2.status_code == 303 and server.COOKIE in r2.cookies


def test_admin_login_rejects_ldap_non_admin(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    import app.services.ldap_auth as ldap_auth
    from app.services.ldap_auth import LdapUser

    monkeypatch.setattr(ldap_auth, "authenticate", lambda s, u, p: LdapUser(username="ldapuser"))
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "ldapuser", "password": "dirpw"}, follow_redirects=False)
    assert resp.status_code == 401
    assert server.COOKIE not in resp.cookies


def test_admin_login_wrong_ldap_password(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    store.provision_ldap_user("ldapadmin")
    store.set_admin("ldapadmin", True)
    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(ldap_auth, "authenticate", lambda s, u, p: None)  # directory rejects
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "ldapadmin", "password": "bad"}, follow_redirects=False)
    assert resp.status_code == 401
