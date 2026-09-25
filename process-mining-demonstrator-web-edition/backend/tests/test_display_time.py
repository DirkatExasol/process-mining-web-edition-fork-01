"""Server-created timestamps follow the Admin Console display zone.

Regression: a note's created date was stored as the browser's UTC clock while its
edited date came from the database clock (local), so get_notes showed 10:34 created /
12:36 edited for a note edited two minutes after creation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app.timeutil as tu
from app.integration import sink_ingest

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture
def berlin(monkeypatch):
    import app.store.security as sec

    monkeypatch.setattr(sec, "store", SimpleNamespace(display_timezone="Europe/Berlin"))
    return BERLIN


def test_display_zone_follows_the_admin_setting(berlin):
    assert tu.display_zone() == BERLIN


def test_display_zone_empty_means_server_local(monkeypatch):
    import app.store.security as sec

    monkeypatch.setattr(sec, "store", SimpleNamespace(display_timezone=""))
    assert tu.display_zone() is None


def test_local_now_is_naive_wall_clock_in_the_display_zone(berlin):
    now = tu.local_now()
    expected = datetime.now(BERLIN).replace(tzinfo=None)
    assert now.tzinfo is None
    assert abs((now - expected).total_seconds()) < 5
    assert now.microsecond % 1000 == 0          # millisecond precision, like _ts()


def test_to_local_converts_aware_and_keeps_naive(berlin):
    assert tu.to_local(datetime(2026, 9, 23, 10, 34, 45, tzinfo=timezone.utc)) == datetime(2026, 9, 23, 12, 34, 45)
    naive = datetime(2026, 9, 23, 12, 0)
    assert tu.to_local(naive) is naive


def test_local_iso_reports_the_zone_offset(berlin):
    assert tu.local_iso(datetime(2026, 9, 23, 12, 34, 45, 691000)) == "2026-09-23T12:34:45+02:00"
    assert tu.local_iso(datetime(2026, 1, 15, 9, 0)) == "2026-01-15T09:00:00+01:00"   # winter
    assert tu.local_iso(None) is None


def test_created_and_edited_now_agree(berlin):
    """Both stamps come from the same clock now — two minutes apart stays two minutes."""
    created = tu.local_now()
    edited = tu.local_now()
    assert timedelta(0) <= edited - created < timedelta(seconds=1)


def test_sink_event_time_defaults_to_local_now(berlin):
    got = sink_ingest._parse_time(None)
    expected = datetime.now(BERLIN).replace(tzinfo=None, microsecond=0)
    assert abs((got - expected).total_seconds()) < 5 and got.microsecond == 0


def test_sink_event_time_with_offset_is_converted_to_local(berlin):
    assert sink_ingest._parse_time("2026-09-23T10:00:00Z") == datetime(2026, 9, 23, 12, 0)
    assert sink_ingest._parse_time("2026-09-23T10:00:00+01:00") == datetime(2026, 9, 23, 11, 0)


def test_sink_event_time_without_offset_is_kept_as_wall_clock(berlin):
    assert sink_ingest._parse_time("2026-09-13T10:00:00") == datetime(2026, 9, 13, 10, 0)


def test_note_comment_stamp_uses_local_time(monkeypatch):
    import app.services.notes as notes

    monkeypatch.setattr(notes, "local_now", lambda: datetime(2026, 9, 23, 12, 36, 42))
    block = notes.comment_block("Dirk", "done", "Fixed")
    assert block == "—— Fixed · Dirk · 2026-09-23 12:36 ——\ndone\n\n"
