"""The integration API's own role gate.

The integration *console* (port 8100) refuses anyone without the Developer role, but
these endpoints live on the shared compute backend — and the MAIN app proxies `/api/*`
for every enabled user. So the router must re-check the role itself; otherwise a plain
(or power) user could drive the whole data-source surface through the app's proxy,
including the sandboxed file preview.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PMW_INTEGRATION_FILES_DIR", str(tmp_path / "files"))

    import app.config as config
    importlib.reload(config)
    import app.store.crypto as crypto
    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security
    import app.store.security as security_mod
    importlib.reload(security_mod)
    import app.integration.files as files_mod
    importlib.reload(files_mod)
    import app.api.integration as integration_api
    importlib.reload(integration_api)
    import app.main as main
    importlib.reload(main)

    return main.app, security_mod.store, config


def _user(store, name, *, power=False, developer=False, admin=False):
    store.create_user(name, "pw", is_admin=admin)
    if power:
        store.set_power(name, True)
    if developer:
        store.set_developer(name, True)
    return name


# Every mutating/reading endpoint on the router, as (method, path, json).
ENDPOINTS = [
    ("get", "/api/integration/sources", None),
    ("get", "/api/integration/source-types", None),
    ("get", "/api/integration/status", None),
    ("post", "/api/integration/sources/preview", {"path": "x.log", "limit": 5}),
    ("post", "/api/integration/source-types", {"name": "x", "sample": "", "fields": []}),
    ("post", "/api/integration/parse/timestamp", {"value": "2026-01-01"}),
]


@pytest.mark.parametrize("role", ["plain", "power"])
@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_non_developers_are_refused(backend, role, method, path, payload):
    """A plain user AND a power user (deliberately barred from the console) are refused
    on every endpoint — this is the app-proxy bypass path."""
    app, store, _ = backend
    _user(store, "alice", power=(role == "power"))
    client = TestClient(app)
    resp = getattr(client, method)(path, headers={"X-PMW-User": "alice"}, **({"json": payload} if payload else {}))
    assert resp.status_code == 403, f"{method.upper()} {path} should be forbidden for a {role} user"


def test_developer_and_admin_are_allowed(backend):
    app, store, config = backend
    _user(store, "dev", developer=True)
    _user(store, "boss", admin=True)
    client = TestClient(app)
    for who in ("dev", "boss"):
        assert client.get("/api/integration/sources", headers={"X-PMW-User": who}).status_code == 200


def test_preview_cannot_be_used_as_an_unauthenticated_file_read(backend):
    """The file preview took no user at all before — the worst leg of the bypass."""
    app, store, config = backend
    (config.INTEGRATION_FILES_DIR / "secret.log").write_text("classified\n")
    _user(store, "alice")  # plain user
    client = TestClient(app)
    resp = client.post(
        "/api/integration/sources/preview",
        headers={"X-PMW-User": "alice"},
        json={"path": "secret.log", "limit": 5},
    )
    assert resp.status_code == 403
    assert "classified" not in resp.text


def test_disabled_console_also_disables_its_api(backend):
    """Turning the console off in the admin panel must disable the API too, not just
    the port-8100 sign-in."""
    app, store, _ = backend
    _user(store, "dev", developer=True)
    client = TestClient(app)
    assert client.get("/api/integration/sources", headers={"X-PMW-User": "dev"}).status_code == 200
    store.set_integration_enabled(False)
    resp = client.get("/api/integration/sources", headers={"X-PMW-User": "dev"})
    assert resp.status_code == 403 and "turned off" in resp.json()["detail"]


def test_revoking_the_role_takes_effect_immediately(backend):
    app, store, _ = backend
    _user(store, "dev", developer=True)
    client = TestClient(app)
    assert client.get("/api/integration/sources", headers={"X-PMW-User": "dev"}).status_code == 200
    store.set_developer("dev", False)
    assert client.get("/api/integration/sources", headers={"X-PMW-User": "dev"}).status_code == 403
