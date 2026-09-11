"""A minimal, dependency-free 5-field cron parser/matcher for scheduled backups.

Fields: ``minute hour day-of-month month day-of-week``. Each field supports
``*``, ``a``, ``a-b``, ``*/n``, ``a-b/n`` and comma-separated lists thereof.
Day-of-week is 0-6 with Sunday=0 (7 is also accepted as Sunday). When BOTH
day-of-month and day-of-week are restricted (neither is a full range), a match on
EITHER fires — the Vixie-cron convention.
"""

from __future__ import annotations

from datetime import datetime

# (lo, hi) inclusive bounds per field.
_FIELD_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
_FIELD_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]
_FULL_DOM = set(range(1, 32))
_FULL_DOW = set(range(0, 7))


def _parse_field(spec: str, lo: int, hi: int, *, dow: bool = False) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty element")
        base, sep, step_s = part.partition("/")
        step = 1
        if sep:
            step = int(step_s)
            if step <= 0:
                raise ValueError("step must be positive")
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(base)
        if dow:  # normalise Sunday-as-7 to 0
            start = 0 if start == 7 else start
            end = 0 if end == 7 else end
        if start > end:
            raise ValueError("range start after end")
        if start < lo or end > hi:
            raise ValueError(f"out of range {lo}-{hi}")
        values.update(range(start, end + 1, step))
    return values


def parse(expr: str) -> list[set[int]]:
    """Parse a 5-field cron expression into per-field value sets. Raises ValueError."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("a cron expression must have exactly 5 fields")
    out: list[set[int]] = []
    for spec, (lo, hi), name in zip(fields, _FIELD_BOUNDS, _FIELD_NAMES):
        try:
            out.append(_parse_field(spec, lo, hi, dow=(name == "day-of-week")))
        except ValueError as exc:
            raise ValueError(f"invalid {name} field {spec!r}: {exc}") from None
    return out


def validate(expr: str) -> None:
    """Raise ValueError if `expr` is not a valid 5-field cron expression."""
    parse(expr)


def matches(expr: str, when: datetime) -> bool:
    """True if `when` (naive local time; seconds ignored) matches `expr`."""
    minute, hour, dom, month, dow = parse(expr)
    if when.minute not in minute or when.hour not in hour or when.month not in month:
        return False
    cron_dow = (when.weekday() + 1) % 7  # Python Mon=0..Sun=6 → cron Sun=0..Sat=6
    dom_restricted = dom != _FULL_DOM
    dow_restricted = dow != _FULL_DOW
    dom_ok = when.day in dom
    dow_ok = cron_dow in dow
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok
