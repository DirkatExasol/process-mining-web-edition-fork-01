"""Dashboard notifications engine.

A single background loop (started in the compute backend's lifespan) wakes every
``NOTIFICATIONS_TICK_SECS`` and, when the feature is enabled, evaluates every
notification rule that is **due** (its own 1m..1d interval has elapsed since the last run).
Rules are grouped by connection so one Exasol connection serves all of a connection's due
rules per tick. For each rule the engine measures the configured metric and records, on the
rule's run state, the last value, whether the criteria is currently met ("triggered") and
since when, and any error — which the Dashboard then reads back per process tile.

The loop runs headless (no signed-in user): rules are shared per connection, so it opens
the stored connection credentials directly, exactly like the file-import watchdog. One
misconfigured rule or connection never stops the others or the loop.

New check kinds slot in by adding an evaluator to ``_EVALUATORS`` (keyed by the rule's
``kind``) plus a validator in ``spec.validate_config`` — no schema or loop change.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone

from .. import log_events as logx
from ..config import NOTIFICATIONS_ENGINE_ENABLED, NOTIFICATIONS_TICK_SECS
from ..db.manager import DatabaseManager
from ..db.repository import ProcessRepository
from ..models import FilterSpec, TransitionMetric
from ..store.security import NotificationRule, store
from ..timeutil import local_now
from . import spec


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _due(state: dict | None, interval_secs: int) -> bool:
    """True if a rule is due to run (never run, or its interval has elapsed)."""
    if not state or not state.get("lastRunAt"):
        return True
    try:
        last = datetime.fromisoformat(state["lastRunAt"])
    except (ValueError, TypeError):
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (_now() - last).total_seconds() >= max(60, int(interval_secs))


# An evaluator returns (value, triggered, error, meta): the measured scalar, whether the
# criterion is met, an error string ("" when fine), and optional metadata the Dashboard card
# carries (e.g. the triggering note for a "note" rule). Metric kinds have no meta (None).
EvalResult = tuple[float | None, bool, str, dict | None]


async def _eval_transition_metric(
    repo: ProcessRepository, project_id, config: dict
) -> EvalResult:
    """Measure a transition_metric check.

    A transition that doesn't occur in the current data is treated as healthy (not
    triggered), with a null value — not an error."""
    try:
        clean = spec.validate_config("transition_metric", config)
    except spec.RuleError as exc:
        return (None, False, str(exc), None)
    metric = TransitionMetric(clean["metric"])
    predicate = spec.COMPARATORS[clean["comparator"]]
    threshold = clean["threshold"]

    # Only look back over the configured window (minutes/days/months/years), or all history.
    cutoff = spec.lookback_cutoff(clean, local_now())
    transitions = await repo.load_transitions(str(project_id), FilterSpec(fromInstant=cutoff))
    match = next(
        (t for t in transitions
         if t.fromStep == clean["fromStep"] and t.toStep == clean["toStep"]),
        None,
    )
    if match is None:
        return (None, False, "", None)
    value = match.metric_value(metric)
    if value is None:
        return (None, False, "", None)
    return (float(value), bool(predicate(float(value), threshold)), "", None)


# Maps a journey_duration metric name to the DurationStats field that holds it.
_DURATION_FIELDS = {
    TransitionMetric.avgTime.value: "avgSecs",
    TransitionMetric.medianTime.value: "medianSecs",
    TransitionMetric.minTime.value: "minSecs",
    TransitionMetric.maxTime.value: "maxSecs",
    TransitionMetric.stdDev.value: "stdDevSecs",
}


async def _eval_journey_duration(
    repo: ProcessRepository, project_id, config: dict
) -> EvalResult:
    """Measure a journey_duration check — a time aggregate of each case's end-to-end duration
    against a threshold. No journeys in the window yields a null value (healthy, not an error)."""
    try:
        clean = spec.validate_config("journey_duration", config)
    except spec.RuleError as exc:
        return (None, False, str(exc), None)
    predicate = spec.COMPARATORS[clean["comparator"]]
    threshold = clean["threshold"]

    # Only look back over the configured window (minutes/days/months/years), or all history.
    cutoff = spec.lookback_cutoff(clean, local_now())
    stats = await repo.load_journey_duration_stats(
        str(project_id), FilterSpec(fromInstant=cutoff)
    )
    value = getattr(stats, _DURATION_FIELDS[clean["metric"]], None)
    if value is None:
        return (None, False, "", None)
    return (float(value), bool(predicate(float(value), threshold)), "", None)


async def _eval_note(repo: ProcessRepository, project_id, config: dict) -> EvalResult:
    """Count the notes a note-rule matches (new / open / resolved / commented, at a minimum
    importance and scope) and trigger when the count meets the threshold. The latest matching
    note is returned as `meta` so the Dashboard card can deep-link to it."""
    try:
        clean = spec.validate_config("note", config)
    except spec.RuleError as exc:
        return (None, False, str(exc), None)
    predicate = spec.COMPARATORS[clean["comparator"]]
    threshold = clean["threshold"]
    cutoff = spec.lookback_cutoff(clean, local_now())
    notes = await repo.match_notes_for_notification(
        str(project_id),
        event=clean["event"], min_importance=clean["minImportance"],
        shared_only=(clean["scope"] != "all"), cutoff=cutoff,
    )
    count = len(notes)
    triggered = bool(predicate(float(count), float(threshold)))
    meta = None
    if notes:
        latest = notes[0]  # newest-first
        when = (latest.editedAt if clean["event"] in ("resolved", "commented") and latest.editedAt
                else latest.createdAt)
        meta = {
            "noteId": latest.id,
            "title": latest.title or "(untitled note)",
            "target": latest.target.display_name if latest.target else "",
            "at": when.isoformat() if when else "",
            "importance": latest.importance,
            "count": count,
            "scope": "shared" if latest.isShared else "personal",
            "event": clean["event"],
        }
    return (float(count), triggered, "", meta)


# Per-kind evaluator registry — the engine's extension point for new check types.
_EVALUATORS = {
    "transition_metric": _eval_transition_metric,
    "journey_duration": _eval_journey_duration,
    "note": _eval_note,
}


async def evaluate_rule(
    repo: ProcessRepository, project_id, kind: str, config: dict
) -> EvalResult:
    """Run the check for `kind` against `config` on an already-open repository. Shared by the
    background loop and the wizard's on-demand "Test" endpoint; never persists anything."""
    evaluator = _EVALUATORS.get(kind)
    if evaluator is None:
        return (None, False, f"Unknown notification kind {kind!r}.", None)
    return await evaluator(repo, project_id, config)


def _persist(rule: NotificationRule, prev: dict | None,
             value: float | None, triggered: bool, error: str,
             meta: dict | None = None) -> None:
    """Write the evaluation result to the rule's run state, preserving the original
    triggered-at time across consecutive triggers so the Dashboard's time sort is stable.

    For a note rule, a changed latest-note id starts a FRESH episode (new triggered-at), so an
    acknowledgement lapses and the newer note re-surfaces — the same edge the delivery fires on."""
    prev = prev or {}
    was = bool(prev.get("triggered"))
    now_iso = _now_iso()
    if triggered:
        new_episode = bool(meta and meta.get("noteId")
                           and (prev.get("note") or {}).get("noteId") != meta.get("noteId"))
        triggered_at = now_iso if (not was or new_episode) else (prev.get("triggeredAt") or now_iso)
        cleared_at = ""
    else:
        triggered_at = ""
        cleared_at = now_iso if was else (prev.get("clearedAt") or "")
    store.set_rule_state(
        rule.id, last_value=value, triggered=triggered,
        triggered_at=triggered_at, cleared_at=cleared_at, last_error=error or "",
        meta=json.dumps(meta)[:2000] if meta else "",
    )


async def _maybe_deliver(rule: NotificationRule, prev: dict | None,
                         triggered: bool, value: float | None,
                         meta: dict | None = None) -> None:
    """Fire the rule's remote delivery channels, but only on the *edge* into triggered (so a
    rule that stays triggered across ticks alerts once), and only for an enabled rule that has
    any channel configured. A note rule also re-fires when a newer matching note appears (a new
    episode), matching the Dashboard's re-surface-after-acknowledge behaviour."""
    if not (rule.enabled and triggered):
        return
    was = bool((prev or {}).get("triggered"))
    new_episode = bool(meta and meta.get("noteId")
                       and ((prev or {}).get("note") or {}).get("noteId") != meta.get("noteId"))
    if was and not new_episode:
        return
    if not rule.delivery_dict():
        return
    try:
        from .delivery import deliver

        await deliver(rule, value)
    except Exception as exc:  # noqa: BLE001 — delivery must never break evaluation
        logx.warn(
            f"notifications: delivery for {rule.id} failed: {exc}",
            operation="notifications", tag=logx.TAG_DATA,
        )


async def check_rule(rule: NotificationRule) -> dict | None:
    """Evaluate one rule against the current data right now and persist its run state — the
    manual "refresh" a user can trigger from a Dashboard card. Returns the new state. Errors
    are recorded on the state (never raised), exactly like the background loop."""
    async def _save(value: float | None, triggered: bool, error: str,
                    meta: dict | None = None) -> dict | None:
        prev = await asyncio.to_thread(store.get_rule_state, rule.id)
        await asyncio.to_thread(_persist, rule, prev, value, triggered, error, meta)
        await _maybe_deliver(rule, prev, triggered, value, meta)
        return await asyncio.to_thread(store.get_rule_state, rule.id)

    conn_def = await asyncio.to_thread(store.get_connection, rule.connection_id, with_secrets=True)
    if conn_def is None:
        return await _save(None, False, "The rule's connection no longer exists.")
    mgr = DatabaseManager(load_legacy_active=False)
    err = await mgr.connect_connection(conn_def)
    if err:
        return await _save(None, False, f"Could not open the connection: {err}")
    mgr.use_materialized_transitions = conn_def.use_materialized_transitions
    meta: dict | None = None
    try:
        repo = ProcessRepository(mgr)
        try:
            value, triggered, error, meta = await evaluate_rule(
                repo, rule.project_id, rule.kind, rule.config_dict()
            )
        except Exception as exc:  # noqa: BLE001
            value, triggered, error = None, False, f"Check failed: {exc}"
    finally:
        await mgr.disconnect()
    return await _save(value, triggered, error, meta)


async def check_rules(rules: list[NotificationRule]) -> None:
    """Evaluate several rules now and persist their state, grouped by connection so each
    database connection is opened once — the Dashboard's "Refresh all". Enabled flag is
    ignored (a manual refresh reports the current value even for a disabled rule)."""
    by_conn: dict[str, list[NotificationRule]] = defaultdict(list)
    for rule in rules:
        by_conn[rule.connection_id].append(rule)
    for connection_id, conn_rules in by_conn.items():
        states = await asyncio.to_thread(store.get_rule_states, [r.id for r in conn_rules])
        try:
            await _run_connection(connection_id, conn_rules, states)
        except Exception as exc:  # noqa: BLE001 — one bad connection must not stop the rest
            logx.warn(
                f"notifications: refresh-all for {connection_id} failed: {exc}",
                operation="notifications", tag=logx.TAG_DATA,
            )


async def _run_connection(connection_id: str, rules: list[NotificationRule],
                          states: dict[str, dict]) -> None:
    """Evaluate all due rules on one connection over a single Exasol connection."""
    conn_def = await asyncio.to_thread(
        store.get_connection, connection_id, with_secrets=True
    )
    if conn_def is None:
        for rule in rules:
            await asyncio.to_thread(
                _persist, rule, states.get(rule.id), None, False,
                "The rule's connection no longer exists.",
            )
        return

    mgr = DatabaseManager(load_legacy_active=False)
    err = await mgr.connect_connection(conn_def)
    if err:
        for rule in rules:
            await asyncio.to_thread(
                _persist, rule, states.get(rule.id), None, False,
                f"Could not open the connection: {err}",
            )
        return
    mgr.use_materialized_transitions = conn_def.use_materialized_transitions
    try:
        repo = ProcessRepository(mgr)
        for rule in rules:
            meta: dict | None = None
            try:
                value, triggered, error, meta = await evaluate_rule(
                    repo, rule.project_id, rule.kind, rule.config_dict()
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — one bad rule must not stop the rest
                value, triggered, error = None, False, f"Check failed: {exc}"
            prev = states.get(rule.id)
            await asyncio.to_thread(_persist, rule, prev, value, triggered, error, meta)
            await _maybe_deliver(rule, prev, triggered, value, meta)
    finally:
        await mgr.disconnect()


async def _tick() -> None:
    """One pass: evaluate every enabled, due rule, grouped by connection."""
    rules = await asyncio.to_thread(store.list_all_notification_rules)
    rules = [r for r in rules if r.enabled]
    if not rules:
        return
    states = await asyncio.to_thread(store.get_rule_states, [r.id for r in rules])
    due = [r for r in rules if _due(states.get(r.id), r.interval_secs)]
    if not due:
        return
    by_conn: dict[str, list[NotificationRule]] = defaultdict(list)
    for rule in due:
        by_conn[rule.connection_id].append(rule)
    for connection_id, conn_rules in by_conn.items():
        try:
            await _run_connection(connection_id, conn_rules, states)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logx.error(
                f"notifications: connection {connection_id} evaluation failed: {exc}",
                operation="notifications", tag=logx.TAG_DATA,
            )


async def notifications_loop() -> None:
    """The background loop. Disabled by env or by the admin toggle is a cheap idle."""
    if not NOTIFICATIONS_ENGINE_ENABLED:
        return
    while True:
        await asyncio.sleep(NOTIFICATIONS_TICK_SECS)
        if not store.notifications_enabled:
            continue
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logx.warn(
                f"notifications: tick failed: {exc}",
                operation="notifications", tag=logx.TAG_DATA,
            )
