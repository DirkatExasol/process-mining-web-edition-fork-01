"""Unit tests for the shared per-IP sign-in throttle (app.services.login_throttle)."""

from __future__ import annotations

from app.services.login_throttle import LoginThrottle


class _Req:
    def __init__(self, host):
        self.client = type("C", (), {"host": host})()


def test_trips_after_max_failures_then_recovers(monkeypatch):
    import app.services.login_throttle as mod
    t = LoginThrottle(max_fails=3, window=900.0, cooldown=300.0)
    now = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])

    for _ in range(3):
        assert t.retry_after("1.2.3.4") == 0.0
        t.record_failure("1.2.3.4")
    # Tripped: must now wait out the cooldown from the last failure.
    assert t.retry_after("1.2.3.4") == 300.0
    now[0] += 299
    assert 0.0 < t.retry_after("1.2.3.4") <= 1.0
    now[0] += 2  # past the cooldown
    assert t.retry_after("1.2.3.4") == 0.0


def test_failures_age_out_of_the_window(monkeypatch):
    import app.services.login_throttle as mod
    t = LoginThrottle(max_fails=3, window=900.0, cooldown=300.0)
    now = [0.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
    for _ in range(3):
        t.record_failure("ip")
    now[0] += 901  # the whole window has elapsed
    assert t.retry_after("ip") == 0.0
    assert "ip" not in t.fails  # pruned


def test_clear_forgets_an_ip(monkeypatch):
    import app.services.login_throttle as mod
    t = LoginThrottle(max_fails=1, cooldown=300.0)
    monkeypatch.setattr(mod.time, "monotonic", lambda: 0.0)
    t.record_failure("ip")
    assert t.retry_after("ip") > 0
    t.clear("ip")
    assert t.retry_after("ip") == 0.0


def test_per_ip_isolation():
    t = LoginThrottle(max_fails=1)
    t.record_failure("a")
    assert t.retry_after("a") > 0
    assert t.retry_after("b") == 0.0  # a different host is unaffected


def test_map_is_bounded(monkeypatch):
    import app.services.login_throttle as mod
    t = LoginThrottle(max_tracked=100)
    monkeypatch.setattr(mod.time, "monotonic", lambda: 0.0)
    for i in range(500):
        t.record_failure(f"10.0.{i // 256}.{i % 256}")
    assert len(t.fails) <= 100


def test_client_ip_falls_back_when_unknown():
    assert LoginThrottle.client_ip(_Req("9.9.9.9")) == "9.9.9.9"
    assert LoginThrottle.client_ip(type("R", (), {"client": None})()) == "unknown"
