"""File-source watchdog: it imports only newly-appended lines and advances the per-file
checkpoint. The destination connection open is stubbed, so no database is needed — the
generated SQL is captured to prove the incremental JOURNEYS writes happened."""

from __future__ import annotations

import asyncio
import importlib
import json

import pytest

FIELDS = [
    {"name": "timestamp", "role": "timestamp",
     "regex": r"\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\]"},
    {"name": "event_id", "role": "id", "regex": r"userId=(\d+)"},
    {"name": "step", "role": "step", "regex": r'"[A-Z]+ /shop/([a-z]+)'},
]
LINE_A = ('10.0.0.1 - - [09/Jan/2015:19:12:14 +0000] 15233 '
          '"GET /shop/view?userId=20253471 HTTP/1.1" 200 8241 "-" "UA"')
LINE_B = ('10.0.0.2 - - [09/Jan/2015:19:12:52 +0000] 7994 '
          '"POST /shop/basket?userId=44189320 HTTP/1.1" 200 341 "-" "UA"')
LINE_C = ('10.0.0.3 - - [09/Jan/2015:19:13:10 +0000] 1020 '
          '"POST /shop/pay?userId=44189320 HTTP/1.1" 200 12 "-" "UA"')


@pytest.fixture
def wd_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PMW_INTEGRATION_FILES_DIR", str(tmp_path / "files"))
    monkeypatch.delenv("PMW_INTEGRATION_ALLOW_ANY_PATH", raising=False)

    import app.config as config
    importlib.reload(config)
    import app.store.crypto as crypto
    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security
    import app.store.security as security_mod
    importlib.reload(security_mod)
    import app.integration.files as files_mod
    importlib.reload(files_mod)
    import app.integration.extractors as extractors_mod
    importlib.reload(extractors_mod)
    import app.integration.watchdog as wd
    importlib.reload(wd)

    return config, security_mod.store, wd


def _seed(config, store):
    """A developer with a File source (watchdog on) → a stored connection + source type."""
    store.create_user("dev", "pw", is_admin=False)
    store.set_developer("dev", True)
    conn = store.upsert_connection({
        "name": "Prod", "host": "db", "port": 8563, "username": "svc",
        "schema": "MINING", "password": "s3cret", "owner": "dev", "assignments": ["dev"],
    })
    st = store.add_source_type("dev", name="Apache", config=json.dumps({"sample": "", "fields": FIELDS}))
    (config.INTEGRATION_FILES_DIR / "live.log").write_text(LINE_A + "\n" + LINE_B + "\n")
    source = store.add_source("dev", name="Live log", kind="file", config=json.dumps({
        "path": "live.log", "encoding": "utf-8", "sourceTypeId": st.id,
        "watchdog": {"enabled": True, "connectionId": conn.id, "projectId": "LIVE", "intervalSecs": 5},
    }))
    return source, conn, st


def test_watchdog_imports_only_new_lines_and_advances_checkpoint(wd_env, monkeypatch):
    config, store, wd = wd_env
    source, _, _ = _seed(config, store)

    captured: list[str] = []

    class _Raw:
        def commit(self): pass
        def close(self): pass

    def _fake_open(conn):
        def run_sql(sql: str):
            captured.append(sql)
            return []  # existing_keys → empty; DDL/INSERT → no rows

        return _Raw(), run_sql

    monkeypatch.setattr(wd, "_open_run_sql", _fake_open)

    # First poll: both existing lines import; the checkpoint advances past them.
    asyncio.run(wd.poll_source(source))
    cp = store.get_source_checkpoint(source.id)
    assert cp is not None and cp["records"] == 2 and cp["lastError"] is None
    assert cp["byteOffset"] > 0
    assert any("INSERT INTO" in s and "JOURNEYS" in s for s in captured)
    off1 = cp["byteOffset"]

    # The file grows by one line. The interval gate would skip it, so force "due".
    monkeypatch.setattr(wd, "_due", lambda *a, **k: True)
    with (config.INTEGRATION_FILES_DIR / "live.log").open("a") as fh:
        fh.write(LINE_C + "\n")

    asyncio.run(wd.poll_source(source))
    cp2 = store.get_source_checkpoint(source.id)
    # Only the ONE new line was imported (2 → 3), and the offset moved forward.
    assert cp2["records"] == 3
    assert cp2["byteOffset"] > off1


def test_watchdog_records_error_without_advancing_offset(wd_env, monkeypatch):
    config, store, wd = wd_env
    source, _, _ = _seed(config, store)

    def _boom(conn):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(wd, "_open_run_sql", _boom)
    asyncio.run(wd.poll_source(source))
    cp = store.get_source_checkpoint(source.id)
    assert cp["records"] == 0 and cp["byteOffset"] == 0
    assert cp["lastError"] and "connection refused" in cp["lastError"]


def test_watchdog_ignores_sources_with_the_watchdog_off(wd_env, monkeypatch):
    config, store, wd = wd_env
    source, conn, st = _seed(config, store)
    # Turn the watchdog off.
    store.update_source(source.id, "dev", name="Live log", kind="file", config=json.dumps({
        "path": "live.log", "encoding": "utf-8", "sourceTypeId": st.id,
        "watchdog": {"enabled": False, "connectionId": conn.id, "projectId": "LIVE", "intervalSecs": 5},
    }))
    off = store.list_sources("dev")[0]
    monkeypatch.setattr(wd, "_open_run_sql", lambda c: (_ for _ in ()).throw(AssertionError("should not open")))
    asyncio.run(wd.poll_source(off))
    assert store.get_source_checkpoint(off.id) is None  # never touched
