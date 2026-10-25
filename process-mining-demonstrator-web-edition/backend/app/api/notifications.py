"""Dashboard notification rules — CRUD + the per-tile enable/disable toggle + a step
list for the wizard.

Rules are **shared per connection**: everyone assigned to a connection sees its rules and
their triggered state on the Dashboard; power users, developers and administrators may
create, edit, delete and toggle them. The background engine (``app.notifications.engine``)
evaluates them and writes the run state this API reads back.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import log_events as logx
from ..db.manager import DatabaseManager, current_user
from ..notifications import spec
from ..store.security import NotificationRule, store as security_store

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _require_enabled() -> None:
    if not security_store.notifications_enabled:
        raise HTTPException(status_code=403, detail="Notifications are not enabled.")


def _caller():
    username = current_user()
    user = security_store.get_user(username) if username else None
    return username, user


def _is_manager(user) -> bool:
    return bool(user and user.is_enabled and (user.is_power or user.is_developer or user.is_admin))


def _require_manager():
    """Create/edit/delete/toggle is for power users, developers and administrators."""
    username, user = _caller()
    if not _is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Notification rules are managed by power users, developers and administrators only.",
        )
    return username, user


def _require_assigned(connection_id: str) -> None:
    if not security_store.user_can_use((connection_id or "").strip(), current_user()):
        raise HTTPException(status_code=403, detail="This connection is not available to you.")


def _rule_or_404(rule_id: str) -> NotificationRule:
    rule = security_store.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="That notification rule was not found.")
    return rule


class RuleBody(BaseModel):
    connectionId: str
    projectId: int
    projectTitle: str = ""
    kind: str = spec.DEFAULT_KIND
    name: str = ""
    severity: str = spec.DEFAULT_SEVERITY
    intervalSecs: int = spec.DEFAULT_INTERVAL
    enabled: bool = True
    config: dict = Field(default_factory=dict)
    delivery: dict = Field(default_factory=dict)


class EnabledBody(BaseModel):
    enabled: bool


class ProjectToggleBody(BaseModel):
    connectionId: str
    projectId: int
    enabled: bool


def _clean_body(body: RuleBody) -> tuple[str, dict]:
    """Validate kind + kind-specific config, returning (kind, config-dict). Raises 400."""
    try:
        kind = spec.validate_kind(body.kind)
        config = spec.validate_config(kind, body.config)
    except spec.RuleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return kind, config


def _rules_payload(username, user) -> dict:
    """The rules the caller may see (on their assigned connections), each with its run state,
    plus `canManage`. Shared by the list and the refresh-all endpoints."""
    conns = security_store.connections_for_user(username)
    conn_names = {c.id: c.name for c in conns}
    rules = security_store.list_rules_for_connections([c.id for c in conns])
    states = security_store.get_rule_states([r.id for r in rules])
    out = []
    for r in rules:
        item = r.public(states.get(r.id))
        item["connectionName"] = conn_names.get(r.connection_id, "")
        out.append(item)
    return {"rules": out, "canManage": _is_manager(user)}


@router.get("")
async def list_rules() -> dict:
    """Rules on every connection the caller is assigned to, each with its run state.
    `canManage` tells the UI whether to offer create/edit/toggle."""
    _require_enabled()
    username, user = _caller()
    return _rules_payload(username, user)


@router.post("/check-all")
async def check_all() -> dict:
    """Re-evaluate every rule the caller can see against the current data now (grouped by
    connection, one database connection each) and return the refreshed list — the summary
    strip's "Refresh all". Available to any assigned user; it never changes a rule."""
    _require_enabled()
    username, user = _caller()
    rules = security_store.list_rules_for_connections(
        [c.id for c in security_store.connections_for_user(username)]
    )
    if rules:
        from ..notifications.engine import check_rules

        await check_rules(rules)
    return _rules_payload(username, user)


@router.post("")
async def create_rule(body: RuleBody) -> dict:
    _require_enabled()
    _require_manager()
    _require_assigned(body.connectionId)
    kind, config = _clean_body(body)
    rule = security_store.add_rule(
        connection_id=body.connectionId.strip(), project_id=body.projectId,
        project_title=body.projectTitle, kind=kind, name=body.name,
        severity=spec.validate_severity(body.severity),
        interval_secs=spec.validate_interval(body.intervalSecs),
        enabled=body.enabled, config=json.dumps(config),
        delivery=json.dumps(spec.validate_delivery(body.delivery)),
        created_by=current_user() or "",
    )
    logx.info(f"notification rule created: {rule.name or rule.id}",
              username=current_user(), operation="notifications", tag=logx.TAG_DATA)
    return rule.public(security_store.get_rule_state(rule.id))


@router.put("/{rule_id}")
async def update_rule(rule_id: str, body: RuleBody) -> dict:
    _require_enabled()
    _require_manager()
    rule = _rule_or_404(rule_id)
    _require_assigned(rule.connection_id)
    kind, config = _clean_body(body)
    updated = security_store.update_rule(
        rule_id, project_id=body.projectId, project_title=body.projectTitle, kind=kind,
        name=body.name, severity=spec.validate_severity(body.severity),
        interval_secs=spec.validate_interval(body.intervalSecs), enabled=body.enabled,
        config=json.dumps(config),
        delivery=json.dumps(spec.validate_delivery(body.delivery)),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="That notification rule was not found.")
    return updated.public(security_store.get_rule_state(rule_id))


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str) -> dict:
    _require_enabled()
    _require_manager()
    rule = _rule_or_404(rule_id)
    _require_assigned(rule.connection_id)
    security_store.delete_rule(rule_id)
    logx.info(f"notification rule deleted: {rule.name or rule.id}",
              username=current_user(), operation="notifications", tag=logx.TAG_DATA)
    return {"deleted": True}


@router.post("/{rule_id}/enabled")
async def set_enabled(rule_id: str, body: EnabledBody) -> dict:
    _require_enabled()
    _require_manager()
    rule = _rule_or_404(rule_id)
    _require_assigned(rule.connection_id)
    security_store.set_rule_enabled(rule_id, body.enabled)
    return {"id": rule_id, "enabled": body.enabled}


@router.post("/{rule_id}/check")
async def check_now(rule_id: str) -> dict:
    """Re-evaluate one rule against the current data now and return it with its fresh state —
    the per-card "refresh". Available to anyone assigned to the rule's connection (it only
    re-runs the check the engine would run anyway; it never changes the rule)."""
    _require_enabled()
    rule = _rule_or_404(rule_id)
    _require_assigned(rule.connection_id)
    from ..notifications.engine import check_rule

    state = await check_rule(rule)
    updated = security_store.get_rule(rule_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="That notification rule was not found.")
    return updated.public(state)


@router.post("/{rule_id}/ack")
async def acknowledge(rule_id: str) -> dict:
    """Acknowledge a rule's current alert — hide it until it clears and triggers again. The
    acknowledgement is tied to this trigger episode (its triggered-at), so a fresh trigger
    shows it anew. Shared per connection (everyone assigned sees the same), available to any
    assigned user; a no-op if the rule is not currently triggered."""
    _require_enabled()
    rule = _rule_or_404(rule_id)
    _require_assigned(rule.connection_id)
    state = security_store.acknowledge_rule(rule_id)
    return rule.public(state)


@router.post("/project-toggle")
async def toggle_project(body: ProjectToggleBody) -> dict:
    """Enable/disable every rule on one process — the Dashboard tile's one-click switch."""
    _require_enabled()
    _require_manager()
    _require_assigned(body.connectionId)
    changed = security_store.set_rules_enabled_for_project(
        body.connectionId.strip(), body.projectId, body.enabled
    )
    return {"changed": changed, "enabled": body.enabled}


@router.post("/test")
async def test_rule(body: RuleBody) -> dict:
    """Evaluate a rule definition against the current data right now, without saving it — the
    wizard's "Test" button. Returns the measured value, whether the criteria is met, and
    whether the transition occurs at all. Never persists; same gate as create."""
    _require_enabled()
    _require_manager()
    _require_assigned(body.connectionId)
    kind, config = _clean_body(body)
    conn_def = security_store.get_connection(body.connectionId.strip(), with_secrets=True)
    if conn_def is None:
        raise HTTPException(status_code=404, detail="That connection was not found.")
    mgr = DatabaseManager(load_legacy_active=False)
    err = await mgr.connect_connection(conn_def)
    if err:
        return {"ok": False, "error": "Could not open the connection.", "value": None,
                "triggered": False, "hasData": False}
    mgr.use_materialized_transitions = conn_def.use_materialized_transitions
    try:
        from ..db.repository import ProcessRepository
        from ..notifications.engine import evaluate_rule

        repo = ProcessRepository(mgr)
        value, triggered, error, _meta = await evaluate_rule(repo, body.projectId, kind, config)
    finally:
        await mgr.disconnect()
    return {
        "ok": not error,
        "value": value,
        "triggered": triggered,
        "hasData": value is not None,
        "error": error or None,
    }


@router.get("/steps")
async def project_steps(connectionId: str = "", projectId: int = 0) -> dict:
    """The step names of a project, for the wizard's from/to pickers. Opens the stored
    connection headlessly (the caller must be assigned to it)."""
    _require_enabled()
    _require_assigned(connectionId)
    conn_def = security_store.get_connection(connectionId.strip(), with_secrets=True)
    if conn_def is None:
        raise HTTPException(status_code=404, detail="That connection was not found.")
    mgr = DatabaseManager(load_legacy_active=False)
    err = await mgr.connect_connection(conn_def)
    if err:
        raise HTTPException(status_code=502, detail="Could not open the connection.")
    try:
        from ..db.repository import ProcessRepository

        repo = ProcessRepository(mgr)
        steps = await repo.load_all_step_names(str(projectId))
    finally:
        await mgr.disconnect()
    return {"steps": steps}


# ── Web Push subscriptions (per browser/device, owned by the signed-in user) ──


class PushSubscribeBody(BaseModel):
    endpoint: str
    keys: dict  # {"p256dh": ..., "auth": ...}


class PushUnsubscribeBody(BaseModel):
    endpoint: str


@router.get("/push/key")
async def push_key() -> dict:
    """The VAPID public key the browser subscribes with (any signed-in user)."""
    _require_enabled()
    public_b64, _ = security_store.vapid_keys()
    return {"publicKey": public_b64}


@router.post("/push/subscribe")
async def push_subscribe(body: PushSubscribeBody) -> dict:
    """Register this browser's push subscription for the signed-in user."""
    _require_enabled()
    username = current_user()
    if not username:
        raise HTTPException(status_code=403, detail="Sign in to enable push notifications.")
    p256dh = str((body.keys or {}).get("p256dh") or "").strip()
    auth = str((body.keys or {}).get("auth") or "").strip()
    endpoint = (body.endpoint or "").strip()
    if not (endpoint.startswith("https://") and p256dh and auth):
        raise HTTPException(status_code=400, detail="A valid push subscription is required.")
    security_store.add_push_subscription(username, endpoint, p256dh, auth)
    return {"subscribed": True}


@router.post("/push/unsubscribe")
async def push_unsubscribe(body: PushUnsubscribeBody) -> dict:
    _require_enabled()
    username = current_user()
    security_store.delete_push_subscription((body.endpoint or "").strip(), username)
    return {"subscribed": False}


@router.post("/push/test")
async def push_test() -> dict:
    """Send a test push to the signed-in user's own subscriptions and report the result per
    device — the "Send a test notification" button. Surfaces the push service's error so a
    misconfiguration (e.g. an invalid VAPID contact) is visible instead of silently logged."""
    _require_enabled()
    username = current_user()
    if not username:
        raise HTTPException(status_code=403, detail="Sign in to send a test push.")
    subs = security_store.list_push_subscriptions(username)
    if not subs:
        return {"sent": 0, "failed": 0,
                "errors": ["This browser isn't subscribed — enable push on this device first."]}
    from ..notifications import webpush

    public_b64, private_pem = security_store.vapid_keys()
    subject = security_store.push_subject
    payload = json.dumps({
        "title": "✅ Test notification",
        "body": "Web browser push is working for Process Mining Demonstrator.",
        "tag": "pmw-test",
    }).encode("utf-8")
    sent, errors = 0, []
    for sub in subs:
        try:
            await webpush.send(
                sub, payload, private_pem=private_pem, public_b64=public_b64, subject=subject
            )
            sent += 1
        except webpush.PushGone:
            security_store.delete_push_subscription(sub["endpoint"])
            errors.append("A subscription had expired and was removed — re-enable push.")
        except Exception as exc:  # noqa: BLE001 — report the reason to the caller
            errors.append(str(exc))
    return {"sent": sent, "failed": len(subs) - sent, "errors": errors}
