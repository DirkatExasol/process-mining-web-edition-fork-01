"""Remote notification delivery — the channel layer.

A rule's ``delivery`` config enables channels: ``{"webpush": true}`` today; ``{"smtp": {...}}``
and others later. The engine calls :func:`deliver` once, on a rule's *not-triggered →
triggered* edge. New channels add a handler to ``_CHANNELS`` and a validator in
``spec.validate_delivery`` — nothing else changes.
"""

from __future__ import annotations

import asyncio
import json

from .. import log_events as logx
from ..store.security import store
from . import webpush


def _message(rule, value: float | None) -> dict:
    """The notification content: a title + plain body (for email) and a JSON payload (for the
    browser service worker)."""
    cfg = rule.config_dict()
    criterion = f"{cfg.get('metric', '')} {cfg.get('fromStep', '')} → {cfg.get('toStep', '')}"
    where = rule.project_title or f"Project {rule.project_id}"
    title = f"⚠ {rule.name or 'Notification'}"
    body = f"{where}: {criterion.strip()} crossed its limit."
    if value is not None:
        body += f"\n\nMeasured value: {value:g}."
    return {
        "title": title,
        "body": body,
        "json": json.dumps({
            "title": title,
            "body": body.splitlines()[0],
            "severity": rule.severity,
            "tag": f"pmw-rule-{rule.id}",
            "ruleId": rule.id,
            "connectionId": rule.connection_id,
            "projectId": rule.project_id,
        }),
    }


async def _deliver_webpush(rule, msg: dict) -> None:
    """Send a browser push to every subscription of the users assigned to the rule's
    connection. A subscription the push service reports as gone is removed."""
    public_b64, private_pem = store.vapid_keys()
    subject = store.push_subject
    usernames = store.usernames_for_connection(rule.connection_id)
    body = msg["json"].encode("utf-8")
    for sub in store.subscriptions_for_users(usernames):
        try:
            await webpush.send(
                sub, body, private_pem=private_pem, public_b64=public_b64, subject=subject
            )
        except webpush.PushGone:
            store.delete_push_subscription(sub["endpoint"])
        except Exception as exc:  # noqa: BLE001 — one dead endpoint must not stop the rest
            logx.warn(
                f"web push failed for a subscriber: {exc}",
                operation="notifications", tag=logx.TAG_DATA,
            )


async def _deliver_smtp(rule, msg: dict) -> None:
    """Email the alert. Recipients are the rule's configured addresses, or — when it names
    none — the email addresses of the users assigned to its connection."""
    settings = store.smtp_settings(with_secret=True)
    if not settings.get("configured"):
        logx.warn(
            "notification email skipped: SMTP is not configured (Admin → Notifications).",
            operation="notifications", tag=logx.TAG_DATA,
        )
        return
    cfg = rule.delivery_dict().get("smtp") or {}
    recipients = [r for r in (cfg.get("recipients") or []) if r]
    if not recipients:
        recipients = store.emails_for_connection(rule.connection_id)
    recipients = list(dict.fromkeys(recipients))
    if not recipients:
        logx.warn(
            f"notification email skipped: no recipients for rule {rule.id}.",
            operation="notifications", tag=logx.TAG_DATA,
        )
        return
    from . import smtp as smtp_mod

    await asyncio.to_thread(smtp_mod.send_email, settings, recipients, msg["title"], msg["body"])


# Channel registry — the extension point for new remote-notification kinds.
_CHANNELS = {
    "webpush": _deliver_webpush,
    "smtp": _deliver_smtp,
}


async def deliver(rule, value: float | None) -> None:
    """Fire every enabled remote channel for a rule that has just triggered."""
    delivery = rule.delivery_dict()
    if not delivery:
        return
    msg = _message(rule, value)
    for channel in delivery:
        handler = _CHANNELS.get(channel)
        if handler is None:
            continue
        try:
            await handler(rule, msg)
        except Exception as exc:  # noqa: BLE001
            logx.warn(
                f"notification delivery ({channel}) failed: {exc}",
                operation="notifications", tag=logx.TAG_DATA,
            )
