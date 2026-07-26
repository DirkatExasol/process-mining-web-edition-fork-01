"""Main-app authentication tests — the GUI server's sign-in gate.

Drives the real GUI-server FastAPI app (`frontend/server.py`) with an isolated
security store, verifying that /api/* is gated when sign-in is required and open
otherwise, and that the login/session/logout cookie flow works.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gui(tmp_path, monkeypatch):
    """A TestClient over the GUI server, wired to a throwaway security store."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))

    # Reload the config + security stack against the temp data dir.
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security

    import app.store.security as security_mod

    importlib.reload(security_mod)

    # Load frontend/server.py as a module (it lives outside the app package).
    frontend_dir = Path(config.PROJECT_ROOT) / "frontend"
    sys.path.insert(0, str(frontend_dir))
    for name in ("server",):
        sys.modules.pop(name, None)
    server = importlib.import_module("server")
    importlib.reload(server)

    # Point the GUI's proxy at a stub backend so gated calls don't need Exasol.
    class _StubResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"stub": true}'

    class _StubClient:
        async def request(self, *args, **kwargs):
            return _StubResponse()

    monkeypatch.setattr(server, "_get_client", lambda: _StubClient())

    return server, security_mod.store


def test_backend_proxy_pins_the_internal_ca(gui, monkeypatch, tmp_path):
    """The GUI→backend hop is HTTPS and verified against the pinned internal CA;
    it falls back to system trust only when the pinned CA file is absent."""
    server, _ = gui
    assert server.BACKEND_URL.startswith("https://")  # encrypted hop

    ca = tmp_path / "internal.crt"
    ca.write_text("x", encoding="utf-8")
    monkeypatch.setattr(server, "BACKEND_CA_PATH", str(ca))
    assert server._backend_verify() == str(ca)  # pinned

    monkeypatch.setattr(server, "BACKEND_CA_PATH", str(tmp_path / "missing.crt"))
    assert server._backend_verify() is True  # system trust fallback


def test_health_is_open_even_when_login_required(gui):
    server, store = gui
    assert store.require_login is True
    client = TestClient(server.app)
    # /api/health is exempt from the gate.
    assert client.get("/api/health").status_code == 200


def test_api_is_gated_without_a_session(gui):
    server, store = gui
    client = TestClient(server.app)
    resp = client.get("/api/projects")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_session_reports_unauthenticated_and_require_login(gui):
    server, _ = gui
    client = TestClient(server.app)
    body = client.get("/auth/session").json()
    assert body == {
        "authenticated": False,
        "username": None,
        "isAdmin": False,
        "isPower": False,
        "displayName": None,
        "authSource": None,
        "requireLogin": True,
        "idleTimeoutMins": 0,
    }


def test_session_reports_and_refreshes_with_idle_timeout(gui):
    server, store = gui
    client = TestClient(server.app)
    # Default: disabled.
    assert client.get("/auth/session").json()["idleTimeoutMins"] == 0
    store.set_idle_timeout_mins(20)
    assert client.get("/auth/session").json()["idleTimeoutMins"] == 20

    # Signing in issues a session; polling /auth/session slides it (re-sets cookie).
    client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    )
    resp = client.get("/auth/session")
    assert resp.json()["authenticated"] is True
    assert server.SESSION_COOKIE in resp.cookies  # sliding refresh on activity


def test_login_wrong_password_is_rejected(gui):
    server, _ = gui
    client = TestClient(server.app)
    resp = client.post("/auth/login", json={"username": "Administrator", "password": "nope"})
    assert resp.status_code == 401
    assert server.SESSION_COOKIE not in resp.cookies


def test_login_then_access_then_logout(gui):
    server, _ = gui
    client = TestClient(server.app)

    # Sign in with the seeded administrator.
    resp = client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    )
    assert resp.status_code == 200
    assert server.SESSION_COOKIE in client.cookies

    # The session is now recognised, and gated API calls pass the guard.
    session = client.get("/auth/session").json()
    assert session["authenticated"] is True
    assert session["username"] == "Administrator"
    assert client.get("/api/projects").status_code == 200

    # Logging out clears the cookie and re-gates the API.
    client.post("/auth/logout")
    assert client.get("/auth/session").json()["authenticated"] is False
    assert client.get("/api/projects").status_code == 401


def test_disabled_user_cannot_sign_in(gui):
    server, store = gui
    store.create_user("bob", "pw", is_admin=False)
    store.set_enabled("bob", False)
    client = TestClient(server.app)
    resp = client.post("/auth/login", json={"username": "bob", "password": "pw"})
    assert resp.status_code == 401


def test_open_access_when_login_not_required(gui):
    server, store = gui
    store.set_require_login(False)
    client = TestClient(server.app)
    # No session, but the API is reachable because sign-in is not required.
    assert client.get("/api/projects").status_code == 200
    assert client.get("/auth/session").json()["requireLogin"] is False


# ── Directory (LDAP) availability indicator ───────────────────────────────────


def test_directory_status_not_configured_reports_unconfigured(gui):
    server, _ = gui
    client = TestClient(server.app)
    # No LDAP configured ⇒ the login panel shows no indicator.
    assert client.get("/auth/directory-status").json() == {
        "configured": False,
        "available": False,
    }


def test_directory_status_probes_when_configured(gui, monkeypatch):
    server, store = gui
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://dir", "baseDN": "dc=x"})

    import app.services.ldap_auth as ldap_auth

    # Reachable — the service-bind probe succeeds.
    monkeypatch.setattr(ldap_auth, "test_settings", lambda *a, **k: {"ok": True})
    client = TestClient(server.app)
    assert client.get("/auth/directory-status").json() == {
        "configured": True,
        "available": True,
    }


def test_directory_status_reports_unavailable_on_probe_failure(gui, monkeypatch):
    server, store = gui
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://dir", "baseDN": "dc=x"})

    import app.services.ldap_auth as ldap_auth

    # Unreachable — the probe returns ok:false (or raises); the endpoint must not error.
    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ldap_auth, "test_settings", _boom)
    client = TestClient(server.app)
    assert client.get("/auth/directory-status").json() == {
        "configured": True,
        "available": False,
    }


# ── Session invalidation on logout ────────────────────────────────────────────


def test_logout_invalidates_captured_token(gui):
    """A token captured before logout must be rejected afterwards — server-side
    invalidation via the per-user session epoch, not just clearing the cookie."""
    server, _ = gui
    client = TestClient(server.app)
    client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    )
    token = client.cookies.get(server.SESSION_COOKIE)
    assert token

    def _replay_status() -> int:
        c = TestClient(server.app)
        c.cookies.set(server.SESSION_COOKIE, token)
        return c.get("/api/projects").status_code

    assert _replay_status() == 200  # the captured token works before logout
    client.post("/auth/logout")  # bumps the user's session epoch
    assert _replay_status() == 401  # the same token no longer passes the gate


# ── License / Demo Mode status (pre-auth, computed locally) ────────────────────


def test_license_status_demo_and_licensed(gui, monkeypatch):
    server, _ = gui
    import app.licensing as licensing

    client = TestClient(server.app)

    # No valid license → Demo Mode with the remaining grace seconds.
    monkeypatch.setattr(
        licensing, "evaluate", lambda: licensing.LicenseStatus("missing", message="none")
    )
    monkeypatch.setattr(licensing, "demo_remaining_secs", lambda create: 300)
    body = client.get("/auth/license-status").json()
    assert body["demoMode"] is True
    assert body["remainingSeconds"] == 300

    # Valid license → not demo, no countdown.
    monkeypatch.setattr(
        licensing,
        "evaluate",
        lambda: licensing.LicenseStatus("valid", licensee="Acme", expires="2099-01-01"),
    )
    body = client.get("/auth/license-status").json()
    assert body["demoMode"] is False
    assert body["remainingSeconds"] is None
    assert body["licensee"] == "Acme"


def test_login_appearance_endpoint_is_open(gui):
    """The login background is served pre-auth (the login page needs it)."""
    server, store = gui
    client = TestClient(server.app)
    assert client.get("/auth/login-appearance").json() == {
        "type": "default",
        "color": "",
        "image": "",
    }
    store.set_login_appearance(type="color", color="#0a84ff")
    assert client.get("/auth/login-appearance").json() == {
        "type": "color",
        "color": "#0a84ff",
        "image": "",
    }
