"""Unit tests for the notification-rule spec (the one place that defines what a rule may
contain): severity / interval / kind / config validation and the comparator predicates."""

from __future__ import annotations

import pytest

from app.notifications import spec


def test_severity_defaults_and_whitelist():
    assert spec.validate_severity("urgent") == "URGENT"
    assert spec.validate_severity("Important") == "IMPORTANT"
    assert spec.validate_severity("bogus") == spec.DEFAULT_SEVERITY
    assert spec.validate_severity(None) == spec.DEFAULT_SEVERITY


def test_interval_must_be_one_of_the_choices():
    assert spec.validate_interval(60) == 60
    assert spec.validate_interval(86400) == 86400
    assert spec.validate_interval(42) == spec.DEFAULT_INTERVAL  # not an offered interval
    assert spec.validate_interval("x") == spec.DEFAULT_INTERVAL


def test_kind_validation():
    assert spec.validate_kind("") == spec.DEFAULT_KIND
    assert spec.validate_kind("transition_metric") == "transition_metric"
    assert spec.validate_kind("journey_duration") == "journey_duration"
    assert spec.validate_kind("note") == "note"
    with pytest.raises(spec.RuleError):
        spec.validate_kind("teleport")


def test_note_config_roundtrip_and_defaults():
    cfg = spec.validate_config("note", {
        "event": "resolved", "minImportance": "important", "scope": "all",
        "lookbackUnit": "days", "lookbackValue": 7,
    })
    assert cfg == {
        "event": "resolved", "minImportance": "IMPORTANT", "scope": "all",
        "comparator": ">=", "threshold": 1, "lookbackUnit": "days", "lookbackValue": 7,
    }
    # Bad/blank values fall back to safe defaults.
    d = spec.validate_config("note", {})
    assert d["event"] == "created" and d["minImportance"] == "NORMAL" and d["scope"] == "shared"
    assert d["comparator"] == ">=" and d["threshold"] == 1 and d["lookbackUnit"] == "all"
    # "All open notes" ignores the window.
    openc = spec.validate_config("note", {"event": "open", "lookbackUnit": "days", "lookbackValue": 3})
    assert openc["event"] == "open" and openc["lookbackUnit"] == "all" and openc["lookbackValue"] == 0
    # Threshold is clamped to at least 1.
    assert spec.validate_config("note", {"threshold": 0})["threshold"] == 1


def test_transition_metric_config_roundtrip():
    cfg = spec.validate_config("transition_metric", {
        "fromStep": " A ", "toStep": "B", "metric": "Avg Time",
        "comparator": ">", "threshold": "7200",
    })
    assert cfg == {
        "fromStep": "A", "toStep": "B", "metric": "Avg Time",
        "comparator": ">", "threshold": 7200.0,
        "lookbackUnit": "all", "lookbackValue": 0,  # defaults
    }


def test_journey_duration_config_roundtrip():
    # No steps; a time aggregate of the whole case, with a lookback window.
    cfg = spec.validate_config("journey_duration", {
        "metric": "Max Time", "comparator": ">", "threshold": "7200",
        "lookbackUnit": "days", "lookbackValue": 30,
    })
    assert cfg == {
        "metric": "Max Time", "comparator": ">", "threshold": 7200.0,
        "lookbackUnit": "days", "lookbackValue": 30,
    }
    assert "fromStep" not in cfg and "toStep" not in cfg


@pytest.mark.parametrize("bad", [
    {"metric": "Count", "comparator": ">", "threshold": 1},   # Count isn't a duration metric
    {"metric": "Nope", "comparator": ">", "threshold": 1},
    {"metric": "Avg Time", "comparator": "~", "threshold": 1},
    {"metric": "Avg Time", "comparator": ">", "threshold": "nan-ish"},
])
def test_journey_duration_config_rejects_bad(bad):
    with pytest.raises(spec.RuleError):
        spec.validate_config("journey_duration", bad)


def test_lookback_validation_and_cutoff():
    from datetime import datetime

    now = datetime(2026, 3, 15, 12, 30, 0)
    # A valid window is kept.
    cfg = spec.validate_config("transition_metric", {
        "fromStep": "A", "toStep": "B", "metric": "Count", "comparator": ">", "threshold": 1,
        "lookbackUnit": "days", "lookbackValue": 7,
    })
    assert cfg["lookbackUnit"] == "days" and cfg["lookbackValue"] == 7
    assert spec.lookback_cutoff(cfg, now) == datetime(2026, 3, 8, 12, 30, 0)
    # Unknown unit or value < 1 collapses to "all" (no window).
    bad = spec.validate_config("transition_metric", {
        "fromStep": "A", "toStep": "B", "metric": "Count", "comparator": ">", "threshold": 1,
        "lookbackUnit": "weeks", "lookbackValue": 3,
    })
    assert bad["lookbackUnit"] == "all" and bad["lookbackValue"] == 0
    assert spec.lookback_cutoff(bad, now) is None
    # Minutes (sub-day) and calendar months/years.
    assert spec.lookback_cutoff({"lookbackUnit": "minutes", "lookbackValue": 30}, now) == \
        datetime(2026, 3, 15, 12, 0, 0)
    assert spec.lookback_cutoff({"lookbackUnit": "months", "lookbackValue": 2}, now) == \
        datetime(2026, 1, 15, 12, 30, 0)
    assert spec.lookback_cutoff({"lookbackUnit": "years", "lookbackValue": 1}, now) == \
        datetime(2025, 3, 15, 12, 30, 0)


@pytest.mark.parametrize("bad", [
    {"fromStep": "A", "toStep": "B", "metric": "Nope", "comparator": ">", "threshold": 1},
    {"fromStep": "A", "toStep": "B", "metric": "Count", "comparator": "~", "threshold": 1},
    {"fromStep": "A", "toStep": "B", "metric": "Count", "comparator": ">", "threshold": "nan-ish"},
    {"fromStep": "", "toStep": "B", "metric": "Count", "comparator": ">", "threshold": 1},
    {"fromStep": "A", "toStep": "", "metric": "Count", "comparator": ">", "threshold": 1},
])
def test_transition_metric_config_rejects_bad(bad):
    with pytest.raises(spec.RuleError):
        spec.validate_config("transition_metric", bad)


def test_comparators():
    assert spec.COMPARATORS[">"](5, 3) is True
    assert spec.COMPARATORS[">="](3, 3) is True
    assert spec.COMPARATORS["<"](2, 3) is True
    assert spec.COMPARATORS["<="](4, 3) is False


def test_comparators_tolerant_at_equality():
    # "> 17:00" must NOT fire on a value that is exactly the threshold, nor on float noise
    # (the kind an AVG/STDDEV can carry) — only a genuine excess triggers.
    assert spec.COMPARATORS[">"](1020.0, 1020.0) is False
    assert spec.COMPARATORS[">"](1020.0000001, 1020.0) is False
    assert spec.COMPARATORS[">"](1021.0, 1020.0) is True
    # The "at least / at most" variants DO fire at equality.
    assert spec.COMPARATORS[">="](1020.0, 1020.0) is True
    assert spec.COMPARATORS["<="](1020.0, 1020.0) is True
    # Strict "<" is symmetric: not at equality / noise, yes for a genuine shortfall.
    assert spec.COMPARATORS["<"](1020.0, 1020.0) is False
    assert spec.COMPARATORS["<"](1019.9999999, 1020.0) is False
    assert spec.COMPARATORS["<"](1019.0, 1020.0) is True


def test_severity_rank_orders_urgent_highest():
    assert spec.SEVERITY_RANK["URGENT"] > spec.SEVERITY_RANK["IMPORTANT"] > spec.SEVERITY_RANK["INFO"]


def test_validate_delivery_channels():
    assert spec.validate_delivery({}) == {}
    assert spec.validate_delivery({"webpush": True}) == {"webpush": True}
    assert spec.validate_delivery({"webpush": False}) == {}
    # SMTP carries a cleaned recipient list (bad addresses dropped).
    out = spec.validate_delivery({"smtp": {"recipients": ["a@b.com", "nope", " c@d.co ", ""]}})
    assert out == {"smtp": {"recipients": ["a@b.com", "c@d.co"]}}
    # SMTP enabled with no recipients is still on (→ connection users at send time).
    assert spec.validate_delivery({"smtp": {"recipients": []}}) == {"smtp": {"recipients": []}}
    # Both channels together.
    both = spec.validate_delivery({"webpush": True, "smtp": {"recipients": ["x@y.z"]}})
    assert both == {"webpush": True, "smtp": {"recipients": ["x@y.z"]}}
