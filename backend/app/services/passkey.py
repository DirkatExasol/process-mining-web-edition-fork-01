"""Shared WebAuthn / passkey helpers used by BOTH the app (GUI) and admin servers.

Wraps py_webauthn so the registration and authentication ceremonies are written
once. The Relying Party ID is the request host (no port), so the app and admin on
the same host share one passkey; expected origins default to the request's own
origin. Both are overridable via config (PMW_PASSKEY_RP_ID / PMW_PASSKEY_ORIGINS)
for split-subdomain deployments.

The pre-auth challenge (no session exists yet at login) is held in a short-lived
Fernet-signed cookie via `crypto.sign_session` / `read_session` (TTL-checked).
"""

from __future__ import annotations

import hashlib
import json

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .. import config
from ..store import crypto

CHALLENGE_TTL_SECS = 300
CHALLENGE_COOKIE = "pmw_pk_challenge"


def resolve_rp(host: str, origin: str) -> tuple[str, list[str]]:
    """(rp_id, expected_origins) — config overrides, else derived from the request.
    rp_id is the host without a port; origins default to the request's own origin."""
    rp_id = config.PASSKEY_RP_ID or (host or "localhost")
    origins = config.PASSKEY_ORIGINS or ([origin] if origin else [])
    return rp_id, origins


# ── Registration (enrol a device) ────────────────────────────────────────────


def _user_handle(username: str) -> bytes:
    """A STABLE per-account WebAuthn user handle (user.id), derived from the
    username. py_webauthn otherwise invents a random handle on every begin, so the
    same account would look like a different user each time — which confuses
    platform authenticators (iCloud Keychain, Windows Hello) and can leave orphan
    passkeys. A hash keeps it stable without exposing the raw username."""
    return hashlib.sha256(("pmw-user:" + (username or "").strip().lower()).encode("utf-8")).digest()


def registration_options(
    *, rp_id: str, username: str, display_name: str, existing_ids: list[str]
) -> tuple[str, bytes]:
    """Returns (options-JSON for the browser, challenge bytes to remember)."""
    opts = generate_registration_options(
        rp_id=rp_id,
        rp_name=config.PASSKEY_RP_NAME,
        user_id=_user_handle(username),
        user_name=username,
        user_display_name=display_name or username,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in existing_ids
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.DISCOURAGED,  # username-first
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return options_to_json(opts), opts.challenge


def verify_registration(
    *, credential, challenge: bytes, rp_id: str, origins: list[str]
) -> dict:
    v = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp_id,
        expected_origin=origins,
    )
    return {
        "credential_id": bytes_to_base64url(v.credential_id),
        "public_key": bytes_to_base64url(v.credential_public_key),
        "sign_count": v.sign_count,
    }


# ── Authentication (sign in) ─────────────────────────────────────────────────


def authentication_options(*, rp_id: str, allow_ids: list[str]) -> tuple[str, bytes]:
    opts = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c)) for c in allow_ids
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options_to_json(opts), opts.challenge


def decoy_allow_ids(username: str) -> list[str]:
    """A stable, plausible-looking credential id for an account that has no real
    passkey (unknown / disabled / not allowed). Derived from an install secret so
    it can't be told apart from a genuine id, and deterministic per-username so
    repeated probes get the same answer — the two properties that let the *begin*
    endpoint answer identically whether or not the account exists (no enumeration).

    Verification later fails for these (no matching stored credential), exactly as
    it would for a real id the user can't satisfy — so the decoy never grants access."""
    seed = crypto.passkey_decoy_seed()
    digest = hashlib.sha256(seed + b"|" + (username or "").strip().lower().encode("utf-8")).digest()
    return [bytes_to_base64url(digest)]


def verify_authentication(
    *,
    credential,
    challenge: bytes,
    rp_id: str,
    origins: list[str],
    public_key: str,
    sign_count: int,
) -> int:
    """Verify the assertion; returns the new sign count (raises on failure/replay)."""
    v = verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp_id,
        expected_origin=origins,
        credential_public_key=base64url_to_bytes(public_key),
        credential_current_sign_count=sign_count,
    )
    return v.new_sign_count


# ── Challenge cookie (pre-auth safe) ─────────────────────────────────────────


def make_challenge_cookie(*, challenge: bytes, username: str, kind: str, aud: str) -> str:
    """kind: 'reg' | 'auth'; aud: 'app' | 'admin'."""
    payload = json.dumps(
        {"c": bytes_to_base64url(challenge), "u": username, "k": kind, "a": aud}
    ).encode("utf-8")
    return crypto.sign_session(payload)


def read_challenge_cookie(token: str, *, kind: str, aud: str) -> dict | None:
    """Return {'challenge': bytes, 'username': str} if the cookie is valid, unexpired
    and matches the expected kind/audience; else None."""
    raw = crypto.read_session(token, CHALLENGE_TTL_SECS)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if data.get("k") != kind or data.get("a") != aud:
        return None
    try:
        return {"challenge": base64url_to_bytes(data["c"]), "username": data.get("u", "")}
    except Exception:  # noqa: BLE001
        return None
