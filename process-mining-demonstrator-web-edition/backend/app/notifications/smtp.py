"""Send email via a configured SMTP server — the plumbing behind the "email" delivery channel
and the admin "send a test email" action. Synchronous (stdlib ``smtplib``); call it off the
event loop with ``asyncio.to_thread``."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


def _from_header(settings: dict) -> str:
    addr = (settings.get("from") or "").strip()
    name = (settings.get("fromName") or "").strip()
    return formataddr((name, addr)) if name else addr


def send_email(settings: dict, recipients: list[str], subject: str, body: str) -> None:
    """Send a plain-text email to `recipients`. `settings` comes from
    ``store.smtp_settings(with_secret=True)``: host, port, security (none|starttls|ssl),
    username, password, from, fromName. Raises on any SMTP/connection error."""
    host = (settings.get("host") or "").strip()
    if not host:
        raise ValueError("SMTP is not configured (no host).")
    port = int(settings.get("port") or 587)
    security = (settings.get("security") or "starttls").lower()
    username = (settings.get("username") or "").strip()
    password = settings.get("password") or ""

    msg = EmailMessage()
    msg["From"] = _from_header(settings)
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.ehlo()
            if security == "starttls":
                server.starttls(context=context)
                server.ehlo()
            if username:
                server.login(username, password)
            server.send_message(msg)
