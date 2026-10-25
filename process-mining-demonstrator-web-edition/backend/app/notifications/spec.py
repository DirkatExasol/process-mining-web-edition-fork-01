"""Shared definitions for dashboard notification rules — the one place that says what a
rule may contain, so the REST API, the MCP tool and the engine agree.

A rule has a `kind` that selects the check type. Only ``transition_metric`` exists today
(a metric on the transition from one step to a following one), but the validation and the
engine are structured as a per-kind registry so new kinds slot in without touching the
schema or the callers: add a validator here and an evaluator in ``engine.py``.
"""

from __future__ import annotations

import calendar
import math
from datetime import datetime, timedelta

from ..models import TransitionMetric

# Severities, highest urgency first — the Dashboard sorts triggered notifications by this
# order, then by time. A subset of the note importance levels (a notification is always at
# least informational).
SEVERITIES: tuple[str, ...] = ("URGENT", "IMPORTANT", "INFO")
SEVERITY_RANK: dict[str, int] = {s: len(SEVERITIES) - i for i, s in enumerate(SEVERITIES)}
DEFAULT_SEVERITY = "IMPORTANT"

# Check intervals offered in the wizard (seconds): 1m, 5m, 15m, 1h, 2h, 5h, 1d.
INTERVAL_CHOICES: tuple[int, ...] = (60, 300, 900, 3600, 7200, 18000, 86400)
DEFAULT_INTERVAL = 300

# Comparators the criteria may use, as name -> predicate(measured, threshold).
#
# The comparison is tolerant of tiny floating-point differences: a measured value that is
# only ~1e-9 away from the threshold (the float noise an Exasol AVG/STDDEV can carry even
# when the true value is exactly the threshold) counts as *equal*. Without this, "> 17 min"
# would fire on an average that is really exactly 17:00 — behaving like ">=". So ">"/"<"
# never trigger at (near-)equality, and ">="/"<=" always do.
def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


COMPARATORS: dict[str, callable] = {
    ">": lambda a, b: a > b and not _close(a, b),
    ">=": lambda a, b: a >= b or _close(a, b),
    "<": lambda a, b: a < b and not _close(a, b),
    "<=": lambda a, b: a <= b or _close(a, b),
}

# Metric names a transition_metric rule may measure (the TransitionMetric enum values).
METRIC_NAMES: tuple[str, ...] = tuple(m.value for m in TransitionMetric)

# Metric names a journey_duration rule may measure: the time-based aggregates of a whole
# case's duration (Avg/Median/Min/Max Time, Std Dev). A journey has no "Count" duration, so
# the non-time metric is excluded.
JOURNEY_METRIC_NAMES: tuple[str, ...] = tuple(m.value for m in TransitionMetric if m.is_time_based)

# How far back a rule looks for events as the base of its measurement. "all" = the whole
# history (no lower bound); otherwise `lookbackValue` of this unit before now.
LOOKBACK_UNITS: tuple[str, ...] = ("all", "minutes", "days", "months", "years")
DEFAULT_LOOKBACK_UNIT = "all"


def _subtract_months(dt: datetime, months: int) -> datetime:
    total = dt.month - 1 - months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def lookback_cutoff(config: dict, now: datetime) -> datetime | None:
    """The lower bound for a rule's measurement window, or None for "all". `now` should be
    the wall-clock reference the data's EVENT_TIME uses (the app's display zone)."""
    unit = str(config.get("lookbackUnit") or "all").lower()
    try:
        value = int(config.get("lookbackValue") or 0)
    except (TypeError, ValueError):
        return None
    if unit == "all" or value < 1:
        return None
    if unit == "minutes":
        return now - timedelta(minutes=value)
    if unit == "days":
        return now - timedelta(days=value)
    if unit == "months":
        return _subtract_months(now, value)
    if unit == "years":
        return _subtract_months(now, value * 12)
    return None

RULE_KINDS: tuple[str, ...] = ("transition_metric", "journey_duration", "note")

# ── note kind ────────────────────────────────────────────────────────────────
# What note activity a "note" rule watches.
NOTE_EVENTS: tuple[str, ...] = ("created", "open", "resolved", "commented")
DEFAULT_NOTE_EVENT = "created"
# Which notes a rule may watch. The engine is headless, so "shared" (the default) is the safe
# choice; "all" also surfaces everyone's personal notes.
NOTE_SCOPES: tuple[str, ...] = ("shared", "all")
# Minimum note importance a rule matches (NORMAL = any). Mirrors models.NOTE_IMPORTANCE.
NOTE_IMPORTANCES: tuple[str, ...] = ("NORMAL", "INFO", "IMPORTANT", "URGENT")
DEFAULT_KIND = "transition_metric"

# Remote delivery channels a rule may fire to when it triggers. Extensible: each adds a branch
# in validate_delivery here and a handler in delivery.py.
DELIVERY_CHANNELS: tuple[str, ...] = ("webpush", "smtp")


def validate_delivery(delivery: dict | None) -> dict:
    """Return the cleaned delivery config — only the enabled, known channels. "webpush" is a
    simple on/off; "smtp" (email) carries an optional recipient list (empty = the users
    assigned to the connection). New channels validate their own sub-config here."""
    d = delivery or {}
    out: dict = {}
    if d.get("webpush"):
        out["webpush"] = True
    smtp = d.get("smtp")
    if smtp:
        raw = smtp.get("recipients") if isinstance(smtp, dict) else []
        recipients = []
        for item in raw or []:
            addr = str(item).strip()
            if addr and "@" in addr and len(addr) <= 320:
                recipients.append(addr)
        out["smtp"] = {"recipients": recipients[:50]}
    return out


class RuleError(ValueError):
    """A rule definition is invalid (bad kind, metric, comparator, threshold, ...)."""


def validate_severity(value: str | None) -> str:
    v = (value or "").strip().upper()
    return v if v in SEVERITY_RANK else DEFAULT_SEVERITY


def validate_interval(value) -> int:
    try:
        secs = int(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
    return secs if secs in INTERVAL_CHOICES else DEFAULT_INTERVAL


def validate_kind(value: str | None) -> str:
    v = (value or "").strip() or DEFAULT_KIND
    if v not in RULE_KINDS:
        raise RuleError(f"Unknown notification kind {v!r}.")
    return v


def _clean_step(value, field: str) -> str:
    s = str(value or "").strip()
    if not s:
        raise RuleError(f"A {field} step is required.")
    if len(s) > 500:
        raise RuleError(f"The {field} step name is too long.")
    return s


def _clean_comparison(cfg: dict, metric_names: tuple[str, ...]) -> dict:
    """The criterion shared by every kind: a metric (from `metric_names`), a comparator, a
    numeric threshold and a lookback window. Returns those cleaned fields."""
    metric = str(cfg.get("metric") or "").strip()
    if metric not in metric_names:
        raise RuleError(f"Unknown metric {metric!r}.")
    comparator = str(cfg.get("comparator") or "").strip()
    if comparator not in COMPARATORS:
        raise RuleError(f"Unknown comparator {comparator!r}.")
    try:
        threshold = float(cfg.get("threshold"))
    except (TypeError, ValueError):
        raise RuleError("A numeric threshold is required.")
    lb_unit = str(cfg.get("lookbackUnit") or "all").strip().lower()
    if lb_unit not in LOOKBACK_UNITS:
        lb_unit = "all"
    try:
        lb_value = int(cfg.get("lookbackValue") or 0)
    except (TypeError, ValueError):
        lb_value = 0
    if lb_unit == "all" or lb_value < 1:
        lb_unit, lb_value = "all", 0
    else:
        lb_value = min(lb_value, 1_000_000)
    return {
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "lookbackUnit": lb_unit,
        "lookbackValue": lb_value,
    }


def validate_config(kind: str, config: dict | None) -> dict:
    """Return a cleaned, canonical config for `kind`, or raise RuleError. This is the
    per-kind extension point: a new kind adds a branch here and an evaluator in the engine.
    """
    cfg = config or {}
    if kind == "transition_metric":
        # A metric on the transition from one step to a following one.
        return {
            "fromStep": _clean_step(cfg.get("fromStep"), "from"),
            "toStep": _clean_step(cfg.get("toStep"), "to"),
            **_clean_comparison(cfg, METRIC_NAMES),
        }
    if kind == "journey_duration":
        # A time aggregate of the whole case's duration — no step selection.
        return _clean_comparison(cfg, JOURNEY_METRIC_NAMES)
    if kind == "note":
        return _clean_note(cfg)
    raise RuleError(f"Unknown notification kind {kind!r}.")


def _clean_note(cfg: dict) -> dict:
    """A note rule: which note activity to watch, at what minimum importance and scope, how
    many must match to fire (comparator/threshold, default "at least 1"), over what window."""
    event = str(cfg.get("event") or "").strip().lower()
    if event not in NOTE_EVENTS:
        event = DEFAULT_NOTE_EVENT
    min_importance = str(cfg.get("minImportance") or "NORMAL").strip().upper()
    if min_importance not in NOTE_IMPORTANCES:
        min_importance = "NORMAL"
    scope = str(cfg.get("scope") or "shared").strip().lower()
    if scope not in NOTE_SCOPES:
        scope = "shared"
    comparator = str(cfg.get("comparator") or ">=").strip()
    if comparator not in COMPARATORS:
        comparator = ">="
    try:
        threshold = max(1, int(float(cfg.get("threshold", 1))))
    except (TypeError, ValueError):
        threshold = 1
    lb_unit = str(cfg.get("lookbackUnit") or "all").strip().lower()
    if lb_unit not in LOOKBACK_UNITS:
        lb_unit = "all"
    try:
        lb_value = int(cfg.get("lookbackValue") or 0)
    except (TypeError, ValueError):
        lb_value = 0
    # "All open notes" ignores the window; the others default to a sensible one if unset.
    if event == "open":
        lb_unit, lb_value = "all", 0
    elif lb_unit == "all" or lb_value < 1:
        lb_unit, lb_value = "all", 0
    else:
        lb_value = min(lb_value, 1_000_000)
    return {
        "event": event,
        "minImportance": min_importance,
        "scope": scope,
        "comparator": comparator,
        "threshold": threshold,
        "lookbackUnit": lb_unit,
        "lookbackValue": lb_value,
    }
