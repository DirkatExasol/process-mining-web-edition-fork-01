"""Background demo-event generator — the pure, DB-free helpers (SQL row building, meta
sampling, event-id hashing). The module lives at generator/launch.py (a sibling tool),
loaded by path like the MCP server test does."""
from __future__ import annotations

import importlib.util
import random
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

_PATH = Path(__file__).resolve().parents[2] / "generator" / "launch.py"
_spec = importlib.util.spec_from_file_location("pm_generator", _PATH)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _ev(step: str, t: datetime):
    return SimpleNamespace(step=step, timestamp=t)


def test_md5_event_id_is_32_hex():
    eid = gen._md5_event_id()
    assert len(eid) == 32 and all(c in "0123456789abcdef" for c in eid)
    assert gen._md5_event_id() != gen._md5_event_id()  # unique per call


def test_insert_sql_builds_rows_escapes_and_targets_the_project():
    events = [_ev("Login", datetime(2026, 10, 4, 9, 0, 0)),
              _ev("O'Brien", datetime(2026, 10, 4, 9, 5, 0))]
    step_ids = {"Login": 1, "O'Brien": 2}
    sql = gen._insert_sql(7, "abc123", events, step_ids, ("EU", "Gold", "Web"))
    assert sql is not None
    assert sql.startswith("INSERT INTO JOURNEYS (PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME,")
    assert "(7, 'abc123', 'Login', 1, TIMESTAMP '2026-10-04 09:00:00', 'EU', 'Gold', 'Web', 'ORIGINAL')" in sql
    assert "'O''Brien'" in sql                      # single quote escaped
    assert sql.count("TIMESTAMP '") == 2            # one row per event


def test_insert_sql_skips_steps_without_an_activity_id():
    events = [_ev("Login", datetime(2026, 10, 4, 9, 0, 0)),
              _ev("Unknown", datetime(2026, 10, 4, 9, 1, 0))]
    sql = gen._insert_sql(1, "e", events, {"Login": 1}, ("", "", ""))
    assert sql is not None and sql.count("TIMESTAMP '") == 1   # only the known step written


def test_insert_sql_returns_none_when_no_rows():
    events = [_ev("Unknown", datetime(2026, 10, 4, 9, 0, 0))]
    assert gen._insert_sql(1, "e", events, {"Login": 1}, ("", "", "")) is None


def test_meta_sampler_draws_from_weighted_triples():
    s = gen._MetaSampler([(("EU", "Gold", "Web"), 90), (("US", "Silver", "App"), 10)])
    rng = random.Random(0)
    picks = [s.sample(rng) for _ in range(400)]
    assert all(p in {("EU", "Gold", "Web"), ("US", "Silver", "App")} for p in picks)
    eu = sum(1 for p in picks if p[0] == "EU")
    assert eu > 300                                 # ~90% weight dominates


def test_meta_sampler_defaults_to_empty_triple_when_no_data():
    assert gen._MetaSampler([]).sample(random.Random(1)) == ("", "", "")


def test_env_helpers_parse_and_fall_back(monkeypatch):
    monkeypatch.delenv("X", raising=False)
    assert gen._env_int("X", 7) == 7            # unset → default
    assert gen._env_float("X", 1.5) == 1.5
    assert gen._env_bool("X", True) is True
    monkeypatch.setenv("X", "")
    assert gen._env_int("X", 7) == 7            # blank → default
    monkeypatch.setenv("X", "nope")
    assert gen._env_int("X", 7) == 7            # unparseable → default (never crashes)
    monkeypatch.setenv("X", "42")
    assert gen._env_int("X", 7) == 42
    for v in ("1", "true", "YES", "on"):
        monkeypatch.setenv("X", v)
        assert gen._env_bool("X", False) is True
    for v in ("0", "false", "off", "no"):
        monkeypatch.setenv("X", v)
        assert gen._env_bool("X", True) is False


def test_args_are_fully_driven_by_env(monkeypatch):
    # Every parameter can come from a PMG_* variable, so the container needs no CLI args.
    env = {
        "PMG_HOST": "db", "PMG_PORT": "9000", "PMG_USER": "u", "PMG_PASSWORD": "p",
        "PMG_SCHEMA": "PM_PROD", "PMG_PROJECT": "1", "PMG_TARGET_PROJECT": "2",
        "PMG_MIN": "3", "PMG_MAX": "9", "PMG_MAX_STEPS": "40", "PMG_COUNT": "10",
        "PMG_TLS": "false", "PMG_INSECURE": "true", "PMG_SEED": "5",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr("sys.argv", ["launch.py"])
    a = gen._args()
    assert (a.host, a.port, a.user, a.password, a.schema) == ("db", 9000, "u", "p", "PM_PROD")
    assert a.project == 1 and a.target_project == 2 and a.max_steps == 40 and a.count == 10
    assert a.min == 3.0 and a.max == 9.0 and a.tls is False and a.insecure is True and a.seed == 5
