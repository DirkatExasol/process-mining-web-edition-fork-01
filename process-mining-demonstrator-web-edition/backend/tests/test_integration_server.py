"""Integration console tests — the fourth surface's role gate + audience isolation.

Drives the real integration server (`integration/server.py`) with an isolated
security store. The console reuses the shared surface factory (covered in depth by
test_auth.py); here we verify only what differs: only developer/admin users may
sign in, its session cookie is a distinct audience, and the admin can disable it.
"""

from __future__ import annotations

import importlib
import json as _json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def integ(tmp_path, monkeypatch):
    """A TestClient over the integration server, wired to a throwaway store."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))

    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto  # noqa: F401

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security

    import app.store.security as security_mod

    importlib.reload(security_mod)

    import app.web_surface as web_surface

    importlib.reload(web_surface)

    # Load integration/server.py as a module (it lives outside the app package).
    integ_dir = Path(config.PROJECT_ROOT) / "integration"
    sys.path.insert(0, str(integ_dir))
    for name in ("server",):
        sys.modules.pop(name, None)
    server = importlib.import_module("server")
    importlib.reload(server)

    class _StubResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"stub": true}'

    class _StubClient:
        async def request(self, *args, **kwargs):
            return _StubResponse()

    server.app.state.get_backend_client = lambda: _StubClient()
    return server, security_mod.store


def _mk(store, name, *, power=False, developer=False, admin=False):
    store.create_user(name, "pw", is_admin=admin)
    if power:
        store.set_power(name, True)
    if developer:
        store.set_developer(name, True)
    return name


def test_plain_user_is_denied(integ):
    server, store = integ
    _mk(store, "alice")  # no role
    client = TestClient(server.app)
    r = client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 403
    assert "Developer" in r.json()["detail"]
    assert server.SESSION_COOKIE not in client.cookies


def test_power_user_is_denied(integ):
    """The power role does NOT admit to the integration console — only developer/admin."""
    server, store = integ
    _mk(store, "pat", power=True)
    client = TestClient(server.app)
    r = client.post("/auth/login", json={"username": "pat", "password": "pw"})
    assert r.status_code == 403
    assert server.SESSION_COOKIE not in client.cookies


@pytest.mark.parametrize("kw", [{"developer": True}, {"admin": True}])
def test_privileged_users_may_sign_in(integ, kw):
    server, store = integ
    _mk(store, "bob", **kw)
    client = TestClient(server.app)
    r = client.post("/auth/login", json={"username": "bob", "password": "pw"})
    assert r.status_code == 200
    assert server.SESSION_COOKIE in client.cookies
    body = client.get("/auth/session").json()
    assert body["authenticated"] is True
    assert body["isDeveloper"] is bool(kw.get("developer"))
    # The API proxy is reachable once signed in.
    assert client.get("/api/projects").status_code == 200


def test_developer_role_grants_and_revokes_access(integ):
    server, store = integ
    _mk(store, "dev", developer=True)
    client = TestClient(server.app)
    assert client.post("/auth/login", json={"username": "dev", "password": "pw"}).status_code == 200
    assert client.get("/api/projects").status_code == 200
    # Revoking the role drops the session immediately (checked in _current_user).
    store.set_developer("dev", False)
    assert client.get("/auth/session").json()["authenticated"] is False
    assert client.get("/api/projects").status_code == 401


def test_app_audience_cookie_is_rejected(integ):
    """An app session cookie (audience "app") must not authenticate the integration
    console, even though both are signed with the same key and name a valid user."""
    import app.store.crypto as crypto

    server, store = integ
    _mk(store, "dev", developer=True)
    epoch = store.session_epoch("dev")
    forged = crypto.sign_session(
        _json.dumps({"u": "dev", "e": epoch, "a": "app"}).encode("utf-8")
    )
    client = TestClient(server.app)
    client.cookies.set(server.SESSION_COOKIE, forged)
    assert client.get("/api/projects").status_code == 401


def test_disabled_console_serves_503(integ):
    server, store = integ
    _mk(store, "dev", developer=True)
    store.set_integration_enabled(False)
    client = TestClient(server.app)
    # An API/XHR call is refused with 503…
    assert client.post("/auth/login", json={"username": "dev", "password": "pw"}).status_code == 503
    # …and a page navigation gets the disabled page, not the SPA.
    page = client.get("/", headers={"accept": "text/html"})
    assert page.status_code == 503
    assert "console unavailable" in page.text.lower()
    assert "<div id=\"root\">" not in page.text  # not the SPA shell
    # Re-enabling restores sign-in.
    store.set_integration_enabled(True)
    assert client.post("/auth/login", json={"username": "dev", "password": "pw"}).status_code == 200
