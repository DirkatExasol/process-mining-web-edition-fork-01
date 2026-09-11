"""The shared LLM resolver (services/llm_config.py): precedence, freshness, source label."""

from __future__ import annotations

import importlib

import pytest

from app.models import LLMServer


@pytest.fixture
def security(tmp_path, monkeypatch):
    """A fresh security store bound to a throwaway data dir (mirrors test_report.py)."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs as certs

    importlib.reload(certs)
    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.store.logs as logs_mod

    importlib.reload(logs_mod)
    return security_mod


@pytest.fixture
def llm_config(security, monkeypatch):
    """The resolver bound to the throwaway store (its module-level singleton is rebound)."""
    import app.services.llm_config as m

    importlib.reload(m)
    monkeypatch.setattr(m, "security_store", security.store)
    return m


class FakeDB:
    """Stands in for a DatabaseManager: only the resolver's two touch-points matter."""

    def __init__(self, own: LLMServer | None = None, conn_id: str | None = None):
        self._own = own
        self.active_profile_id = conn_id

    @property
    def active_llm_server(self) -> LLMServer | None:
        return self._own


def _make_connection(store, **llm) -> str:
    conn = store.upsert_connection(
        {"name": "Sales Exasol", "host": "db.example.com", "username": "u", **llm}
    )
    return conn.id


# ── precedence ──────────────────────────────────────────────────────────────


def test_connection_overrides_global(security, llm_config):
    security.store.set_report_config(
        llm_url="https://global.example/v1", llm_model="global-model", llm_key="gk"
    )
    own = LLMServer(name="Sales Exasol", serverURL="https://conn.example/v1", model="conn-model")
    r = llm_config.resolve_llm(FakeDB(own=own))
    assert r.source == "connection"
    assert r.url == "https://conn.example/v1"
    assert r.model == "conn-model"
    assert "Sales Exasol" in r.label


def test_falls_back_to_global_default(security, llm_config):
    security.store.set_report_config(
        llm_url="https://global.example/v1", llm_model="global-model", llm_key="gk"
    )
    r = llm_config.resolve_llm(FakeDB(own=None))
    assert r.source == "global"
    assert r.url == "https://global.example/v1"
    assert r.model == "global-model"
    assert r.key == "gk"
    assert r.configured


def test_none_when_nothing_configured(security, llm_config):
    r = llm_config.resolve_llm(FakeDB(own=None))
    assert r.source == "none"
    assert not r.configured
    assert r.as_server() is None


def test_blank_connection_url_is_not_an_override(security, llm_config):
    security.store.set_report_config(llm_url="https://global.example/v1", llm_model="g")
    own = LLMServer(name="x", serverURL="   ", model="ignored")  # whitespace-only → not set
    r = llm_config.resolve_llm(FakeDB(own=own))
    assert r.source == "global"


# ── connection_llm_server: freshness (no snapshot) ──────────────────────────


def test_connection_llm_server_reads_fresh(security, llm_config):
    cid = _make_connection(
        security.store, llmURL="https://conn.example/v1", llmModel="gpt-4o", llmKey="k1"
    )
    srv = llm_config.connection_llm_server(cid)
    assert srv is not None and srv.model == "gpt-4o" and srv.serverURL == "https://conn.example/v1"

    # Edit the model — a later read must reflect it immediately (no cached snapshot).
    security.store.upsert_connection({"id": cid, "name": "Sales Exasol", "llmURL": "https://conn.example/v1", "llmModel": "gpt-5"})
    assert llm_config.connection_llm_server(cid).model == "gpt-5"


def test_connection_llm_server_none_without_url(security, llm_config):
    cid = _make_connection(security.store, llmModel="gpt-4o")  # model but no URL
    assert llm_config.connection_llm_server(cid) is None
    assert llm_config.connection_llm_server(None) is None
    assert llm_config.connection_llm_server("nope") is None


def test_resolve_reflects_edited_model_without_reconnect(security, llm_config):
    """End-to-end: the resolver returns the connection's CURRENT model each call."""
    cid = _make_connection(
        security.store, llmURL="https://conn.example/v1", llmModel="old-model", llmKey="k"
    )

    def resolve():
        own = llm_config.connection_llm_server(cid)
        return llm_config.resolve_llm(FakeDB(own=own, conn_id=cid))

    assert resolve().model == "old-model"
    security.store.upsert_connection({"id": cid, "name": "Sales Exasol", "llmURL": "https://conn.example/v1", "llmModel": "new-model"})
    assert resolve().model == "new-model"  # no reconnect, no stale snapshot
