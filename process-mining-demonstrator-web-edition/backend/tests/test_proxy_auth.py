"""The compute backend rejects any /api/* request that did not come through the
GUI proxy (which alone validated the session) — closing the X-PMW-User forgery gap.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def guarded_backend(tmp_path, monkeypatch):
    """The backend app with proxy-auth ENFORCED (the production default)."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PMW_REQUIRE_PROXY_AUTH", "1")

    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.db.manager as manager

    importlib.reload(manager)
    import app.main as main

    importlib.reload(main)
    return main.app, crypto.proxy_auth_secret()


def test_direct_backend_access_is_rejected_without_the_secret(guarded_backend):
    app, _ = guarded_backend
    client = TestClient(app)
    # No proxy-auth header → a local process forging X-PMW-User is blocked.
    resp = client.get("/api/connection/status", headers={"X-PMW-User": "Administrator"})
    assert resp.status_code == 403
    assert "not allowed" in resp.json()["detail"].lower()


def test_wrong_secret_is_rejected(guarded_backend):
    app, _ = guarded_backend
    client = TestClient(app)
    resp = client.get(
        "/api/connection/status", headers={"X-PMW-Proxy-Auth": "not-the-secret"}
    )
    assert resp.status_code == 403


def test_correct_secret_is_accepted(guarded_backend):
    app, secret = guarded_backend
    client = TestClient(app)
    resp = client.get(
        "/api/connection/status", headers={"X-PMW-Proxy-Auth": secret}
    )
    assert resp.status_code == 200  # passes the gate (no DB needed for status)


def test_health_is_exempt(guarded_backend):
    app, _ = guarded_backend
    client = TestClient(app)
    # The container liveness probe hits the backend directly, without the secret.
    assert client.get("/api/health").status_code == 200
