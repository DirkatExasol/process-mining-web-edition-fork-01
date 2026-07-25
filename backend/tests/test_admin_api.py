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


def test_login_get_inactivity_shows_notice(admin):
    server, _ = admin
    client = TestClient(server.app)
    assert "inactivity" not in client.get("/login").text
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
    # Every one is tagged with the backup operation.
    assert entries and all(e["operation"] == "backup" for e in entries)
