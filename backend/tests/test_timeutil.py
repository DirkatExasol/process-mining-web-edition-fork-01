"""Tests for the display-timezone resolver (admin timezone setting)."""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo

from app import timeutil


def test_resolve_zone():
    assert timeutil.resolve_zone("") is None  # empty → server-local
    assert timeutil.resolve_zone(None) is None
    assert isinstance(timeutil.resolve_zone("Europe/Berlin"), tzinfo)
    assert isinstance(timeutil.resolve_zone("UTC"), tzinfo)
    assert timeutil.resolve_zone("Not/AZone") is None  # unknown → fall back, never raise


def test_is_valid_zone():
    assert timeutil.is_valid_zone("") is True  # server-local is allowed
    assert timeutil.is_valid_zone("UTC") is True
    assert timeutil.is_valid_zone("America/New_York") is True
    assert timeutil.is_valid_zone("Mars/Base") is False
    assert timeutil.is_valid_zone("garbage") is False


def test_conversion_is_correct_for_a_known_instant():
    inst = datetime(2026, 7, 29, 0, 30, tzinfo=timezone.utc)  # 00:30 UTC, July → CEST
    assert inst.astimezone(timeutil.resolve_zone("Europe/Berlin")).strftime("%H:%M") == "02:30"
    ny = inst.astimezone(timeutil.resolve_zone("America/New_York"))
    assert ny.strftime("%Y-%m-%d %H:%M") == "2026-07-28 20:30"  # prev day, EDT (UTC-4)
