"""Unit tests for the dependency-free cron matcher used by scheduled backups."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services import cron


def test_daily_match():
    assert cron.matches("30 2 * * *", datetime(2026, 7, 28, 2, 30))
    assert not cron.matches("30 2 * * *", datetime(2026, 7, 28, 2, 31))
    assert not cron.matches("30 2 * * *", datetime(2026, 7, 28, 3, 30))


def test_hourly_and_step():
    assert cron.matches("0 * * * *", datetime(2026, 7, 28, 13, 0))
    assert cron.matches("*/15 * * * *", datetime(2026, 7, 28, 9, 45))
    assert not cron.matches("*/15 * * * *", datetime(2026, 7, 28, 9, 44))


def test_weekly_uses_cron_sunday_zero():
    # 2026-07-27 is a Monday, 2026-08-02 is a Sunday.
    assert cron.matches("0 3 * * 1", datetime(2026, 7, 27, 3, 0))  # Monday
    assert not cron.matches("0 3 * * 1", datetime(2026, 7, 28, 3, 0))  # Tuesday
    assert cron.matches("0 0 * * 0", datetime(2026, 8, 2, 0, 0))  # Sunday=0
    assert cron.matches("0 0 * * 7", datetime(2026, 8, 2, 0, 0))  # 7 also = Sunday


def test_monthly_day_of_month():
    assert cron.matches("0 4 1 * *", datetime(2026, 8, 1, 4, 0))
    assert not cron.matches("0 4 1 * *", datetime(2026, 8, 2, 4, 0))


def test_dom_and_dow_both_restricted_is_or():
    # Vixie cron: when both DOM and DOW are set, match on EITHER. 2026-08-03 is Monday.
    expr = "0 0 1 * 1"  # 1st of month OR any Monday
    assert cron.matches(expr, datetime(2026, 8, 1, 0, 0))  # the 1st (a Saturday)
    assert cron.matches(expr, datetime(2026, 8, 3, 0, 0))  # a Monday, not the 1st
    assert not cron.matches(expr, datetime(2026, 8, 4, 0, 0))  # neither


def test_list_and_range():
    assert cron.matches("0 9,17 * * *", datetime(2026, 7, 28, 17, 0))
    assert cron.matches("0 9-17 * * *", datetime(2026, 7, 28, 12, 0))
    assert not cron.matches("0 9-17 * * *", datetime(2026, 7, 28, 18, 0))


@pytest.mark.parametrize(
    "bad",
    ["", "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *",
     "0 0 0 * *", "0 0 32 * *", "0 0 * 13 *", "* * * * 8", "a * * * *", "5-2 * * * *"],
)
def test_validate_rejects_bad(bad):
    with pytest.raises(ValueError):
        cron.validate(bad)


def test_validate_accepts_good():
    for good in ["0 2 * * *", "*/15 * * * *", "0 0 1 * *", "0 3 * * 1", "30 8,20 * * 1-5"]:
        cron.validate(good)  # no raise
