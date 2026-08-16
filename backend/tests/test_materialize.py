"""Pure run-collapse transforms behind the aggregate materialiser (no database)."""

from __future__ import annotations

from app.db.materialize import (
    SourceEvent,
    StepRow,
    collapse_high_level,
    filter_detail,
    sigma_step_row,
)


def _ev(eid: str, step: str, sid: int) -> SourceEvent:
    return SourceEvent(eid, step, sid, f"2024-01-01 00:00:{sid:02d}", None, None, None)


def test_collapse_folds_each_member_run_into_one_sigma_event():
    # e1:  A  M1 M2  B  M3   (members M1,M2,M3)
    events = [_ev("e1", s, i) for i, s in enumerate(["A", "M1", "M2", "B", "M3"])]
    out = collapse_high_level(events, {"M1", "M2", "M3"}, "Σ")
    assert [e.step for e in out] == ["A", "Σ", "B", "Σ"]
    # The Σ event keeps the run's FIRST event's time/step_id (M1 at index 1).
    sigma = out[1]
    assert sigma.step_id == 1 and sigma.event_time.endswith(":01")


def test_collapse_resets_run_across_journeys():
    events = [_ev("e1", "M1", 0), _ev("e1", "M2", 1), _ev("e2", "M1", 0), _ev("e2", "X", 1)]
    out = collapse_high_level(events, {"M1", "M2"}, "Σ")
    # e1's M1,M2 fold to one Σ; e2 starts a fresh run → its own Σ, then X passes through.
    assert [(e.event_id, e.step) for e in out] == [("e1", "Σ"), ("e2", "Σ"), ("e2", "X")]


def test_collapse_passes_non_members_through_unchanged():
    events = [_ev("e1", "A", 0), _ev("e1", "B", 1), _ev("e1", "C", 2)]
    out = collapse_high_level(events, {"Z"}, "Σ")
    assert [e.step for e in out] == ["A", "B", "C"]


def test_filter_detail_keeps_only_member_events():
    events = [_ev("e1", "A", 0), _ev("e1", "M1", 1), _ev("e1", "B", 2), _ev("e1", "M2", 3)]
    out = filter_detail(events, {"M1", "M2"})
    assert [e.step for e in out] == ["M1", "M2"]


def test_sigma_step_row_sums_member_scores():
    steps = [
        StepRow("M1", "", "", "", 3, "rectangle", False, ""),
        StepRow("M2", "", "", "", 4, "rectangle", False, ""),
        StepRow("X", "", "", "", 9, "rectangle", False, ""),
    ]
    row = sigma_step_row("Σ", {"M1", "M2"}, steps)
    assert row.step == "Σ" and row.score == 7  # 3 + 4, X excluded
