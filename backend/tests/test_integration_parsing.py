"""Source-type wizard log parsing: field auto-detection + regex-from-segment.

Every generated regex must have exactly one capturing group and re-match the value it
was derived from."""

from __future__ import annotations

import re

import pytest

from app.integration.parsing import detect_fields, regex_from_segment

SAMPLE = (
    "2026-08-03T14:05:09.123Z INFO OrderReceived "
    "case_id=abc-123 user=alice amount=42 "
    "trace=550e8400-e29b-41d4-a716-446655440000"
)


def _by_role(fields):
    out = {}
    for f in fields:
        out.setdefault(f["role"], []).append(f)
    return out


def test_detect_finds_timestamp_id_step_and_meta():
    fields = detect_fields(SAMPLE)
    roles = _by_role(fields)
    assert "timestamp" in roles and "id" in roles and "step" in roles and "meta" in roles

    # Each regex captures the expected value out of the sample.
    ts = re.search(roles["timestamp"][0]["regex"], SAMPLE)
    assert ts and ts.group(1) == "2026-08-03T14:05:09.123Z"
    idm = re.search(roles["id"][0]["regex"], SAMPLE)
    assert idm and idm.group(1) == "550e8400-e29b-41d4-a716-446655440000"
    step = re.search(roles["step"][0]["regex"], SAMPLE)
    assert step and step.group(1) == "OrderReceived"

    metas = {f["name"]: f["regex"] for f in roles["meta"]}
    assert "case_id" in metas and re.search(metas["case_id"], SAMPLE).group(1) == "abc-123"
    assert "amount" in metas and re.search(metas["amount"], SAMPLE).group(1) == "42"


def test_every_detected_regex_has_exactly_one_group():
    for f in detect_fields(SAMPLE):
        assert re.compile(f["regex"]).groups == 1, f["regex"]


def test_detect_empty_sample_returns_nothing():
    assert detect_fields("") == []


def test_regex_from_segment_generalises_and_rematches():
    seg = regex_from_segment(SAMPLE, 0, 10)  # "2026-08-03"
    assert seg["value"] == "2026-08-03"
    assert re.compile(seg["regex"]).groups == 1
    m = re.search(seg["regex"], SAMPLE)
    assert m and m.group(1) == "2026-08-03"
    # digits generalised, not a literal year.
    assert "2026" not in seg["regex"]
    assert re.search(seg["regex"], "1999-12-31 ...").group(1) == "1999-12-31"


def test_regex_from_segment_anchors_on_preceding_context():
    s = "status=RUNNING next=OK"
    seg = regex_from_segment(s, 7, 14)  # "RUNNING"
    assert seg["regex"].startswith("status=")
    assert re.search(seg["regex"], s).group(1) == "RUNNING"


def test_regex_from_segment_empty_selection_raises():
    with pytest.raises(ValueError):
        regex_from_segment(SAMPLE, 5, 5)


# ── timestamp analysis / normalisation ────────────────────────────────────────


def test_analyze_timestamp_normalises_many_formats():
    from app.integration.parsing import analyze_timestamp
    cases = {
        # ISO-8601 with fractional seconds + offsets / Z
        "2026-08-03T14:05:09.123Z": "2026-08-03 14:05:09",
        "2026-08-03T14:05:09.123456+02:00": "2026-08-03 14:05:09",
        "2026-08-03 14:05:09": "2026-08-03 14:05:09",
        # dot / slash separators, day-first (European default)
        "03.08.2026 14:05:09": "2026-08-03 14:05:09",
        "03/08/2026 14:05:09": "2026-08-03 14:05:09",
        # 12-hour AM/PM ⇒ month-first (US) reading
        "08/03/2026 02:05:09 PM": "2026-08-03 14:05:09",
        # spelled-out / abbreviated month names
        "03 Aug 2026 14:05:09": "2026-08-03 14:05:09",
        "August 3, 2026 2:05 PM": "2026-08-03 14:05:00",
        # web-server / email / date-only
        "03/Aug/2026:14:05:09 +0000": "2026-08-03 14:05:09",
        "Mon, 03 Aug 2026 14:05:09 +0000": "2026-08-03 14:05:09",
        "2026-08-03": "2026-08-03 00:00:00",
    }
    for value, expected in cases.items():
        out = analyze_timestamp(value)
        assert out["normalized"] == expected, value
        assert out["format"], value  # a parse format was inferred


def test_analyze_timestamp_handles_epochs():
    from app.integration.parsing import analyze_timestamp
    assert analyze_timestamp("1754229909")["format"] == "epoch:s"
    assert analyze_timestamp("1754229909123")["format"] == "epoch:ms"
    # Same instant in seconds and milliseconds.
    assert analyze_timestamp("1754229909")["normalized"] == analyze_timestamp("1754229909123")["normalized"]


def test_analyze_timestamp_rejects_non_dates():
    from app.integration.parsing import analyze_timestamp
    assert analyze_timestamp("not a date") == {"format": "", "normalized": ""}
    assert analyze_timestamp("") == {"format": "", "normalized": ""}


def test_detect_attaches_a_format_to_the_timestamp_field():
    fields = detect_fields(SAMPLE)
    ts = next(f for f in fields if f["role"] == "timestamp")
    assert ts.get("format")  # e.g. "%Y-%m-%dT%H:%M:%S%z"


def test_detect_and_normalise_apache_clf_timestamp():
    import re
    from app.integration.parsing import analyze_timestamp
    line = ('10.185.248.71 - - [09/Jan/2015:19:12:06 +0000] 808840 '
            '"GET /shop/view?userId=20253471&bookId=B-1001 HTTP/1.1" 200 8241 "-" "UA"')
    ts = next(f for f in detect_fields(line) if f["role"] == "timestamp")
    m = re.search(ts["regex"], line)
    assert m and m.group(1) == "09/Jan/2015:19:12:06 +0000"
    assert analyze_timestamp(m.group(1))["normalized"] == "2015-01-09 19:12:06"
