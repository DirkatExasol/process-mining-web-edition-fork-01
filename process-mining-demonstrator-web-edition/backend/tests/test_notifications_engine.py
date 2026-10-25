"""Engine-logic tests: due-ness, the transition-metric evaluator, and the run-state
persistence that keeps a notification's original triggered-at time across consecutive
triggers. No database — the repository is faked."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from types import SimpleNamespace

from app.models import DurationStats, NoteTarget, ProcessTransition
from app.notifications import engine
from app.store.security import NotificationRule


def _rule(**over) -> NotificationRule:
    cfg = {"fromStep": "A", "toStep": "B", "metric": "Avg Time",
           "comparator": ">", "threshold": 7200.0}
    cfg.update(over.pop("config", {}))
    data = dict(
        id="r1", connection_id="c1", project_id=1, project_title="Orders",
        kind="transition_metric", name="slow A→B", severity="URGENT",
        interval_secs=300, enabled=True, config=json.dumps(cfg), delivery="",
        created_by="alice", created_at="2026-01-01T00:00:00+00:00",
    )
    data.update(over)
    return NotificationRule(**data)


def _journey_rule(**over) -> NotificationRule:
    cfg = {"metric": "Max Time", "comparator": ">", "threshold": 7200.0}
    cfg.update(over.pop("config", {}))
    return _rule(kind="journey_duration", config=cfg, name="slow journeys", **over)


def _note_rule(**over) -> NotificationRule:
    cfg = {"event": "created", "minImportance": "NORMAL", "scope": "shared"}
    cfg.update(over.pop("config", {}))
    data = dict(
        id="r1", connection_id="c1", project_id=1, project_title="Orders",
        kind="note", name="new notes", severity="INFO", interval_secs=300, enabled=True,
        config=json.dumps(cfg), delivery="", created_by="alice",
        created_at="2026-01-01T00:00:00+00:00",
    )
    data.update(over)
    return NotificationRule(**data)


def _note(id, title="n", importance="IMPORTANT", shared=True):
    return SimpleNamespace(
        id=id, title=title, importance=importance, isShared=shared,
        target=NoteTarget(type="node", value="Enter"),
        createdAt=datetime(2026, 10, 20, 9, 0, 0), editedAt=datetime(2026, 10, 20, 10, 0, 0),
    )


class _FakeRepo:
    def __init__(self, transitions=None, duration=None, notes=None):
        self._transitions = transitions or []
        self._duration = duration
        self._notes = notes or []
        self.last_filter = None
        self.note_args = None

    async def load_transitions(self, project_id, f):
        self.last_filter = f
        return self._transitions

    async def load_journey_duration_stats(self, project_id, f):
        self.last_filter = f
        return self._duration

    async def match_notes_for_notification(self, project_id, *, event, min_importance,
                                           shared_only, cutoff):
        self.note_args = dict(event=event, min_importance=min_importance,
                              shared_only=shared_only, cutoff=cutoff)
        return self._notes


def _run(coro):
    return asyncio.run(coro)


def test_due_logic():
    assert engine._due(None, 300) is True
    assert engine._due({"lastRunAt": ""}, 300) is True
    recent = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    assert engine._due({"lastRunAt": recent}, 300) is False
    old = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    assert engine._due({"lastRunAt": old}, 300) is True
    # Interval is floored at 60s even if a rule somehow stored less.
    just = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    assert engine._due({"lastRunAt": just}, 1) is False


def _eval(repo, rule):
    # evaluate_rule returns (value, triggered, error, meta); these tests assert the first three.
    value, triggered, error, _meta = _run(
        engine.evaluate_rule(repo, rule.project_id, rule.kind, rule.config_dict())
    )
    return value, triggered, error


def test_evaluate_triggers_when_over_threshold():
    repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=5, avgSecs=9000.0)])
    value, triggered, err = _eval(repo, _rule())
    assert value == 9000.0 and triggered is True and err == ""


def test_evaluate_not_triggered_when_under_threshold():
    repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=5, avgSecs=100.0)])
    value, triggered, err = _eval(repo, _rule())
    assert value == 100.0 and triggered is False and err == ""


def test_evaluate_strict_gt_does_not_fire_at_or_near_threshold():
    # "> 7200" must not trigger when the average is exactly the threshold, nor on float noise.
    for v in (7200.0, 7200.0000001):
        repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=5, avgSecs=v)])
        _, triggered, _ = _eval(repo, _rule())  # default rule is "Avg Time > 7200"
        assert triggered is False
    # A genuine excess does trigger.
    repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=5, avgSecs=7260.0)])
    _, triggered, _ = _eval(repo, _rule())
    assert triggered is True


def test_evaluate_missing_transition_is_healthy_not_error():
    repo = _FakeRepo([ProcessTransition(fromStep="X", toStep="Y", occurrences=1, avgSecs=1.0)])
    value, triggered, err = _eval(repo, _rule())
    assert value is None and triggered is False and err == ""


def test_evaluate_count_metric():
    repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=12, avgSecs=None)])
    value, triggered, err = _eval(repo, _rule(config={"metric": "Count", "comparator": ">=", "threshold": 10}))
    assert value == 12.0 and triggered is True


def test_evaluate_bad_config_reports_error():
    repo = _FakeRepo([])
    value, triggered, err = _eval(repo, _rule(config={"metric": "Nope"}))
    assert value is None and triggered is False and err


def test_evaluate_unknown_kind():
    repo = _FakeRepo([])
    value, triggered, err, meta = _run(engine.evaluate_rule(repo, 1, "teleport", {}))
    assert value is None and triggered is False and "teleport" in err and meta is None


def test_evaluate_applies_lookback_window():
    # "all" (default) → no lower bound on the query.
    repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=5, avgSecs=100.0)])
    _eval(repo, _rule())
    assert repo.last_filter.fromInstant is None
    # A days window → a precise fromInstant is set.
    repo = _FakeRepo([ProcessTransition(fromStep="A", toStep="B", occurrences=5, avgSecs=100.0)])
    _eval(repo, _rule(config={"lookbackUnit": "days", "lookbackValue": 7}))
    assert repo.last_filter.fromInstant is not None


def test_evaluate_journey_duration_triggers_over_threshold():
    repo = _FakeRepo(duration=DurationStats(avgSecs=3000.0, maxSecs=9000.0, medianSecs=2500.0))
    value, triggered, err = _eval(repo, _journey_rule())  # Max Time > 7200
    assert value == 9000.0 and triggered is True and err == ""


def test_evaluate_journey_duration_uses_selected_metric():
    repo = _FakeRepo(duration=DurationStats(avgSecs=3000.0, maxSecs=9000.0, medianSecs=2500.0))
    # Median Time (2500) is under the 7200 limit, so the same stats don't trigger.
    value, triggered, _ = _eval(repo, _journey_rule(config={"metric": "Median Time"}))
    assert value == 2500.0 and triggered is False


def test_evaluate_journey_duration_no_journeys_is_healthy():
    # An empty window → the metric's field is None → null value, not an error.
    repo = _FakeRepo(duration=DurationStats())
    value, triggered, err = _eval(repo, _journey_rule())
    assert value is None and triggered is False and err == ""


def test_evaluate_journey_duration_rejects_count_metric():
    repo = _FakeRepo(duration=DurationStats(maxSecs=1.0))
    value, triggered, err = _eval(repo, _journey_rule(config={"metric": "Count"}))
    assert value is None and triggered is False and err


def test_evaluate_journey_duration_applies_lookback_window():
    repo = _FakeRepo(duration=DurationStats(maxSecs=1.0))
    _eval(repo, _journey_rule(config={"lookbackUnit": "days", "lookbackValue": 3}))
    assert repo.last_filter.fromInstant is not None


def _eval4(repo, rule):
    return _run(engine.evaluate_rule(repo, rule.project_id, rule.kind, rule.config_dict()))


def test_note_rule_counts_matches_and_carries_the_latest_note():
    repo = _FakeRepo(notes=[_note("n2", title="Newest"), _note("n1")])
    value, triggered, err, meta = _eval4(repo, _note_rule())
    assert value == 2.0 and triggered is True and err == ""
    assert meta["noteId"] == "n2" and meta["title"] == "Newest" and meta["count"] == 2
    assert meta["target"] == "Enter" and meta["importance"] == "IMPORTANT"


def test_note_rule_not_triggered_without_matches():
    repo = _FakeRepo(notes=[])
    value, triggered, err, meta = _eval4(repo, _note_rule())
    assert value == 0.0 and triggered is False and meta is None


def test_note_rule_forwards_scope_importance_and_event():
    repo = _FakeRepo(notes=[])
    _eval4(repo, _note_rule(config={"event": "resolved", "minImportance": "URGENT", "scope": "all"}))
    assert repo.note_args["event"] == "resolved"
    assert repo.note_args["min_importance"] == "URGENT"
    assert repo.note_args["shared_only"] is False  # scope "all" → not shared-only


def test_note_rule_threshold_requires_enough_matches():
    repo = _FakeRepo(notes=[_note("n1")])
    _, triggered, _, _ = _eval4(repo, _note_rule(config={"threshold": 3}))
    assert triggered is False  # 1 < 3
    repo = _FakeRepo(notes=[_note("a"), _note("b"), _note("c")])
    _, triggered, _, _ = _eval4(repo, _note_rule(config={"threshold": 3}))
    assert triggered is True


def test_persist_keeps_first_triggered_at_then_clears(monkeypatch):
    saved = {}

    def _set_state(rule_id, **kw):
        saved.update(kw)
        saved["rule_id"] = rule_id

    monkeypatch.setattr(engine.store, "set_rule_state", _set_state)
    rule = _rule()

    # First trigger: triggered_at is set.
    engine._persist(rule, None, 9000.0, True, "")
    first = saved["triggered_at"]
    assert saved["triggered"] is True and first
    assert saved["cleared_at"] == ""

    # Still triggered on the next tick: the original triggered_at is preserved.
    prev = {"triggered": True, "triggeredAt": first}
    engine._persist(rule, prev, 9500.0, True, "")
    assert saved["triggered_at"] == first

    # Recovers: not triggered, cleared_at recorded.
    prev = {"triggered": True, "triggeredAt": first}
    engine._persist(rule, prev, 100.0, False, "")
    assert saved["triggered"] is False and saved["triggered_at"] == "" and saved["cleared_at"]
