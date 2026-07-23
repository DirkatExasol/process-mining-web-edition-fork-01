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
        "displayName": None,
        "authSource": None,
        "requireLogin": True,
    }


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
