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

# Roles a detected/'assigned field can take. Mirrors the process-mining essentials plus
# free-form meta attributes.
ROLES = ("timestamp", "id", "step", "meta")

# ── timestamp templates (ordered: most specific first) ────────────────────────
_TIMESTAMP_PATTERNS = [
    # ISO-8601: 2026-08-03T14:05:09.123 / 2026-08-03 14:05:09
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?",
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

    # timestamp
    for pat in _TIMESTAMP_PATTERNS:
        m = _first(sample, pat)
        if m and free(m.span()):
            fields.append({"name": "timestamp", "role": "timestamp", "regex": _capture(pat)})
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
    key = re.split(r"\s*[=:]", matched, 1)[0]
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
