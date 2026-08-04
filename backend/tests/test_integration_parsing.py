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
