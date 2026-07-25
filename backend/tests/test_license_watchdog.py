"""The compute-backend license watchdog: one-time demo window and shutdown."""

from __future__ import annotations

import asyncio

import pytest

from app import licensing, main


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    # Keep the loop tight so tests don't wait real seconds.
    monkeypatch.setattr(main, "_LICENSE_POLL_SECS", 0.01)


@pytest.fixture(autouse=True)
def isolate_marker(monkeypatch, tmp_path):
    # Every test gets its own demo marker so the one-time window can't leak across.
    monkeypatch.setattr(licensing, "DEMO_MARKER_PATH", tmp_path / "demo_grace.json")


def _status(state: str) -> licensing.LicenseStatus:
    return licensing.LicenseStatus(state, message=f"{state} for test")


@pytest.mark.asyncio
async def test_demo_window_stops_after_grace(monkeypatch):
    monkeypatch.setattr(main, "LICENSE_GRACE_SECS", 0)  # zero-length demo window
    monkeypatch.setattr(licensing, "LICENSE_GRACE_SECS", 0)
    monkeypatch.setattr(licensing, "evaluate", lambda: _status("missing"))

    killed: list = []
    monkeypatch.setattr(main, "_stop_backend", lambda: killed.append(True))

    await asyncio.wait_for(main._license_watchdog(), timeout=2)
    assert killed, "watchdog should have stopped the backend once the demo is spent"


@pytest.mark.asyncio
async def test_spent_demo_gives_no_new_window(monkeypatch, tmp_path):
    """A restart after the demo is used gets no fresh grace — it stops at once."""
    # Pre-write a marker whose deadline is already in the past.
    from datetime import datetime, timedelta, timezone

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    (tmp_path / "demo_grace.json").write_text(
        f'{{"started": "x", "deadline": "{past}"}}'
    )
    monkeypatch.setattr(licensing, "evaluate", lambda: _status("expired"))

    killed: list = []
    monkeypatch.setattr(main, "_stop_backend", lambda: killed.append(True))

    await asyncio.wait_for(main._license_watchdog(), timeout=2)
    assert killed


@pytest.mark.asyncio
async def test_valid_license_never_stops(monkeypatch):
    monkeypatch.setattr(licensing, "evaluate", lambda: _status("valid"))

    killed: list = []
    monkeypatch.setattr(main, "_stop_backend", lambda: killed.append(True))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(main._license_watchdog(), timeout=0.2)
    assert not killed


@pytest.mark.asyncio
async def test_applying_a_license_mid_demo_cancels_shutdown(monkeypatch):
    # Long demo window so the deadline never hits during the test.
    monkeypatch.setattr(main, "LICENSE_GRACE_SECS", 10_000)
    monkeypatch.setattr(licensing, "LICENSE_GRACE_SECS", 10_000)

    states = iter(["missing", "missing", "valid", "valid", "valid"])
    monkeypatch.setattr(licensing, "evaluate", lambda: _status(next(states, "valid")))

    killed: list = []
    monkeypatch.setattr(main, "_stop_backend", lambda: killed.append(True))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(main._license_watchdog(), timeout=0.2)
    assert not killed
