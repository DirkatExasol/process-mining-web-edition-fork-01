"""Shared TOTP two-factor helpers used by BOTH the app (GUI) and admin servers.

Wraps pyotp so the enrolment and verification ceremonies are written once. TOTP is
an *optional*, admin-gated second factor layered on top of the password (or LDAP)
sign-in — it never replaces the password.

Two-step login needs the server to remember, between the password step and the
code step, that the password already verified. As with passkeys, that state lives
in a short-lived Fernet-signed cookie (`crypto.sign_session` / `read_session`),
never a server-side session — so no real session exists until the code is checked.
"""

from __future__ import annotations

import json
import secrets

import pyotp
import qrcode

from .. import config
from ..store import crypto

# The pending-login cookie is short (the user just typed their password); the
# setup cookie a little longer (they may need to install an app first).
PENDING_TTL_SECS = 300
SETUP_TTL_SECS = 600
PENDING_COOKIE = "pmw_mfa_pending"
SETUP_COOKIE = "pmw_mfa_setup"

# A tolerance of ±1 time-step (30 s) absorbs clock skew between server and phone.
_VALID_WINDOW = 1


# ── Enrolment ─────────────────────────────────────────────────────────────────


def new_secret() -> str:
    """A fresh base32 TOTP secret."""
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, username: str) -> str:
    """The otpauth:// URI to hand an authenticator app (encodes issuer + account)."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=config.MFA_ISSUER)


def qr_svg(uri: str) -> str:
    """Render the provisioning URI as a self-contained SVG string (no PIL needed).

    Built by hand from the QR matrix rather than via qrcode's SVG factory: that
    factory emits namespaced ``<svg:rect>`` elements sized in ``mm`` with no
    viewBox, which the HTML parser drops when the markup is injected through
    ``innerHTML`` (so the code renders blank). This plain SVG — a viewBox, one
    white backdrop and black unit squares, scaling to its container — inlines
    cleanly in both the SPA and the admin page."""
    qr = qrcode.QRCode(border=2)  # 2-module quiet zone, included in the matrix
    qr.add_data(uri)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    rects = [
        f'<rect x="{x}" y="{y}" width="1" height="1"/>'
        for y, row in enumerate(matrix)
        for x, dark in enumerate(row)
        if dark
    ]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
        f'width="100%" height="100%" shape-rendering="crispEdges">'
        f'<rect width="{n}" height="{n}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g></svg>'
    )


def verify_code(secret: str, code: str) -> bool:
    """True if `code` is a currently-valid TOTP for `secret` (±1 step of skew)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=_VALID_WINDOW)
    except Exception:  # noqa: BLE001 — a malformed secret is simply "not valid"
        return False


def generate_recovery_codes(n: int = 10) -> list[str]:
    """Human-friendly one-time recovery codes, e.g. `a1b2c3d4-e5f6g7h8`."""
    alphabet = "abcdefghijkmnpqrstuvwxyz23456789"  # no look-alikes (0/o, 1/l)

    def block() -> str:
        return "".join(secrets.choice(alphabet) for _ in range(8))

    return [f"{block()}-{block()}" for _ in range(n)]


# ── Challenge cookies (pre-session state) ────────────────────────────────────
# These share the Fernet key with the session cookies, so their audience is
# namespaced ("mfa-app" / "mfa-admin") to make it impossible for a pre-auth MFA
# cookie to be structurally accepted as a real session cookie (whose audience is
# "app" / "admin") — belt-and-suspenders alongside the distinct cookie names.


def _mfa_aud(aud: str) -> str:
    return f"mfa-{aud}"


def make_pending_cookie(*, username: str, aud: str) -> str:
    """Signed proof that `username` passed the password step; aud: 'app' | 'admin'."""
    payload = json.dumps(
        {"u": username, "a": _mfa_aud(aud), "k": "pending"}
    ).encode("utf-8")
    return crypto.sign_session(payload)


def read_pending_cookie(token: str, *, aud: str) -> str | None:
    """Return the username if the pending cookie is valid, unexpired and matches aud."""
    raw = crypto.read_session(token or "", PENDING_TTL_SECS)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if data.get("k") != "pending" or data.get("a") != _mfa_aud(aud):
        return None
    return data.get("u") or None


def make_setup_cookie(*, username: str, secret: str, aud: str) -> str:
    """Hold the not-yet-confirmed secret so it is only persisted once a code proves
    the authenticator was set up correctly (no half-enrolled rows)."""
    payload = json.dumps(
        {"u": username, "s": secret, "a": _mfa_aud(aud), "k": "setup"}
    ).encode("utf-8")
    return crypto.sign_session(payload)


def read_setup_cookie(token: str, *, username: str, aud: str) -> str | None:
    """Return the pending secret if the setup cookie is valid and belongs to this
    user + audience; else None."""
    raw = crypto.read_session(token or "", SETUP_TTL_SECS)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if data.get("k") != "setup" or data.get("a") != _mfa_aud(aud):
        return None
    if (data.get("u") or "").lower() != (username or "").lower():
        return None
    return data.get("s") or None
