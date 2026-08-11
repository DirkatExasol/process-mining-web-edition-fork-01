"""Admin-interface API tests — the connection management endpoints.

Drives the real admin FastAPI app (`admin/server.py`) with an isolated security
store, verifying the admin guard, connection CRUD, per-user assignments, and the
connection-test endpoint. The test endpoint's database/LLM probes are stubbed so
no network access is needed.
"""

from __future__ import annotations

import base64
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

    # Fresh log store bound to the temp data dir (log_events references the module,
    # so this reload is picked up everywhere).
    import app.store.logs as logs_mod

    importlib.reload(logs_mod)

    # Settings store + connection manager + backup service (the Backup tab uses
    # these) rebound to the temp data dir.
    import app.store.settings as settings_mod

    importlib.reload(settings_mod)
    import app.db.manager as manager_mod

    importlib.reload(manager_mod)
    import app.services.backup as backup_mod

    importlib.reload(backup_mod)

    # License verifier rebound to the temp data dir (App Control → License).
    import app.licensing as licensing_mod

    importlib.reload(licensing_mod)

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

    # Both the DB and the LLM server test are logged at INFO.
    conn_log = " ".join(
        e["message"].lower() for e in server.log_store.query(operation="connection")
    )
    assert "tested a database connection to db.example.com:8563 — ok" in conn_log
    llm_entries = server.log_store.query(operation="llm-test")
    assert any(
        e["severity"] == "INFO"
        and "tested an llm server at https://llm.example.com/v1 — ok (2 models)"
        in e["message"].lower()
        for e in llm_entries
    )


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


def test_login_get_inactivity_shows_notice(admin):
    server, _ = admin
    client = TestClient(server.app)
    # A plain /login shows no inactivity NOTICE (the one-time-strip script always ships,
    # so check for the notice text, not the bare word "inactivity").
    assert "You were signed out due to inactivity." not in client.get("/login").text
    body = client.get("/login?inactivity=1").text
    assert "You were signed out due to inactivity." in body


def test_admin_login_rejects_non_admin_local(admin):
    server, store = admin
    store.create_user("bob", "pw", is_admin=False)
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "bob", "password": "pw"}, follow_redirects=False)
    assert resp.status_code == 401
    assert server.COOKIE not in resp.cookies


def test_admin_login_accepts_ldap_tagged_admin(admin, monkeypatch):
    server, store = admin
    # Directory admin sign-in must be explicitly allowed for the admin interface.
    store.set_ldap_config(
        {"enabled": True, "adminLoginEnabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"}
    )
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


def test_admin_login_directory_blocked_unless_enabled(admin, monkeypatch):
    """With directory admin-login off (the default), even a promoted directory admin
    cannot sign in to the admin panel — only local accounts are accepted."""
    server, store = admin
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    store.provision_ldap_user("ldapadmin")
    store.set_admin("ldapadmin", True)
    import app.services.ldap_auth as ldap_auth
    from app.services.ldap_auth import LdapUser

    # The directory would authenticate them, but admin-login is not enabled.
    called = {"n": 0}

    def _auth(s, u, p):
        called["n"] += 1
        return LdapUser(username="ldapadmin")

    monkeypatch.setattr(ldap_auth, "authenticate", _auth)
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "ldapadmin", "password": "dirpw"}, follow_redirects=False)
    assert resp.status_code == 401 and server.COOKIE not in resp.cookies
    assert called["n"] == 0  # local-only path never consults the directory

    # Flip the switch on → the same promoted directory admin now gets in.
    store.set_ldap_config(
        {"enabled": True, "adminLoginEnabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"}
    )
    r2 = client.post("/login", data={"username": "ldapadmin", "password": "dirpw"}, follow_redirects=False)
    assert r2.status_code == 303 and server.COOKIE in r2.cookies


def test_admin_login_rejects_ldap_non_admin(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config(
        {"enabled": True, "adminLoginEnabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"}
    )
    import app.services.ldap_auth as ldap_auth
    from app.services.ldap_auth import LdapUser

    monkeypatch.setattr(ldap_auth, "authenticate", lambda s, u, p: LdapUser(username="ldapuser"))
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "ldapuser", "password": "dirpw"}, follow_redirects=False)
    assert resp.status_code == 401
    assert server.COOKIE not in resp.cookies


def test_admin_login_wrong_ldap_password(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config(
        {"enabled": True, "adminLoginEnabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"}
    )
    store.provision_ldap_user("ldapadmin")
    store.set_admin("ldapadmin", True)
    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(ldap_auth, "authenticate", lambda s, u, p: None)  # directory rejects
    client = TestClient(server.app)
    resp = client.post("/login", data={"username": "ldapadmin", "password": "bad"}, follow_redirects=False)
    assert resp.status_code == 401


def test_idle_timeout_endpoint(admin):
    server, store = admin
    client = _login(server)
    assert client.get("/api/session").json()["idleTimeoutMins"] == 0
    r = client.post("/api/access/idle-timeout", json={"minutes": 15})
    assert r.status_code == 200 and r.json()["idleTimeoutMins"] == 15
    assert store.idle_timeout_mins == 15
    # Negative clamps to 0 (disabled).
    client.post("/api/access/idle-timeout", json={"minutes": -3})
    assert store.idle_timeout_mins == 0


def test_power_endpoint_toggles_role(admin):
    server, store = admin
    client = _login(server)
    store.create_user("pat", "pw", is_admin=False)

    r = client.post("/api/users/pat/power", json={"isPower": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert store.get_user("pat").is_power is True
    # The users listing exposes the role for the admin UI badge/button.
    listed = {u["username"]: u for u in client.get("/api/users").json()}
    assert listed["pat"]["isPower"] is True

    assert client.post("/api/users/pat/power", json={"isPower": False}).status_code == 200
    assert store.get_user("pat").is_power is False


def test_power_endpoint_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.post("/api/users/pat/power", json={"isPower": True}).status_code == 401


def test_developer_endpoint_toggles_role(admin):
    server, store = admin
    client = _login(server)
    store.create_user("dev", "pw", is_admin=False)

    r = client.post("/api/users/dev/developer", json={"isDeveloper": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert store.get_user("dev").is_developer is True
    listed = {u["username"]: u for u in client.get("/api/users").json()}
    assert listed["dev"]["isDeveloper"] is True

    assert client.post("/api/users/dev/developer", json={"isDeveloper": False}).status_code == 200
    assert store.get_user("dev").is_developer is False


def test_developer_endpoint_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.post("/api/users/dev/developer", json={"isDeveloper": True}).status_code == 401


def test_integration_endpoints_toggle_and_require_admin(admin):
    server, store = admin
    # Unauthenticated → gated.
    anon = TestClient(server.app)
    assert anon.get("/api/integration").status_code == 401
    assert anon.post("/api/integration/enabled", json={"enabled": False}).status_code == 401

    client = _login(server)
    status = client.get("/api/integration").json()
    assert status["enabled"] is True and status["httpPort"] and status["httpsPort"]

    r = client.post("/api/integration/enabled", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert store.integration_enabled is False
    assert client.get("/api/integration").json()["enabled"] is False
    client.post("/api/integration/enabled", json={"enabled": True})
    assert store.integration_enabled is True


def test_provision_schema_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    resp = client.post(
        "/api/connections/provision-schema", json={"host": "db", "schema": "PM"}
    )
    assert resp.status_code == 401


def test_provision_schema_admin_invokes_provisioner(admin, monkeypatch):
    server, _ = admin
    client = _login(server)
    import app.db.schema_ddl as ddl

    seen: dict = {}

    async def _fake(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "error": None, "created": ["schema PM"]}

    monkeypatch.setattr(ddl, "provision_process_mining_schema", _fake)
    resp = client.post(
        "/api/connections/provision-schema",
        json={"host": "db", "username": "u", "password": "pw", "schema": "PM"},
    )
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert seen["schema"] == "PM"


# ── Directory availability indicator (login screen) ───────────────────────────


def test_admin_directory_status_unconfigured(admin):
    server, _ = admin
    client = TestClient(server.app)
    # Unauthenticated endpoint; nothing configured ⇒ the login screen shows no LED.
    assert client.get("/api/directory-status").json() == {
        "configured": False,
        "available": False,
    }


def test_admin_directory_status_available_when_reachable(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(ldap_auth, "test_settings", lambda *a, **k: {"ok": True})
    client = TestClient(server.app)
    assert client.get("/api/directory-status").json() == {
        "configured": True,
        "available": True,
    }


def test_admin_directory_status_unavailable_on_probe_failure(admin, monkeypatch):
    server, store = admin
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    import app.services.ldap_auth as ldap_auth

    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ldap_auth, "test_settings", _boom)
    client = TestClient(server.app)
    assert client.get("/api/directory-status").json() == {
        "configured": True,
        "available": False,
    }


def test_admin_idle_timeout_endpoint_and_sliding_session(admin):
    server, store = admin
    client = _login(server)

    assert client.get("/api/session").json()["adminIdleTimeoutMins"] == 0
    r = client.post("/api/access/admin-idle-timeout", json={"minutes": 20})
    assert r.status_code == 200 and r.json()["adminIdleTimeoutMins"] == 20
    assert store.admin_idle_timeout_mins == 20
    # It is separate from the main app's idle timeout.
    assert store.idle_timeout_mins == 0

    # Polling the session re-issues the cookie (slides the idle window).
    resp = client.get("/api/session")
    assert server.COOKIE in resp.cookies

    client.post("/api/access/admin-idle-timeout", json={"minutes": -5})  # clamps
    assert store.admin_idle_timeout_mins == 0


# ── Logging ───────────────────────────────────────────────────────────────────


def test_logs_endpoints_capture_and_filter(admin):
    server, _ = admin
    client = _login(server)  # a successful admin sign-in → a USAGE 'login' entry

    body = client.get("/api/logs?level=DEBUG&limit=100").json()
    assert body["config"]["levels"] == ["INFO", "USAGE", "WARN", "ERROR", "DEBUG"]
    assert body["config"]["level"] == "ERROR"  # default
    ops = {e["operation"] for e in body["entries"]}
    msgs = " ".join(e["message"] for e in body["entries"])
    assert "login" in ops and "signed in" in msgs
    # Every entry carries the format fields.
    top = body["entries"][0]
    assert set(top) >= {"date", "time", "severity", "clientIp", "user", "operation", "message"}

    # Config round-trips (level + max file size).
    r = client.post("/api/logs/config", json={"level": "DEBUG", "maxBytes": 250000})
    assert r.status_code == 200 and r.json()["config"]["level"] == "DEBUG"

    # Regex search filters the message.
    hits = client.get("/api/logs?search=signed%20in&limit=100").json()["entries"]
    assert hits and all("signed in" in e["message"].lower() for e in hits)

    # Severity filter.
    login_only = client.get("/api/logs?operation=login&limit=100").json()["entries"]
    assert all(e["operation"] == "login" for e in login_only)

    # Download returns the DATE -- TIME -- ... format.
    dl = client.get("/api/logs/download")
    assert dl.status_code == 200 and " -- " in dl.text

    # Clear empties the live log.
    assert client.post("/api/logs/clear").status_code == 200


def test_logs_are_paginated_and_search_spans_all_pages(admin):
    server, _ = admin
    client = _login(server)
    # Seed at INFO/ERROR (recorded at the default level); the DEBUG request-logs the
    # /api/logs calls themselves emit are NOT recorded, so the window stays stable
    # between page fetches.
    for i in range(60):
        server.log_store.record("INFO", f"seed {i:02d}", operation="page")
    server.log_store.record("ERROR", "the lone needle", operation="error")

    # Page 1 of 25 → 25 rows, but 'total' reflects the whole (filtered) log.
    first = client.get("/api/logs?perPage=25&page=1").json()
    assert first["perPage"] == 25 and first["page"] == 1
    assert len(first["entries"]) == 25
    total = first["total"]
    assert total >= 61 and first["pages"] == (total + 24) // 25

    # A middle and last page slice the same set without overlap.
    p2 = client.get("/api/logs?perPage=25&page=2").json()
    assert len(p2["entries"]) == 25
    ids1 = {(e["date"], e["time"], e["message"]) for e in first["entries"]}
    ids2 = {(e["date"], e["time"], e["message"]) for e in p2["entries"]}
    assert ids1.isdisjoint(ids2)

    # An out-of-range page is clamped to the last page.
    clamped = client.get("/api/logs?perPage=25&page=999").json()
    assert clamped["page"] == clamped["pages"]

    # An invalid perPage falls back to 25.
    assert client.get("/api/logs?perPage=999").json()["perPage"] == 25

    # Search runs over ALL pages, not just the current page: the needle is found
    # even though it is not on page 1 of the unfiltered view.
    hit = client.get("/api/logs?search=lone%20needle&perPage=10&page=1").json()
    assert hit["total"] == 1 and len(hit["entries"]) == 1
    assert hit["entries"][0]["message"] == "the lone needle"


def test_logs_endpoints_require_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.get("/api/logs").status_code == 401
    assert client.post("/api/logs/config", json={"level": "INFO"}).status_code == 401
    assert client.get("/api/logs/download").status_code == 401


def test_backup_export_inspect_restore_roundtrip(admin):
    server, _ = admin
    client = _login(server)  # authenticated admin

    export = client.post("/api/backup/export", json={"includeUsername": True})
    assert export.status_code == 200
    assert "attachment" in export.headers.get("content-disposition", "")

    content = base64.b64encode(export.content).decode("ascii")
    summary = client.post("/api/backup/inspect", json={"content": content}).json()
    assert "createdAt" in summary and "connectionCount" in summary

    restored = client.post(
        "/api/backup/restore",
        json={"content": content, "options": {"appSettings": True}},
    )
    assert restored.status_code == 200 and restored.json()["ok"] is True


def test_backup_endpoints_require_admin(admin):
    server, _ = admin
    client = TestClient(server.app)  # no session
    assert client.post("/api/backup/export", json={}).status_code == 401
    assert client.post("/api/backup/inspect", json={"content": ""}).status_code == 401
    assert client.post("/api/backup/restore", json={"content": ""}).status_code == 401


def test_display_timezone_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)  # no session
    assert client.post("/api/access/timezone", json={"timezone": "UTC"}).status_code == 401


def test_display_timezone_set_validates_and_applies(admin):
    import app.store.logs as logs_mod

    server, store = admin
    client = _login(server)
    assert client.get("/api/session").json()["displayTimezone"] == ""  # default server-local

    # An unknown zone is rejected.
    r = client.post("/api/access/timezone", json={"timezone": "Not/AZone"})
    assert r.status_code == 400 and "timezone" in r.json()["detail"].lower()

    # A valid zone is stored, surfaced in the session, and applied to the log store.
    r = client.post("/api/access/timezone", json={"timezone": "Europe/Berlin"})
    assert r.status_code == 200 and r.json()["displayTimezone"] == "Europe/Berlin"
    assert client.get("/api/session").json()["displayTimezone"] == "Europe/Berlin"
    assert store.display_timezone == "Europe/Berlin"
    assert logs_mod._display_tz is not None  # log rendering now uses the zone

    # Empty clears back to server-local.
    assert client.post("/api/access/timezone", json={"timezone": ""}).json()[
        "displayTimezone"
    ] == ""


def test_scheduler_lifespan_starts_and_stops_cleanly(admin):
    # Entering the TestClient context runs the admin app's lifespan — this creates
    # the backup-scheduler task on startup and cancels it on shutdown. A clean
    # enter/exit proves the wiring (and, with a disabled default schedule, that the
    # first tick writes nothing).
    server, _ = admin
    with TestClient(server.app) as client:
        assert client.get("/login").status_code == 200
    assert not list(server.BACKUPS_DIR.glob("pmw-backup-*.json"))


def test_backup_schedule_endpoints_require_admin(admin):
    server, _ = admin
    client = TestClient(server.app)  # no session
    assert client.get("/api/backup/schedule").status_code == 401
    assert client.post(
        "/api/backup/schedule", json={"enabled": False, "cron": "0 2 * * *"}
    ).status_code == 401
    assert client.post("/api/backup/run-now").status_code == 401


def test_backup_schedule_get_set_and_validation(admin):
    server, _ = admin
    client = _login(server)
    s = client.get("/api/backup/schedule").json()
    assert s["enabled"] is False and s["hasPassword"] is False and s["cron"] == "0 2 * * *"

    # Enabling without a password is refused.
    r = client.post("/api/backup/schedule", json={"enabled": True, "cron": "0 2 * * *"})
    assert r.status_code == 400 and "password" in r.json()["detail"].lower()
    # An invalid cron is refused.
    r = client.post("/api/backup/schedule", json={"enabled": False, "cron": "99 2 * * *"})
    assert r.status_code == 400 and "invalid" in r.json()["detail"].lower()

    # Valid save with a password; the password is never echoed back.
    r = client.post("/api/backup/schedule", json={
        "enabled": True, "cron": "30 3 * * 1", "retention": 5, "password": "pw-123",
    })
    assert r.status_code == 200
    s = r.json()
    assert s["enabled"] and s["cron"] == "30 3 * * 1" and s["retention"] == 5
    assert s["hasPassword"] is True and "pw-123" not in str(s)
    # Omitting the password on a later save keeps it.
    r = client.post("/api/backup/schedule", json={"enabled": False, "cron": "30 3 * * 1"})
    assert r.json()["hasPassword"] is True


def test_backup_run_now_writes_encrypted_file_and_prunes(admin):
    import json as _json

    import app.services.backup as backup_service

    server, _ = admin
    client = _login(server)
    # No password yet → refused.
    assert client.post("/api/backup/run-now").status_code == 400
    # Configure a password + a small retention.
    client.post("/api/backup/schedule", json={
        "enabled": True, "cron": "0 2 * * *", "retention": 2, "password": "pw-xyz",
    })
    for _ in range(3):
        r = client.post("/api/backup/run-now")
        assert r.status_code == 200 and r.json()["ok"] is True and r.json()["file"]

    # Retention 2 keeps only the newest two files on disk.
    on_disk = sorted(server.BACKUPS_DIR.glob("pmw-backup-*.json"))
    assert len(on_disk) == 2
    # The written file is a valid encrypted backup, decryptable with the password.
    data = on_disk[-1].read_bytes()
    assert backup_service.is_encrypted(data)
    payload = _json.loads(backup_service.decrypt(data, "pw-xyz"))
    assert "version" in payload
    # The last run is recorded in the schedule status; "at" is UTC-aware ISO so the
    # admin UI can render it in the configured display timezone.
    status = client.get("/api/backup/schedule").json()["status"]
    assert status["ok"] is True and status["at"].endswith("+00:00")


def test_export_download_reuses_stored_backup_password(admin):
    """The unified Backup card shares one password: a download with a blank field
    reuses the stored automatic-backup password (useStoredPassword)."""
    import json as _json

    import app.services.backup as backup_service

    server, _ = admin
    client = _login(server)
    client.post("/api/backup/schedule", json={
        "enabled": False, "cron": "0 2 * * *", "password": "stored-pw",
    })
    # Blank password + useStoredPassword → encrypted with the stored password.
    r = client.post("/api/backup/export", json={"password": "", "useStoredPassword": True})
    assert r.status_code == 200 and backup_service.is_encrypted(r.content)
    assert "version" in _json.loads(backup_service.decrypt(r.content, "stored-pw"))
    # Without the flag, a blank password still yields an unencrypted file (unchanged).
    r2 = client.post("/api/backup/export", json={"password": ""})
    assert not backup_service.is_encrypted(r2.content)


def test_run_now_accepts_a_typed_password_when_none_stored(admin):
    server, _ = admin
    client = _login(server)
    # No stored password, but a typed one lets a manual server backup run.
    r = client.post("/api/backup/run-now", json={"password": "typed-pw"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert list(server.BACKUPS_DIR.glob("pmw-backup-*.json"))


def test_encrypted_backup_inspect_without_password_is_400_not_401(admin):
    """A 401 makes the admin fetch helper redirect to /login (the 'jumps to App
    Control / looks like a refresh' bug); the encrypted-backup case must be 400."""
    server, _ = admin
    client = _login(server)

    enc = client.post("/api/backup/export", json={"password": "pw123"})
    content = base64.b64encode(enc.content).decode("ascii")

    missing = client.post("/api/backup/inspect", json={"content": content})
    assert missing.status_code == 400  # NOT 401
    assert "encrypted" in missing.json()["detail"].lower()

    wrong = client.post("/api/backup/inspect", json={"content": content, "password": "nope"})
    assert wrong.status_code == 400  # NOT 401

    ok = client.post("/api/backup/inspect", json={"content": content, "password": "pw123"})
    assert ok.status_code == 200


def test_backup_upload_size_is_capped(admin, monkeypatch):
    server, _ = admin
    monkeypatch.setattr(server, "_MAX_BACKUP_B64", 100)
    client = _login(server)
    resp = client.post("/api/backup/inspect", json={"content": "A" * 101})
    assert resp.status_code == 413


def test_backup_actions_are_logged(admin):
    server, _ = admin
    client = _login(server)

    export = client.post("/api/backup/export", json={"includeUsername": True})
    content = base64.b64encode(export.content).decode("ascii")
    client.post("/api/backup/inspect", json={"content": content})
    client.post(
        "/api/backup/restore",
        json={"content": content, "options": {"appSettings": True}},
    )
    # A failed decode (encrypted, no password) must be logged too.
    enc = base64.b64encode(
        client.post("/api/backup/export", json={"password": "pw"}).content
    ).decode("ascii")
    assert client.post("/api/backup/inspect", json={"content": enc}).status_code == 400

    entries = server.log_store.query(operation="backup", limit=50)
    joined = " ".join(e["message"].lower() for e in entries)
    assert "exported a settings backup" in joined
    assert "inspected a backup file" in joined
    assert "restored a settings backup" in joined
    assert "inspect failed" in joined  # the failure is recorded
    # Every one carries the backup operation AND the BACKUP/RESTORE tag, so the whole
    # custody trail of a backup file — export, inspect, restore and their failures —
    # is reachable from the tag filter alone, at any severity.
    assert entries and all(e["operation"] == "backup" for e in entries)
    assert all(e["tag"] == "BACKUP/RESTORE" for e in entries)
    tagged = server.log_store.query(tag="BACKUP/RESTORE", limit=50)
    assert len(tagged) == len(entries)
    assert {"USAGE", "WARN"} & {e["severity"] for e in tagged}


def test_max_failed_logins_config_roundtrip(admin):
    server, store = admin
    client = _login(server)
    # Secure-by-default: unset → 3 (not 0/off).
    assert client.get("/api/session").json()["maxFailedLogins"] == 3
    resp = client.post("/api/access/max-failed-logins", json={"count": 5})
    assert resp.status_code == 200 and resp.json()["maxFailedLogins"] == 5
    assert store.max_failed_logins == 5
    assert client.get("/api/session").json()["maxFailedLogins"] == 5
    # An explicit 0 still turns the lockout off (admin override).
    assert client.post("/api/access/max-failed-logins", json={"count": 0}).json()[
        "maxFailedLogins"
    ] == 0
    assert store.max_failed_logins == 0


def test_admin_responses_carry_security_headers(admin):
    server, _ = admin
    r = TestClient(server.app).get("/login")
    assert r.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in (r.headers.get("content-security-policy") or "")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "no-referrer"


def test_admin_rejects_foreign_audience_cookie(admin):
    """An app session cookie (audience "app") must not authenticate the admin UI,
    even though both interfaces sign tokens with the same key."""
    import json as _json

    server, store = admin
    epoch = store.session_epoch("Administrator")
    forged = server.sign_session(
        _json.dumps({"u": "Administrator", "e": epoch, "a": "app"}).encode("utf-8")
    )
    client = TestClient(server.app)
    client.cookies.set(server.COOKIE, forged)
    assert client.get("/api/session").status_code == 401
    # A correctly-scoped admin token is accepted (control).
    client.cookies.set(server.COOKIE, server._issue_session("Administrator"))
    assert client.get("/api/session").status_code == 200


def test_admin_login_is_ip_throttled(admin):
    """After too many failures from one host, further attempts are blocked with a
    429 — even a correct password — independent of per-account lockout."""
    server, store = admin
    store.set_max_failed_logins(0)  # isolate the per-IP throttle from account lockout
    client = TestClient(server.app)
    for _ in range(server._LOGIN_IP_MAX):
        r = client.post(
            "/login",
            data={"username": "Administrator", "password": "nope"},
            follow_redirects=False,
        )
        assert r.status_code == 401
    blocked = client.post(
        "/login",
        data={"username": "Administrator", "password": "Administrator"},
        follow_redirects=False,
    )
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}


def test_admin_login_throttle_clears_on_success(admin):
    server, store = admin
    store.set_max_failed_logins(0)
    client = TestClient(server.app)
    for _ in range(server._LOGIN_IP_MAX - 1):  # below the threshold
        client.post(
            "/login",
            data={"username": "Administrator", "password": "nope"},
            follow_redirects=False,
        )
    ok = client.post(
        "/login",
        data={"username": "Administrator", "password": "Administrator"},
        follow_redirects=False,
    )
    assert ok.status_code in (200, 303)  # success resets the counter
    # A fresh run of failures is needed to throttle again (counter was cleared).
    for _ in range(server._LOGIN_IP_MAX - 1):
        r = client.post(
            "/login",
            data={"username": "Administrator", "password": "nope"},
            follow_redirects=False,
        )
        assert r.status_code == 401  # not throttled yet


def test_admin_login_throttle_map_is_bounded(admin):
    """A distributed flood of one-shot IPs can't grow the throttle map without bound."""
    server, _ = admin
    server._login_ip_failures.clear()
    cap = server._LOGIN_IP_MAX_TRACKED
    for i in range(cap + 200):
        server._record_login_failure_ip(f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}")
    assert len(server._login_ip_failures) <= cap


def test_max_failed_logins_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert (
        client.post("/api/access/max-failed-logins", json={"count": 5}).status_code
        == 401
    )


def test_admin_login_shows_lockout_message(admin):
    """A locked (non-built-in) admin gets the lockout message on the login screen."""
    server, store = admin
    store.create_user("ops", "opspw", is_admin=True)
    store.set_max_failed_logins(1)
    store.record_login_failure("ops")  # threshold 1 → locked
    assert store.get_user("ops").is_enabled is False
    client = TestClient(server.app)
    # Even the correct password is refused, and the panel explains why.
    r = client.post(
        "/login",
        data={"username": "ops", "password": "opspw"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "locked" in r.text.lower()


# ── License (App Control → License) ──────────────────────────────────────────


def _sign_license(server, license_obj: dict) -> str:
    """Sign a license with an ephemeral key and patch the verifier to accept it.
    Returns the base64 the upload endpoint expects."""
    import base64 as _b64
    import json as _json

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    server.licensing._PUBLIC_KEY = priv.public_key()
    sig = priv.sign(server.licensing._canonical(license_obj))
    doc = {"license": license_obj, "signature": sig.hex()}
    return _b64.b64encode(_json.dumps(doc).encode()).decode()


def _future_license() -> dict:
    from datetime import date, timedelta

    return {
        "licensee": "Acme GmbH",
        "issued": "2026-01-01",
        "expires": (date.today() + timedelta(days=30)).isoformat(),
        "version": 1,
    }


def test_license_upload_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.get("/api/license").status_code == 401
    assert client.post("/api/license", json={"content": ""}).status_code == 401


def test_license_upload_installs_valid(admin):
    server, _ = admin
    client = _login(server)
    content = _sign_license(server, _future_license())
    r = client.post("/api/license", json={"content": content})
    assert r.status_code == 200, r.text
    assert r.json()["license"]["state"] == "valid"
    # Session now reports the installed license.
    assert client.get("/api/session").json()["license"]["state"] == "valid"


def test_license_upload_rejects_forged(admin):
    server, _ = admin
    client = _login(server)
    content = _sign_license(server, _future_license())
    # Corrupt the base64'd document so the signature no longer matches.
    import base64
    import json

    doc = json.loads(base64.b64decode(content))
    doc["license"]["licensee"] = "Evil Corp"
    tampered = base64.b64encode(json.dumps(doc).encode()).decode()
    r = client.post("/api/license", json={"content": tampered})
    assert r.status_code == 400
    assert "signature" in r.json()["detail"].lower()
    # Nothing was stored.
    assert client.get("/api/session").json()["license"]["state"] == "missing"


def test_license_upload_rejects_bad_base64(admin):
    server, _ = admin
    client = _login(server)
    r = client.post("/api/license", json={"content": "not!base64!"})
    assert r.status_code == 400


def test_license_delete_removes_installed(admin):
    server, _ = admin
    client = _login(server)
    # Install one, then delete it.
    content = _sign_license(server, _future_license())
    assert client.post("/api/license", json={"content": content}).status_code == 200
    assert client.get("/api/session").json()["license"]["state"] == "valid"

    r = client.request("DELETE", "/api/license")
    assert r.status_code == 200
    assert r.json()["removed"] is True
    assert client.get("/api/session").json()["license"]["state"] == "missing"

    # Deleting again is a no-op, not an error.
    r2 = client.request("DELETE", "/api/license")
    assert r2.status_code == 200 and r2.json()["removed"] is False


def test_license_delete_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.request("DELETE", "/api/license").status_code == 401


def test_logout_invalidates_captured_token(admin):
    """A token captured before logout must be rejected afterwards — server-side
    invalidation, not merely clearing the client's cookie."""
    server, _ = admin
    client = _login(server)
    token = client.cookies.get(server.COOKIE)
    assert token

    def _replay():
        c = TestClient(server.app)
        c.cookies.set(server.COOKIE, token)
        return c.get("/api/session").status_code

    assert _replay() == 200  # valid before logout
    client.post("/logout", follow_redirects=False)  # bumps the session epoch
    assert _replay() == 401  # the same captured token no longer authenticates


# ── Customize (login page background) ─────────────────────────────────────────


def test_customize_login_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.get("/api/customize/login").status_code == 401
    assert (
        client.post("/api/customize/login", json={"type": "default"}).status_code
        == 401
    )


def test_customize_login_roundtrip(admin):
    server, store = admin
    client = _login(server)

    assert client.get("/api/customize/login").json()["type"] == "default"

    resp = client.post(
        "/api/customize/login", json={"type": "color", "color": "#0a84ff"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"type": "color", "color": "#0a84ff", "image": ""}
    assert store.login_appearance()["type"] == "color"


def test_customize_login_rejects_bad_color(admin):
    server, _ = admin
    client = _login(server)
    resp = client.post("/api/customize/login", json={"type": "color", "color": "nope"})
    assert resp.status_code == 400


def test_customize_login_accepts_a_3mb_image(admin):
    # base64 inflates a 3 MB source image (the UI's file-size limit) to ~4.19 MB of
    # characters; the server cap must clear that, or images the UI accepts fail to
    # save (regression: the cap was 4.0 MB, rejecting anything over a ~2.86 MB file).
    import base64
    server, store = admin
    client = _login(server)
    # data URI whose length matches a 3 MB (3 * 1024 * 1024 B) source image.
    body = b"\x89" * (3 * 1024 * 1024)
    uri = "data:image/png;base64," + base64.b64encode(body).decode()
    assert len(uri) > 4_000_000  # would have failed the old cap
    resp = client.post("/api/customize/login", json={"type": "image", "image": uri})
    assert resp.status_code == 200
    assert store.login_appearance()["type"] == "image"


def test_customize_login_rejects_an_oversized_image(admin):
    import base64
    server, _ = admin
    client = _login(server)
    body = b"\x89" * (4 * 1024 * 1024)  # ~5.6 MB of base64 → over the cap
    uri = "data:image/png;base64," + base64.b64encode(body).decode()
    resp = client.post("/api/customize/login", json={"type": "image", "image": uri})
    assert resp.status_code == 400 and "too large" in resp.json()["detail"].lower()


def test_login_page_uses_custom_background(admin):
    server, _ = admin
    client = _login(server)
    client.post("/api/customize/login", json={"type": "color", "color": "#0a84ff"})
    anon = TestClient(server.app)  # the sign-in page is served pre-auth
    html = anon.get("/login").text
    assert "background: #0a84ff;" in html


def test_customize_login_is_logged_as_info(admin):
    server, _ = admin
    client = _login(server)
    client.post("/api/customize/login", json={"type": "color", "color": "#0a84ff"})
    entries = server.log_store.query(operation="customize", limit=10)
    assert any(
        e["severity"] == "INFO"
        and "login page background" in e["message"].lower()
        and "0a84ff" in e["message"]
        for e in entries
    )


def test_ldap_cert_and_connection_actions_are_logged(admin, monkeypatch):
    server, _ = admin
    client = _login(server)

    # ── LDAP: configure + test (server-only and account) ──────────────────────
    client.post("/api/ldap", json={"enabled": True, "serverURI": "ldap://dir:389"})
    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(
        ldap_auth,
        "test_settings",
        lambda s, u, p: {"ok": True, "error": None, "userOk": bool(u and p)},
    )
    client.post("/api/ldap/test", json={"serverURI": "ldap://dir:389", "baseDN": "dc=x"})
    client.post(
        "/api/ldap/test",
        json={
            "serverURI": "ldap://dir:389",
            "baseDN": "dc=x",
            "testUsername": "alice",
            "testPassword": "pw",
        },
    )
    ldap_entries = server.log_store.query(operation="ldap", limit=50)
    ldap_log = " ".join(e["message"].lower() for e in ldap_entries)
    assert "saved the directory (ldap) configuration" in ldap_log
    assert "tested the directory server connection" in ldap_log
    assert "tested a directory account login for 'alice'" in ldap_log
    assert all(e["severity"] == "INFO" for e in ldap_entries)

    # ── Certificate actions: generate → activate → delete ─────────────────────
    cert = client.post(
        "/api/certs/generate",
        json={"name": "Test Cert", "commonName": "localhost", "activate": True},
    ).json()
    client.post(f"/api/certs/{cert['id']}/activate")
    client.delete(f"/api/certs/{cert['id']}")
    tls_entries = server.log_store.query(operation="tls", limit=50)
    tls_log = " ".join(e["message"].lower() for e in tls_entries)
    assert "generated tls certificate 'test cert'" in tls_log
    assert "activated tls certificate" in tls_log
    assert any(
        e["severity"] == "WARN" and "deleted tls certificate" in e["message"].lower()
        for e in tls_entries
    )

    # ── Database connection: create → assign → delete ─────────────────────────
    conn = client.post("/api/connections", json=_connection_body()).json()
    client.post(f"/api/connections/{conn['id']}/assignments", json={"assignments": []})
    client.delete(f"/api/connections/{conn['id']}")
    conn_entries = server.log_store.query(operation="connection", limit=50)
    conn_log = " ".join(e["message"].lower() for e in conn_entries)
    assert "created database connection" in conn_log
    assert "set the user assignments" in conn_log
    assert any(
        e["severity"] == "WARN" and "deleted database connection" in e["message"].lower()
        for e in conn_entries
    )


# ── Pre-materialised transitions: toggle, rebuild, external token ─────────────


def test_materialized_toggle_persists(admin):
    server, store = admin
    client = _login(server)

    created = client.post(
        "/api/connections", json=_connection_body(useMaterializedTransitions=True)
    ).json()
    assert created["useMaterializedTransitions"] is True
    assert store.get_connection(created["id"]).use_materialized_transitions is True

    body = _connection_body(id=created["id"], useMaterializedTransitions=False)
    del body["password"]
    del body["llmKey"]
    updated = client.post("/api/connections", json=body).json()
    assert updated["useMaterializedTransitions"] is False


def test_rebuild_requires_admin_or_token(admin, monkeypatch):
    server, store = admin
    client = _login(server)
    conn = client.post("/api/connections", json=_connection_body()).json()

    async def _stub_rebuild(**kwargs):
        return {"ok": True, "error": None, "rows": 7, "built_at": "2026-07-28T00:00:00+00:00"}

    monkeypatch.setattr("app.db.schema_ddl.rebuild_materialized_transitions", _stub_rebuild)

    # No auth at all → 401.
    anon = TestClient(server.app)
    assert anon.post(f"/api/connections/{conn['id']}/rebuild-transitions").status_code == 401

    # Admin session → runs, echoes the result, and records the status.
    resp = client.post(f"/api/connections/{conn['id']}/rebuild-transitions")
    assert resp.status_code == 200 and resp.json()["rows"] == 7
    assert store.materialization_status(conn["id"])["rows"] == 7

    # Unknown connection → 404.
    assert client.post("/api/connections/nope/rebuild-transitions").status_code == 404

    # It is logged under the materialize operation.
    mat_log = " ".join(
        e["message"].lower() for e in server.log_store.query(operation="materialize")
    )
    assert "rebuilt materialised transitions" in mat_log


def test_rebuild_bearer_token_is_per_connection(admin, monkeypatch):
    server, store = admin
    client = _login(server)
    conn = client.post("/api/connections", json=_connection_body()).json()
    other = client.post("/api/connections", json=_connection_body(name="Other")).json()

    async def _stub_rebuild(**kwargs):
        return {"ok": True, "error": None, "rows": 3, "built_at": "2026-07-28T00:00:00+00:00"}

    monkeypatch.setattr("app.db.schema_ddl.rebuild_materialized_transitions", _stub_rebuild)

    cid = conn["id"]
    token = client.post(f"/api/connections/{cid}/rebuild-token").json()["token"]
    # The token flag surfaces on the connection listing.
    listing = {c["id"]: c for c in client.get("/api/connections").json()}
    assert listing[cid]["rebuildTokenSet"] is True

    ext = TestClient(server.app)  # no admin cookie — a scheduler with only the token
    ok = ext.post(
        f"/api/connections/{cid}/rebuild-transitions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200 and ok.json()["rows"] == 3

    # A wrong token is rejected.
    assert ext.post(
        f"/api/connections/{cid}/rebuild-transitions",
        headers={"Authorization": "Bearer not-the-token"},
    ).status_code == 401

    # Scoped: the token cannot rebuild a DIFFERENT connection.
    assert ext.post(
        f"/api/connections/{other['id']}/rebuild-transitions",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 401

    # After rotation the old token stops working.
    client.post(f"/api/connections/{cid}/rebuild-token")
    assert ext.post(
        f"/api/connections/{cid}/rebuild-transitions",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 401

    # Revoke clears it.
    client.request("DELETE", f"/api/connections/{cid}/rebuild-token")
    assert {c["id"]: c for c in client.get("/api/connections").json()}[cid]["rebuildTokenSet"] is False


def test_token_rebuild_is_throttled_but_admin_is_not(admin, monkeypatch):
    server, _ = admin
    client = _login(server)
    conn = client.post("/api/connections", json=_connection_body()).json()
    cid = conn["id"]

    async def _stub(**kwargs):
        return {"ok": True, "error": None, "rows": 1, "built_at": "2026-07-28T00:00:00+00:00"}

    monkeypatch.setattr("app.db.schema_ddl.rebuild_materialized_transitions", _stub)
    token = client.post(f"/api/connections/{cid}/rebuild-token").json()["token"]
    ext = TestClient(server.app)
    hdr = {"Authorization": f"Bearer {token}"}

    assert ext.post(f"/api/connections/{cid}/rebuild-transitions", headers=hdr).status_code == 200
    # A second token call right away is throttled…
    assert ext.post(f"/api/connections/{cid}/rebuild-transitions", headers=hdr).status_code == 429
    # …but an admin session may still force a rebuild.
    assert client.post(f"/api/connections/{cid}/rebuild-transitions").status_code == 200


def test_rebuild_rejects_a_concurrent_run(admin):
    server, _ = admin
    client = _login(server)
    conn = client.post("/api/connections", json=_connection_body()).json()
    cid = conn["id"]
    server._rebuild_in_progress.add(cid)  # simulate a rebuild already running
    try:
        assert client.post(f"/api/connections/{cid}/rebuild-transitions").status_code == 409
    finally:
        server._rebuild_in_progress.discard(cid)


def test_rebuild_token_endpoints_require_admin(admin):
    server, _ = admin
    client = _login(server)
    cid = client.post("/api/connections", json=_connection_body()).json()["id"]
    anon = TestClient(server.app)
    assert anon.post(f"/api/connections/{cid}/rebuild-token").status_code == 401
    assert anon.request("DELETE", f"/api/connections/{cid}/rebuild-token").status_code == 401


def test_provision_can_also_build_transitions(admin, monkeypatch):
    server, _ = admin
    client = _login(server)

    async def _stub_provision(**kwargs):
        return {"ok": True, "error": None, "created": ["schema MINING", "JOURNEYS"]}

    async def _stub_rebuild(**kwargs):
        return {"ok": True, "error": None, "rows": 0, "built_at": "2026-07-28T00:00:00+00:00"}

    monkeypatch.setattr("app.db.schema_ddl.provision_process_mining_schema", _stub_provision)
    monkeypatch.setattr("app.db.schema_ddl.rebuild_materialized_transitions", _stub_rebuild)

    resp = client.post(
        "/api/connections/provision-schema",
        json={"host": "h", "port": 8563, "username": "u", "password": "p",
              "schema": "MINING", "buildTransitions": True},
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["materialization"]["ok"] is True


# ── Dashboard render: the per-connection rebuild API (in the editor) ──────────


def test_dashboard_has_per_connection_rebuild_api(admin):
    server, _ = admin
    client = _login(server)

    html = client.get("/").text
    # The rebuild-token + curl controls live in the connection editor…
    assert 'id="api_curl"' in html and "copyCurl(" in html
    assert "curl -k -X POST" in html  # -k skips the TLS check
    assert "rebuild-transitions" in html
    # …and there is no longer a standalone global API tab.
    assert 'data-tab="api"' not in html and 'id="tab-api"' not in html


# ── Passkeys (WebAuthn) ───────────────────────────────────────────────────────


def test_passkey_allowed_endpoint_toggles_role(admin):
    server, store = admin
    client = _login(server)
    store.create_user("pat", "pw", is_admin=False)

    r = client.post("/api/users/pat/passkey-allowed", json={"allowed": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert store.get_user("pat").passkey_allowed is True
    # The users listing exposes the flag for the admin UI checkbox.
    listed = {u["username"]: u for u in client.get("/api/users").json()}
    assert listed["pat"]["passkeyAllowed"] is True

    assert client.post("/api/users/pat/passkey-allowed", json={"allowed": False}).status_code == 200
    assert store.get_user("pat").passkey_allowed is False


def test_passkey_allowed_endpoint_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    r = client.post("/api/users/pat/passkey-allowed", json={"allowed": True})
    assert r.status_code == 401


def test_passkey_all_endpoint_is_master_toggle(admin):
    server, store = admin
    client = _login(server)
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)

    assert client.post("/api/access/passkey-all", json={"allowed": True}).status_code == 200
    assert all(u.passkey_allowed for u in store.list_users())

    assert client.post("/api/access/passkey-all", json={"allowed": False}).status_code == 200
    assert not any(u.passkey_allowed for u in store.list_users())


def test_passkey_all_endpoint_requires_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.post("/api/access/passkey-all", json={"allowed": True}).status_code == 401


def test_admin_passkey_login_begin_is_enumeration_resistant(admin):
    # Enumeration-resistant: an eligible admin, a non-admin, an admin without a
    # passkey and an unknown username all return the SAME 200 shape (challenge +
    # one allowCredentials + cookie). The admin-only restriction is enforced at
    # the finish step (verification fails), not by a leaky 403 at begin.
    server, store = admin
    store.create_user("padmin", "pw", is_admin=True)
    store.set_passkey_allowed("padmin", True)
    store.add_credential("padmin", credential_id="cred-1", public_key="K", sign_count=0)
    store.create_user("power", "pw", is_admin=False)  # non-admin, has a passkey
    store.set_passkey_allowed("power", True)
    store.add_credential("power", credential_id="cred-2", public_key="K", sign_count=0)
    store.create_user("plain", "pw", is_admin=True)   # admin, no passkey

    def shape(username: str) -> tuple:
        client = TestClient(server.app)
        r = client.post("/login/passkey/begin", json={"username": username})
        body = r.json()
        return (
            r.status_code,
            "detail" in body,
            len(body.get("allowCredentials", [])),
            server.passkey.CHALLENGE_COOKIE in client.cookies,
        )

    eligible = shape("padmin")
    assert eligible == (200, False, 1, True)
    assert shape("power") == eligible   # a non-admin doesn't stand out
    assert shape("plain") == eligible   # an admin without a passkey doesn't either
    assert shape("ghost") == eligible   # nor an unknown username


# ── Two-factor (TOTP) — admin gating + the admin two-step login ───────────────


def test_mfa_allowed_endpoint_toggles_and_lists(admin):
    server, store = admin
    client = _login(server)
    store.create_user("pat", "pw", is_admin=False)

    r = client.post("/api/users/pat/mfa-allowed", json={"allowed": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert store.get_user("pat").mfa_allowed is True
    listed = {u["username"]: u for u in client.get("/api/users").json()}
    assert listed["pat"]["mfaAllowed"] is True and listed["pat"]["mfaEnabled"] is False

    assert client.post("/api/users/pat/mfa-allowed", json={"allowed": False}).status_code == 200
    assert store.get_user("pat").mfa_allowed is False


def test_mfa_allowed_and_all_require_admin(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert client.post("/api/users/pat/mfa-allowed", json={"allowed": True}).status_code == 401
    assert client.post("/api/access/mfa-all", json={"allowed": True}).status_code == 401


def test_mfa_all_endpoint_is_master_toggle(admin):
    server, store = admin
    client = _login(server)
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    assert client.post("/api/access/mfa-all", json={"allowed": True}).status_code == 200
    assert all(u.mfa_allowed for u in store.list_users())
    assert client.post("/api/access/mfa-all", json={"allowed": False}).status_code == 200
    assert not any(u.mfa_allowed for u in store.list_users())


def test_admin_login_asks_for_a_code_then_signs_in(admin):
    import pyotp
    import app.services.mfa as mfa
    server, store = admin
    secret = mfa.new_secret()
    store.create_user("padmin", "pw", is_admin=True)
    store.set_mfa_allowed("padmin", True)
    store.set_totp_secret("padmin", secret)

    client = TestClient(server.app)
    r = client.post("/login", data={"username": "padmin", "password": "pw"},
                    follow_redirects=False)
    # Password ok, but the code step is shown — no admin cookie yet.
    assert r.status_code == 200 and "Authentication code" in r.text
    assert server.COOKIE not in client.cookies
    assert server.passkey  # module wired (sanity)
    assert mfa.PENDING_COOKIE in client.cookies

    # Wrong code stays on the step, still no session.
    bad = client.post("/login/mfa", data={"code": "000000"}, follow_redirects=False)
    assert bad.status_code == 401 and server.COOKIE not in client.cookies

    ok = client.post("/login/mfa", data={"code": pyotp.TOTP(secret).now()},
                     follow_redirects=False)
    assert ok.status_code == 303 and server.COOKIE in client.cookies


def test_admin_login_mfa_without_pending_is_rejected(admin):
    server, _ = admin
    client = TestClient(server.app)  # never did the password step
    r = client.post("/login/mfa", data={"code": "000000"}, follow_redirects=False)
    assert r.status_code == 401 and server.COOKIE not in client.cookies


def test_admin_mfa_setup_roundtrip(admin):
    import pyotp
    server, store = admin
    client = _login(server)  # built-in Administrator
    store.set_mfa_allowed("Administrator", True)

    begin = client.post("/api/mfa/setup/begin")
    assert begin.status_code == 200
    secret = begin.json()["secret"]
    fin = client.post("/api/mfa/setup/finish", json={"code": pyotp.TOTP(secret).now()})
    assert fin.status_code == 200 and len(fin.json()["recoveryCodes"]) == 10
    assert client.get("/api/mfa/status").json()["enabled"] is True

    # Disable requires the current code (re-auth the downgrade).
    assert client.post("/api/mfa/disable", json={"code": "000000"}).status_code == 401
    assert store.get_user("Administrator").mfa_enabled is True
    assert client.post("/api/mfa/disable", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    assert store.get_user("Administrator").mfa_enabled is False


def test_admin_mfa_disable_is_ip_throttled(admin):
    import pyotp
    server, store = admin
    client = _login(server)  # built-in Administrator (correct password → throttle clear)
    store.set_mfa_allowed("Administrator", True)
    secret = client.post("/api/mfa/setup/begin").json()["secret"]
    client.post("/api/mfa/setup/finish", json={"code": pyotp.TOTP(secret).now()})

    for _ in range(server._LOGIN_IP_MAX):
        assert client.post("/api/mfa/disable", json={"code": "000000"}).status_code == 401
    assert client.post("/api/mfa/disable", json={"code": "000000"}).status_code == 429
    assert store.get_user("Administrator").mfa_enabled is True  # never stripped


def test_admin_login_forces_2fa_setup_when_required(admin):
    # An admin allowed 2FA but not enrolled must configure it before a session —
    # the password alone yields the enrolment step, not the dashboard.
    import app.services.mfa as mfa
    server, store = admin
    store.create_user("padmin", "pw", is_admin=True)
    store.set_mfa_allowed("padmin", True)  # allowed, not enrolled
    client = TestClient(server.app)

    r = client.post("/login", data={"username": "padmin", "password": "pw"},
                    follow_redirects=False)
    assert r.status_code == 200 and "Set up two-factor" in r.text
    assert server.COOKIE not in client.cookies  # no admin session yet
    assert mfa.PENDING_COOKIE in client.cookies and mfa.SETUP_COOKIE in client.cookies


def test_admin_login_mfa_setup_completes_and_signs_in(admin):
    import pyotp
    import app.services.mfa as mfa
    server, store = admin
    store.create_user("padmin", "pw", is_admin=True)
    store.set_mfa_allowed("padmin", True)
    client = TestClient(server.app)
    client.post("/login", data={"username": "padmin", "password": "pw"}, follow_redirects=False)

    # The secret rides in the setup cookie; derive the code from it.
    secret = mfa.read_setup_cookie(
        client.cookies.get(mfa.SETUP_COOKIE), username="padmin", aud="admin")
    assert secret

    # Wrong code: stays on the setup step, no session, not enrolled.
    bad = client.post("/login/mfa-setup", data={"code": "000000"}, follow_redirects=False)
    assert bad.status_code == 401 and server.COOKIE not in client.cookies
    assert store.get_user("padmin").mfa_enabled is False

    ok = client.post("/login/mfa-setup", data={"code": pyotp.TOTP(secret).now()},
                     follow_redirects=False)
    assert ok.status_code == 200 and "Save your recovery codes" in ok.text
    assert server.COOKIE in client.cookies              # session issued
    assert store.get_user("padmin").mfa_enabled is True  # enrolled
