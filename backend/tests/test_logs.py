"""Tests for the shared structured LogStore (app.store.logs)."""

from __future__ import annotations

import os

import pytest

from app.store.logs import LEVELS, LogStore, format_line


@pytest.fixture
def logs(tmp_path, monkeypatch):
    # Isolate the rotation archive directory to the temp dir (LOGS_DIR is otherwise
    # the developer's real data/logs).
    import app.store.logs as logs_mod

    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    monkeypatch.setattr(logs_mod, "LOGS_DIR", archive_dir)
    return LogStore(path=tmp_path / "logs.sqlite3")


def _sevs(store):
    return [e["severity"] for e in store.query(severities=list(LEVELS), limit=100)]


def test_severity_ladder_is_cumulative(logs):
    assert logs.level == "ERROR"  # default: INFO+USAGE+WARN+ERROR, not DEBUG
    for sev in LEVELS:
        logs.record(sev, f"{sev} message")
    # DEBUG (rank above ERROR) is dropped at the default level.
    recorded = set(_sevs(logs))
    assert recorded == {"INFO", "USAGE", "WARN", "ERROR"}

    # Raising the max level to DEBUG records everything.
    logs.set_level("DEBUG")
    logs.record("DEBUG", "now on")
    assert "DEBUG" in _sevs(logs)

    # Lowering to INFO records only INFO.
    logs.set_level("INFO")
    logs.record("USAGE", "should be dropped")
    logs.record("INFO", "kept")
    assert not any(
        e["message"] == "should be dropped" for e in logs.query(limit=100)
    )


def test_newest_first_and_format(logs):
    logs.record("USAGE", "first", client_ip="1.1.1.1", username="alice", operation="login")
    logs.record("WARN", "second", client_ip="2.2.2.2", username="bob", operation="logout")
    entries = logs.query(limit=10)
    assert [e["message"] for e in entries] == ["second", "first"]  # youngest on top
    top = entries[0]
    assert set(top) >= {"date", "time", "severity", "clientIp", "user", "operation", "message"}


def test_format_line_matches_the_spec(logs):
    logs.record("ERROR", "boom", client_ip="9.9.9.9", username="carol")
    row = logs._conn.execute(
        "SELECT ts, severity, client_ip, username, operation, message FROM log_entries"
    ).fetchone()
    line = format_line(row)
    parts = line.split(" -- ")
    # DATE -- TIME -- SEVERITY -- CLIENT-IP -- USER -- text
    assert len(parts) == 6
    assert parts[2] == "ERROR" and parts[3] == "9.9.9.9" and parts[4] == "carol"
    assert parts[5] == "boom"


def test_filters_severity_ip_operation(logs):
    logs.set_level("DEBUG")
    logs.record("USAGE", "login a", client_ip="10.0.0.1", username="a", operation="login")
    logs.record("USAGE", "logout a", client_ip="10.0.0.1", username="a", operation="logout")
    logs.record("ERROR", "err x", client_ip="10.0.0.9", operation="error")

    assert len(logs.query(severities=["ERROR"])) == 1
    assert {e["message"] for e in logs.query(operation="login")} == {"login a"}
    assert len(logs.query(client_ip="10.0.0.1")) == 2  # LIKE substring
    # 'level' includes everything up to it in the ladder.
    assert len(logs.query(level="USAGE")) == 2  # INFO+USAGE only → both USAGE rows


def test_count_and_paging(logs):
    logs.set_level("DEBUG")
    for i in range(23):
        logs.record("INFO", f"row {i:02d}", operation="page")
    logs.record("ERROR", "the needle", operation="error")  # 24 total

    assert logs.count() == 24
    # count() honours the same filter as query() (search spans the whole store).
    assert logs.count(operation="error") == 1
    assert logs.count(search="needle") == 1

    # Page 1 of 10 → newest 10; offsets slice the same newest-first ordering.
    p1 = logs.query(limit=10, offset=0)
    p2 = logs.query(limit=10, offset=10)
    p3 = logs.query(limit=10, offset=20)
    assert [len(p) for p in (p1, p2, p3)] == [10, 10, 4]
    assert p1[0]["message"] == "the needle"  # newest first
    # No overlap and full coverage across pages.
    seen = [e["message"] for e in (*p1, *p2, *p3)]
    assert len(seen) == len(set(seen)) == 24


def test_search_is_redos_bounded(logs):
    """A catastrophic-backtracking pattern must not hang the log search."""
    import time

    from app.store import logs as logs_mod

    logs.set_level("DEBUG")
    logs.record("INFO", "a" * 60 + "b")  # bait for (a|a)*$ style blowup

    start = time.perf_counter()
    logs.query(search="(a|a)*$")  # would run for aeons unbounded
    elapsed = time.perf_counter() - start
    # Bounded by the per-match timeout (or the length cap), well under a second.
    assert elapsed < max(2.0, logs_mod._SEARCH_TIMEOUT_SECS * 4)

    # An over-long pattern degrades to a safe literal match rather than compiling.
    huge = "(a+)+" * 200
    assert len(huge) > logs_mod._MAX_SEARCH_PATTERN
    assert logs.query(search=huge) == []  # no literal match, no hang


def test_regex_search(logs):
    logs.set_level("DEBUG")
    logs.record("USAGE", "user alice signed in")
    logs.record("USAGE", "user bob signed out")
    logs.record("WARN", "failed sign-in for 'eve'")

    assert {e["message"] for e in logs.query(search="signed in")} == {"user alice signed in"}
    assert len(logs.query(search="sign")) == 3
    assert len(logs.query(search="^user ")) == 2  # anchored regex
    # An invalid regex falls back to a literal substring match (never errors).
    assert len(logs.query(search="[unclosed")) == 0


def test_rotation_writes_archive_and_empties_store(logs):
    logs.set_level("DEBUG")
    logs.set_max_bytes(50_000)  # clamped minimum
    for i in range(800):
        logs.record("USAGE", "padding entry number %04d " % i + "x" * 60, client_ip="1.2.3.4")
    # The live store was rotated (fewer than all 800 remain).
    assert len(logs.query(limit=10_000)) < 800
    import app.store.logs as logs_mod

    archives = [f for f in os.listdir(logs_mod.LOGS_DIR) if f.endswith(".log")]
    assert archives, "expected a rotated .log archive"
    # Archive is newest-first and in the spec format.
    text = (logs_mod.LOGS_DIR / archives[0]).read_text()
    lines = text.splitlines()
    assert " -- " in lines[0] and len(lines[0].split(" -- ")) == 6


def test_store_enables_busy_timeout(logs):
    # A cross-process log write must retry rather than fail immediately on SQLITE_BUSY.
    assert logs._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_log_rows_render_in_the_display_timezone():
    """Stored UTC-epoch timestamps render in the configured display timezone (the
    admin timezone setting) for both the viewer dict and the exported .log line."""
    import app.store.logs as logs_mod
    from datetime import datetime, timezone

    from app import timeutil

    ts = datetime(2026, 7, 29, 0, 30, tzinfo=timezone.utc).timestamp()  # 00:30 UTC
    row = {"ts": ts, "severity": "INFO", "client_ip": "1.2.3.4",
           "username": "u", "operation": "op", "message": "hi"}
    try:
        logs_mod.set_display_timezone(timeutil.resolve_zone("Europe/Berlin"))
        d = logs_mod._row_to_dict(row)
        assert d["date"] == "2026-07-29" and d["time"] == "02:30:00"  # CEST = UTC+2
        assert "2026-07-29 -- 02:30:00" in logs_mod.format_line(row)
        logs_mod.set_display_timezone(timeutil.resolve_zone("America/New_York"))
        assert logs_mod._row_to_dict(row)["date"] == "2026-07-28"  # 20:30 prev day
    finally:
        logs_mod.set_display_timezone(None)


def test_rotation_prunes_to_newest_archives(logs):
    import app.store.logs as logs_mod

    # Seed more archives than the retention cap; timestamped names sort chronologically.
    for i in range(logs_mod._MAX_ARCHIVES + 5):
        (logs_mod.LOGS_DIR / f"pmw-20260101-0000{i:02d}.log").write_text("x\n")
    logs._prune_archives()
    remaining = sorted(p.name for p in logs_mod.LOGS_DIR.glob("pmw-*.log"))
    assert len(remaining) == logs_mod._MAX_ARCHIVES  # only the newest N survive
    assert remaining[-1] == f"pmw-20260101-0000{logs_mod._MAX_ARCHIVES + 4:02d}.log"
    # The oldest were the ones deleted.
    assert "pmw-20260101-000000.log" not in remaining


def test_config_clamps_and_round_trips(logs):
    logs.set_level("bogus")  # invalid → default
    assert logs.level == "ERROR"
    logs.set_level("warn")  # case-insensitive
    assert logs.level == "WARN"
    logs.set_max_bytes(10)  # below the floor
    assert logs.max_bytes >= 50_000
    cfg = logs.config()
    assert cfg["levels"] == list(LEVELS) and cfg["level"] == "WARN"


def test_client_ip_extraction():
    from app import log_events as logx

    class _Req:
        def __init__(self, headers, host):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    # X-Forwarded-For wins and the first hop is used.
    assert logx.client_ip(_Req({"x-forwarded-for": "9.9.9.9, 1.1.1.1"}, "127.0.0.1")) == "9.9.9.9"
    # Falls back to the socket peer.
    assert logx.client_ip(_Req({}, "5.5.5.5")) == "5.5.5.5"
    # Never raises on a missing request.
    assert logx.client_ip(None) == ""


def test_record_strips_control_chars_to_prevent_log_forgery(logs):
    logs.set_level("DEBUG")
    logs.record(
        "WARN",
        "real\n2099-01-01 -- 00:00:00 -- ERROR -- 9.9.9.9 -- root -- FORGED",
        username="a\r\nb",
        operation="op",
    )
    entry = logs.query()[0]
    assert "\n" not in entry["message"] and "\r" not in entry["message"]
    assert "\n" not in entry["user"] and "\r" not in entry["user"]
    # The exported form is a single line per entry (no forged extra line).
    assert logs.render().count("\n") == 1
