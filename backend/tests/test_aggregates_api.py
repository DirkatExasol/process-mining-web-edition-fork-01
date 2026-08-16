"""Aggregate endpoint auth + validation gates (all fire before any database work)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401

    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.db.manager as manager

    importlib.reload(manager)
    import app.api.connections as connections_api

    importlib.reload(connections_api)
    import app.api.aggregates as aggregates_api

    importlib.reload(aggregates_api)
    import app.main as main

    importlib.reload(main)
    return main.app, security_mod.store


def _user(store, name, *, power=False, developer=False, admin=False):
    store.create_user(name, "pw", is_admin=admin)
    if power:
        store.set_power(name, True)
    if developer:
        store.set_developer(name, True)


def _conn(store, *, assignments):
    return store.upsert_connection({
        "name": "Cust", "host": "db.example.com", "port": 8563, "username": "svc",
        "schema": "MINING", "password": "s3cret", "llmURL": "", "llmModel": "", "llmKey": "",
        "assignments": assignments,
    }).id


def _body(cid, members):
    return {
        "connectionId": cid,
        "members": members,
        "sigmaName": "Σ Test",
        "highLevel": {"name": "High", "targetConnectionId": "", "targetSchema": ""},
        "detail": {"name": "Detail", "targetConnectionId": "", "targetSchema": ""},
    }


def test_non_developer_cannot_create(backend):
    app, store = backend
    _user(store, "pat", power=True)  # power user is NOT allowed
    cid = _conn(store, assignments=["pat"])
    client = TestClient(app)
    r = client.post(f"/api/projects/P/aggregate", json=_body(cid, ["A", "B"]), headers={"X-PMW-User": "pat"})
    assert r.status_code == 403


def test_developer_needs_at_least_two_members(backend):
    app, store = backend
    _user(store, "dev", developer=True)
    cid = _conn(store, assignments=["dev"])
    client = TestClient(app)
    r = client.post(f"/api/projects/P/aggregate", json=_body(cid, ["A"]), headers={"X-PMW-User": "dev"})
    assert r.status_code == 400


def test_idor_unassigned_connection(backend):
    app, store = backend
    _user(store, "dev", developer=True)  # assigned to nothing
    _user(store, "owner", developer=True)
    cid = _conn(store, assignments=["owner"])
    client = TestClient(app)
    r = client.post(f"/api/projects/P/aggregate", json=_body(cid, ["A", "B"]), headers={"X-PMW-User": "dev"})
    assert r.status_code == 403


def test_list_aggregates_empty(backend):
    app, store = backend
    _user(store, "dev", developer=True)
    cid = _conn(store, assignments=["dev"])
    client = TestClient(app)
    r = client.get("/api/projects/P/aggregates", params={"connectionId": cid}, headers={"X-PMW-User": "dev"})
    assert r.status_code == 200 and r.json()["aggregates"] == []


def _group(sigma, members, name="Detail"):
    return {"sigmaName": sigma, "members": members, "detail": {"name": name, "targetConnectionId": "", "targetSchema": ""}}


def _set_body(cid, groups):
    return {"connectionId": cid, "highLevel": {"name": "High", "targetConnectionId": "", "targetSchema": ""}, "aggregates": groups}


def test_set_create_rejects_overlapping_members(backend):
    app, store = backend
    _user(store, "dev", developer=True)
    cid = _conn(store, assignments=["dev"])
    client = TestClient(app)
    body = _set_body(cid, [_group("Σ1", ["A", "B"]), _group("Σ2", ["B", "C"])])  # B in both
    r = client.post("/api/projects/P/aggregate-set", json=body, headers={"X-PMW-User": "dev"})
    assert r.status_code == 400 and "only one aggregate" in r.json()["detail"]


def test_set_create_needs_developer(backend):
    app, store = backend
    _user(store, "pat", power=True)
    cid = _conn(store, assignments=["pat"])
    client = TestClient(app)
    r = client.post("/api/projects/P/aggregate-set", json=_set_body(cid, [_group("Σ1", ["A", "B"])]), headers={"X-PMW-User": "pat"})
    assert r.status_code == 403


def test_add_to_missing_set_is_404(backend):
    app, store = backend
    _user(store, "dev", developer=True)
    cid = _conn(store, assignments=["dev"])
    client = TestClient(app)
    body = {"connectionId": cid, "aggregates": [_group("Σ1", ["A", "B"])]}
    r = client.post("/api/projects/nope/aggregate-set/add", json=body, headers={"X-PMW-User": "dev"})
    assert r.status_code == 404


def test_aggregate_set_roundtrips_in_store(backend):
    _app, store = backend
    rec = store.save_aggregate_set({
        "sourceConnectionId": "c1", "sourceProjectId": "P",
        "highLevelConnectionId": "c1", "highLevelProjectId": "agg_1",
        "highLevelSchema": "MINING", "highLevelTitle": "High",
        "aggregates": [{"sigmaStep": "Σ1", "members": ["A", "B"], "detailConnectionId": "c1", "detailProjectId": "d1", "detailSchema": "MINING", "detailTitle": "D"}],
    })
    assert rec["createdAt"] and rec["updatedAt"]
    assert store.aggregate_set_by_source("c1", "P")["highLevelProjectId"] == "agg_1"
    assert store.aggregate_set_by_high_level("c1", "agg_1")["sourceProjectId"] == "P"
    # upsert by source: a second save with an extra aggregate replaces, keeps createdAt.
    rec["aggregates"].append({"sigmaStep": "Σ2", "members": ["C", "D"], "detailConnectionId": "c1", "detailProjectId": "d2", "detailSchema": "MINING", "detailTitle": "D2"})
    rec2 = store.save_aggregate_set(rec)
    assert rec2["createdAt"] == rec["createdAt"]
    assert len(store.aggregate_set_by_source("c1", "P")["aggregates"]) == 2


def test_aggregate_link_roundtrips_in_store(backend):
    _app, store = backend
    store.add_aggregate_link(
        {"connectionId": "c1", "projectId": "agg_1", "sigmaStep": "Σ", "detailConnectionId": "c1", "detailProjectId": "d1"}
    )
    got = store.aggregates_for("c1", "agg_1")
    assert len(got) == 1 and got[0]["detailProjectId"] == "d1"
    # keyed by (connection, project, sigma) — a second call with the same key replaces.
    store.add_aggregate_link(
        {"connectionId": "c1", "projectId": "agg_1", "sigmaStep": "Σ", "detailConnectionId": "c2", "detailProjectId": "d2"}
    )
    got2 = store.aggregates_for("c1", "agg_1")
    assert len(got2) == 1 and got2[0]["detailProjectId"] == "d2"
