"""The compute backend logs the operational problems that matter: database
connection errors, SQL execution errors, timeouts and simulation crashes.

The shared LogStore is redirected to a temp instance (log_events references the
`app.store.logs` module, so patching its `store`/`LOGS_DIR` is picked up).
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def logstore(tmp_path, monkeypatch):
    import app.store.logs as logs_mod
    from app.store.logs import LogStore

    archive = tmp_path / "arch"
    archive.mkdir()
    monkeypatch.setattr(logs_mod, "LOGS_DIR", archive)
    s = LogStore(path=tmp_path / "logs.sqlite3")
    s.set_level("DEBUG")  # record everything so we can assert on any severity
    monkeypatch.setattr(logs_mod, "store", s)
    return s


# ── Simulation crash / oversized run ──────────────────────────────────────────


def test_simulation_rejects_too_many_journeys(logstore):
    from app.main import app

    client = TestClient(app)
    body = {"graph": {"steps": {}, "transitions": []}, "config": {"journeyCount": 999_999}}
    resp = client.post("/api/simulate", json=body)
    assert resp.status_code == 400
    entries = logstore.query(operation="simulation")
    assert entries and "exceeds" in entries[0]["message"].lower()


def test_simulation_crash_is_logged(logstore, monkeypatch):
    from app.main import app
    from app.services import simulation

    def _boom(*args, **kwargs):
        raise RuntimeError("ran out of memory")

    monkeypatch.setattr(simulation, "simulate", _boom)
    client = TestClient(app)
    body = {"graph": {"steps": {}, "transitions": []}, "config": {"journeyCount": 100}}
    resp = client.post("/api/simulate", json=body)
    assert resp.status_code == 500
    entries = logstore.query(operation="simulation", severities=["ERROR"])
    assert entries and "Simulation failed" in entries[0]["message"]


def test_simulation_timeout_is_logged(logstore, monkeypatch):
    """A run that overruns the wall-clock ceiling is abandoned and logged, not hung."""
    import time

    from app.main import app
    import app.api.features as features
    from app.services import simulation

    monkeypatch.setattr(features, "_SIM_TIMEOUT_SECS", 0.05)
    monkeypatch.setattr(simulation, "simulate", lambda *a, **k: time.sleep(0.5))
    client = TestClient(app)
    body = {"graph": {"steps": {}, "transitions": []}, "config": {"journeyCount": 100}}
    resp = client.post("/api/simulate", json=body)
    assert resp.status_code == 504
    entries = logstore.query(operation="simulation", severities=["ERROR"])
    assert entries and "timed out" in entries[0]["message"].lower()


# ── SQL execution error / timeout ─────────────────────────────────────────────


def _bare_manager(conn):
    from app.db import manager

    mgr = manager.DatabaseManager.__new__(manager.DatabaseManager)
    mgr._lock = threading.RLock()
    mgr._conn = conn
    return mgr


def test_sql_execution_error_is_logged_with_the_statement(logstore):
    class BoomConn:
        def execute(self, sql):
            raise RuntimeError("syntax error")

    mgr = _bare_manager(BoomConn())
    with pytest.raises(Exception):
        asyncio.run(mgr.execute("SELECT * FROMM widgets"))
    entries = logstore.query(operation="db-sql")
    assert entries
    assert "SELECT * FROMM widgets" in entries[0]["message"]  # SQL captured


def test_sql_timeout_is_logged(logstore):
    import time

    mgr = _bare_manager(conn=None)
    mgr._execute_sync = lambda sql: time.sleep(0.5)  # slower than the timeout
    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        asyncio.run(mgr.execute("SELECT 1", timeout=0.05))
    entries = logstore.query(operation="db-timeout")
    assert entries and "timed out" in entries[0]["message"].lower()


def test_execute_quiet_never_logs_expected_ddl_failures(logstore):
    class BoomConn:
        def execute(self, sql):
            raise RuntimeError("column already exists")

    mgr = _bare_manager(BoomConn())
    # Migrations run through execute_quiet — their failures are expected and silent.
    asyncio.run(mgr.execute_quiet("ALTER TABLE x ADD COLUMN y INT"))
    assert logstore.query(operation="db-sql") == []


# ── Database connection error ─────────────────────────────────────────────────


def test_database_connection_error_is_logged(logstore, monkeypatch):
    from app.db import manager

    mgr = manager.DatabaseManager.__new__(manager.DatabaseManager)
    mgr._lock = threading.RLock()
    mgr._conn = None
    mgr.active_profile_id = None
    mgr.is_connected = False
    mgr.is_llm_reachable = False
    mgr.last_error = None
    mgr._active_db_server = None
    mgr._active_llm_server = None

    def _boom(server, password):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(mgr, "_open", _boom)

    class ConnDef:
        id = "c1"
        name = "Prod"
        host = "db.example.com"
        port = 8563
        username = "svc"
        use_tls = False
        cert_mode = "verify"
        fingerprint = ""
        min_rsa_bits = 2048
        schema = "MINING"
        password = "pw"
        llm_url = ""
        llm_api_key = ""
        llm_model = ""

    msg = asyncio.run(mgr.connect_connection(ConnDef()))
    assert msg  # a friendly error string is returned to the caller
    entries = logstore.query(operation="db-connect")
    assert entries and "Database connection failed" in entries[0]["message"]
    assert "db.example.com" in entries[0]["message"]


def test_db_connection_test_failure_is_logged(logstore, monkeypatch):
    """The 'Test connection' probe (no DB connected) logs its failure too."""
    from app.db import manager

    def _boom(self, server, password):
        raise RuntimeError("authentication failed: invalid credentials")

    monkeypatch.setattr(manager.DatabaseManager, "_open", _boom)
    msg = asyncio.run(
        manager.test_db_connection(host="db.x", port=8563, username="u", password="")
    )
    assert msg  # a friendly error is returned to the UI
    entries = logstore.query(operation="db-test")
    assert entries
    assert "connection test failed" in entries[0]["message"].lower()
    assert "db.x" in entries[0]["message"]


def test_llm_connection_error_is_logged(logstore, monkeypatch):
    """An LLM reachability probe captures the real connection error before it is
    swallowed (covers Test buttons and connect, which all call check_llm_reachable)."""
    from app.db import manager
    from app.models import LLMServer

    # Loopback is SSRF-blocked by default; opt in so we exercise the real
    # connection-error path (port 1 refuses immediately).
    monkeypatch.setenv("PMW_ALLOW_PRIVATE_LLM_HOSTS", "1")
    server = LLMServer(id="x", name="n", serverURL="http://127.0.0.1:1/v1", apiKey="", model="")
    reachable = asyncio.run(manager.check_llm_reachable(server))
    assert reachable is False
    entries = logstore.query(operation="llm-test")
    assert entries
    assert "127.0.0.1:1" in entries[0]["message"]
    assert (
        "connection error" in entries[0]["message"].lower()
        or "not reachable" in entries[0]["message"].lower()
    )


def test_llm_ssrf_url_is_refused_and_logged(logstore):
    """A configured LLM URL pointing at cloud-metadata is refused before any fetch."""
    from app.db import manager
    from app.models import LLMServer

    server = LLMServer(
        id="x", name="n",
        serverURL="http://169.254.169.254/latest/meta-data/", apiKey="sk-secret", model="",
    )
    reachable = asyncio.run(manager.check_llm_reachable(server))
    assert reachable is False
    entries = logstore.query(operation="llm-test")
    assert entries and "ssrf guard" in entries[0]["message"].lower()
    assert "sk-secret" not in entries[0]["message"]  # the api key is never logged
