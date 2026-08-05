"""Example-log field detection + regex generation for the source-type wizard.

Given a pasted example log line, `detect_fields` suggests a timestamp, a unique id, a
step/activity and candidate meta fields — each with a regex that captures the value.
`regex_from_segment` turns a user-highlighted span into a generalised capturing regex.

Every regex produced here:
- has **exactly one capturing group** = the extracted value, and
- uses a syntax subset valid in **both** Python `re` and JavaScript `RegExp` (no named
  groups, no back-references), so the browser can highlight/preview the same pattern the
  backend will later execute.

This module only *generates* patterns from our own templates and from literal text; it
never compiles or runs a user-supplied regex (that happens client-side), so it is not a
ReDoS vector.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# Roles a detected/'assigned field can take. Mirrors the process-mining essentials plus
# free-form meta attributes.
ROLES = ("timestamp", "id", "step", "meta")

# The canonical timestamp shape every extracted date is normalised to:
# YEAR-MONTH-DAY HOUR:MINUTE:SECOND.
TIMESTAMP_TARGET = "%Y-%m-%d %H:%M:%S"

# Fully-specified special formats tried first (structure differs from the grid below).
_SPECIAL_FORMATS = [
    "%d/%b/%Y:%H:%M:%S %z",       # Apache / NCSA common log:  03/Aug/2026:14:05:09 +0000
    "%d/%b/%Y:%H:%M:%S",
    "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822 / email:          Mon, 03 Aug 2026 14:05:09 +0000
    "%a %b %d %H:%M:%S %Y",       # C asctime / `date`:        Mon Aug  3 14:05:09 2026
    "%b %d %H:%M:%S",             # syslog (yearless):         Aug  3 14:05:09
]

# Numeric date halves. The two orderings differ only in how the ambiguous "08/03"
# style is read: day-first (European) is the default, but month-first (US) is tried
# first when the time is a 12-hour AM/PM clock — a strong US-locale signal. ISO
# (year-first) is unambiguous and always leads.
_DATE_NUMERIC_DAYFIRST = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
    "%m/%d/%Y", "%m-%d-%Y",
]
_DATE_NUMERIC_MONTHFIRST = [
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%m/%d/%Y", "%m-%d-%Y",
    "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
]
# Spelled-out / abbreviated month names — unambiguous, tried after the numeric dates.
_DATE_NAMED = [
    "%d %b %Y", "%d %B %Y",
    "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y",
]
_TIME_PARTS = [
    "T%H:%M:%S.%f", "T%H:%M:%S", "T%H:%M",
    " %H:%M:%S.%f", " %H:%M:%S", " %H:%M",
    " %I:%M:%S %p", " %I:%M %p",
    "",  # date only
]


def _candidate_formats() -> list[str]:
    out = list(_SPECIAL_FORMATS)
    for time in _TIME_PARTS:
        month_first = time.endswith("%p")  # AM/PM ⇒ prefer the US month-first reading
        dates = (_DATE_NUMERIC_MONTHFIRST if month_first else _DATE_NUMERIC_DAYFIRST) + _DATE_NAMED
        for date in dates:
            out.append(date + time)
            # A numeric-offset / Z variant when there is a real time component.
            if time and not time.endswith("%p"):
                out.append(date + time + "%z")
    return out


_TS_FORMATS = _candidate_formats()


def analyze_timestamp(value: str) -> dict:
    """Infer how to parse ``value`` as a date/time and normalise it to
    ``YYYY-MM-DD HH:MM:SS``.

    Returns ``{"format": <token>, "normalized": <str>}``; both empty when the value
    can't be parsed. ``format`` is a strptime pattern (or ``epoch:s`` / ``epoch:ms`` /
    ``epoch:us`` for Unix epochs) and is stored with the timestamp field so extraction
    later parses each value the same way and emits the canonical shape.

    Recognises ISO-8601 (with fractional seconds, ``Z`` or ``±HH:MM`` offsets), common
    slash/dot/dash dates (day-first and month-first), spelled-out and abbreviated month
    names, 12-hour clocks with AM/PM, Apache/CLF, RFC-2822 and syslog lines, and Unix
    epochs in seconds / milliseconds / microseconds.
    """
    v = re.sub(r"\s+", " ", (value or "").strip())  # collapse runs of whitespace
    if not v:
        return {"format": "", "normalized": ""}

    # Unix epoch (10-digit seconds / 13-digit ms / 16-digit µs).
    if v.isdigit() and len(v) in (10, 13, 16):
        divisor, token = {10: (1, "epoch:s"), 13: (1000, "epoch:ms"), 16: (1_000_000, "epoch:us")}[len(v)]
        try:
            dt = datetime.fromtimestamp(int(v) / divisor, tz=timezone.utc)
            return {"format": token, "normalized": dt.strftime(TIMESTAMP_TARGET)}
        except (ValueError, OverflowError, OSError):
            return {"format": "", "normalized": ""}

    for fmt in _TS_FORMATS:
        # Yearless formats (syslog) fill the current year — append it to both the value
        # and the format so strptime never parses an (ambiguous) yearless date.
        yearless = "%Y" not in fmt and "%y" not in fmt
        try:
            if yearless:
                parse_v = f"{v} {datetime.now(timezone.utc).year}"
                dt = datetime.strptime(parse_v, f"{fmt} %Y")
            else:
                dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        # Guard against %Y greedily matching a 2-digit year (e.g. "03/08/26").
        if dt.year < 1000 and "%Y" in fmt:
            continue
        return {"format": fmt, "normalized": dt.strftime(TIMESTAMP_TARGET)}

    return {"format": "", "normalized": ""}

# ── timestamp templates (ordered: most specific first) ────────────────────────
_TIMESTAMP_PATTERNS = [
    # ISO-8601: 2026-08-03T14:05:09.123 / 2026-08-03 14:05:09
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?",
    # Apache / NCSA common-log: 09/Jan/2015:19:12:06 +0000
    r"\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}(?: ?[+-]\d{4})?",
    # 03/08/2026 14:05:09  or  08/03/2026 14:05:09
    r"\d{2}/\d{2}/\d{4}[ T]\d{2}:\d{2}:\d{2}",
    # syslog: Aug  3 14:05:09
    r"[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}",
    # date only: 2026-08-03
    r"\d{4}-\d{2}-\d{2}",
    # epoch millis / seconds (10–13 digits) — matched last, guarded by word boundaries
    r"\b\d{13}\b",
    r"\b\d{10}\b",
]

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_LONG_HEX = r"\b[0-9a-fA-F]{16,}\b"

# Common log levels — used to find the "step" that usually follows, and to avoid
# mistaking the level itself for the step.
_LEVELS = ("TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL")


def _capture(pattern: str) -> str:
    """Wrap a pattern in a single capturing group."""
    return f"({pattern})"


def _first(sample: str, pattern: str) -> re.Match | None:
    return re.search(pattern, sample)


def detect_fields(sample: str) -> list[dict]:
    """Suggest extraction fields for one example log line.

    Returns a list of ``{name, role, regex}`` (regex captures the value). Best-effort:
    a field is only suggested when a confident pattern matches. Order: timestamp, id,
    step, then meta fields.
    """
    sample = sample or ""
    fields: list[dict] = []
    claimed: list[tuple[int, int]] = []  # spans already assigned, to avoid overlaps

    def free(span: tuple[int, int]) -> bool:
        return all(span[1] <= s or span[0] >= e for s, e in claimed)

    # timestamp — also infer a parse format so the value can be normalised later.
    for pat in _TIMESTAMP_PATTERNS:
        m = _first(sample, pat)
        if m and free(m.span()):
            field = {"name": "timestamp", "role": "timestamp", "regex": _capture(pat)}
            fmt = analyze_timestamp(m.group(0)).get("format")
            if fmt:
                field["format"] = fmt
            fields.append(field)
            claimed.append(m.span())
            break

    # unique id
    for pat in (_UUID, _LONG_HEX):
        m = _first(sample, pat)
        if m and free(m.span()):
            fields.append({"name": "id", "role": "id", "regex": _capture(pat)})
            claimed.append(m.span())
            break
    else:
        # id=… / id:… , else a standalone long integer not already claimed
        m = re.search(r"\b(?:id|uuid|guid|trace[_-]?id)\s*[=:]\s*(\w+)", sample, re.IGNORECASE)
        if m and free(m.span(1)):
            fields.append({"name": "id", "role": "id", "regex": _id_kv_regex(m.group(0))})
            claimed.append(m.span(1))
        else:
            m = re.search(r"\b\d{4,}\b", sample)
            if m and free(m.span()):
                fields.append({"name": "id", "role": "id", "regex": _capture(r"\d{4,}")})
                claimed.append(m.span())

    # step / activity
    step = _detect_step(sample, claimed, free)
    if step is not None:
        fields.append(step)

    # meta fields: key=value / key: value pairs
    for m in re.finditer(r"([A-Za-z][\w.-]{0,40})\s*[=:]\s*(\"[^\"]*\"|'[^']*'|[^\s,;]+)", sample):
        key, _val = m.group(1), m.group(2)
        name = _safe_name(key)
        if not name or any(f["name"] == name for f in fields):
            continue
        if not free(m.span(2)):
            continue
        quoted = _val[:1] in ("\"", "'")
        value_pat = r"\"[^\"]*\"" if _val[:1] == '"' else (r"'[^']*'" if _val[:1] == "'" else r"[^\s,;]+")
        fields.append({
            "name": name, "role": "meta",
            "regex": re.escape(key) + r"\s*[=:]\s*" + _capture(value_pat),
        })
        claimed.append(m.span(2))
        if len(fields) >= 12:  # keep the suggestion list sane
            break

    return fields


def _id_kv_regex(matched: str) -> str:
    key = re.split(r"\s*[=:]", matched, maxsplit=1)[0]
    return re.escape(key) + r"\s*[=:]\s*" + _capture(r"\w+")


def _detect_step(sample: str, claimed, free) -> dict | None:
    # 1) token right after a log level (e.g. "INFO OrderReceived")
    lvl = re.search(r"\b(" + "|".join(_LEVELS) + r")\b[\s:\-\]]+([A-Za-z][\w.-]{1,60})", sample)
    if lvl and free(lvl.span(2)):
        return {"name": "step", "role": "step",
                "regex": r"\b(?:" + "|".join(_LEVELS) + r")\b[\s:\-\]]+" + _capture(r"[A-Za-z][\w.-]+")}
    # 2) a quoted phrase
    q = re.search(r"\"([^\"]{2,60})\"", sample)
    if q and free(q.span(1)):
        return {"name": "step", "role": "step", "regex": r"\"" + _capture(r"[^\"]+") + r"\""}
    # 3) first CamelCase / ALLCAPS-ish word that isn't a level
    for m in re.finditer(r"\b([A-Z][A-Za-z][\w.-]{2,40})\b", sample):
        if m.group(1).upper() in _LEVELS:
            continue
        if free(m.span(1)):
            return {"name": "step", "role": "step", "regex": _capture(r"[A-Z][A-Za-z][\w.-]+")}
    return None


def regex_from_segment(sample: str, start: int, end: int) -> dict:
    """Generalise the substring ``sample[start:end]`` into a single-capture-group regex.

    Digit runs → ``\\d{n}``, letter runs → ``[A-Za-z]+``, alphanumeric runs → ``\\w+``,
    punctuation kept as escaped literals. When a non-space character immediately precedes
    the segment, a short escaped literal of that context is prepended (outside the group)
    to anchor the match. Returns ``{regex, value}``.
    """
    if sample is None:
        raise ValueError("sample required")
    n = len(sample)
    start = max(0, min(start, n))
    end = max(start, min(end, n))
    segment = sample[start:end]
    if not segment:
        raise ValueError("empty selection")

    body = _generalise(segment)
    # Anchor with up to 8 chars of immediately-preceding non-space context.
    prefix = ""
    if start > 0 and not sample[start - 1].isspace():
        ctx = sample[max(0, start - 8):start]
        ctx = ctx[ctx.rfind(" ") + 1:] if " " in ctx else ctx
        prefix = re.escape(ctx)
    return {"regex": prefix + _capture(body), "value": segment}


def _generalise(segment: str) -> str:
    """Turn a literal string into a compact regex body (no capturing group)."""
    out: list[str] = []
    i = 0
    n = len(segment)
    while i < n:
        c = segment[i]
        if c.isdigit():
            j = i
            while j < n and segment[j].isdigit():
                j += 1
            run = j - i
            out.append(rf"\d{{{run}}}" if run <= 8 else r"\d+")
            i = j
        elif c.isalpha():
            j = i
            while j < n and segment[j].isalpha():
                j += 1
            out.append(r"[A-Za-z]+")
            i = j
        elif c.isspace():
            j = i
            while j < n and segment[j].isspace():
                j += 1
            out.append(r"\s+")
            i = j
        else:
            # keep punctuation as an escaped literal
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _safe_name(key: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", (key or "").strip()).strip("_").lower()
    return name[:40]
