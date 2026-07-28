"""License verification.

The app ships only the Ed25519 *public* key below, so it can verify a license
but can never mint one — that requires the private key held offline by the
issuer (see the separate license-issuer tool). A license is a plain, readable
JSON document plus a detached signature over the canonical form of its payload:

    {"license": {"licensee": "...", "issued": "...", "expires": "YYYY-MM-DD",
                 "version": 1},
     "signature": "<hex ed25519 signature over the canonical license object>"}

The only constraint enforced today is the expiry date. The signature makes the
payload unforgeable; it cannot stop someone who controls the host from patching
this (open) verifier or rolling back the clock — an accepted limitation of any
offline check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .config import DEMO_MARKER_PATH, LICENSE_GRACE_SECS, LICENSE_PATH

# Public half of the issuer keypair. Safe to publish; the matching private key
# lives only in the offline issuer. Rotating the issuer key means updating this.
_PUBLIC_KEY_HEX = "59afd128c103c3c6bb4013683af9612f858d134be5d59102809996304cdb798f"
_PUBLIC_KEY = Ed25519PublicKey.from_public_bytes(bytes.fromhex(_PUBLIC_KEY_HEX))


@dataclass(frozen=True)
class LicenseStatus:
    """Outcome of evaluating a license. `state` is one of:
    valid | expired | invalid | missing."""

    state: str
    licensee: str = ""
    issued: str = ""
    expires: str = ""
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.state == "valid"

    def public(self) -> dict:
        return {
            "state": self.state,
            "licensee": self.licensee,
            "issued": self.issued,
            "expires": self.expires,
            "message": self.message,
        }


def _canonical(license_obj: dict) -> bytes:
    """Exact bytes covered by the signature — MUST match the issuer's canonical()."""
    return json.dumps(license_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify(document: dict) -> LicenseStatus:
    """Verify a parsed license document (signature + expiry). Pure, no I/O."""
    if not isinstance(document, dict):
        return LicenseStatus("invalid", message="License file is not a JSON object.")

    license_obj = document.get("license")
    signature_hex = document.get("signature")
    if not isinstance(license_obj, dict) or not isinstance(signature_hex, str):
        return LicenseStatus("invalid", message="License file is missing 'license' or 'signature'.")

    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return LicenseStatus("invalid", message="License signature is malformed.")

    try:
        _PUBLIC_KEY.verify(signature, _canonical(license_obj))
    except InvalidSignature:
        return LicenseStatus("invalid", message="License signature is not valid.")

    licensee = str(license_obj.get("licensee", ""))
    issued = str(license_obj.get("issued", ""))
    expires = str(license_obj.get("expires", ""))
    try:
        expiry_date = date.fromisoformat(expires)
    except ValueError:
        return LicenseStatus("invalid", licensee=licensee, issued=issued,
                             message="License has no valid expiry date.")

    if expiry_date < date.today():
        return LicenseStatus("expired", licensee=licensee, issued=issued, expires=expires,
                             message=f"License for {licensee!r} expired on {expires}.")

    return LicenseStatus("valid", licensee=licensee, issued=issued, expires=expires,
                         message=f"Licensed to {licensee!r}, valid until {expires}.")


def evaluate() -> LicenseStatus:
    """Read and verify the license file on disk. Never raises."""
    try:
        raw = LICENSE_PATH.read_bytes()
    except FileNotFoundError:
        return LicenseStatus("missing", message="No license installed.")
    except OSError as exc:
        return LicenseStatus("invalid", message=f"License file could not be read: {exc}.")

    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return LicenseStatus("invalid", message="License file is not valid JSON.")

    return verify(document)


def install(raw: bytes) -> LicenseStatus:
    """Validate an uploaded license and, if its signature is authentic, store it.

    A bad signature (forged/corrupt) is rejected and never written. A validly
    signed but expired license is stored (so its details are visible) and
    reported as expired.
    """
    try:
        document = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return LicenseStatus("invalid", message="Uploaded file is not valid JSON.")

    status = verify(document)
    if status.state in ("invalid", "missing"):
        return status

    # Re-serialise from the parsed document so we store a clean, canonical file.
    LICENSE_PATH.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return status


def uninstall() -> bool:
    """Remove the installed license, if any. Returns True if a file was removed."""
    try:
        LICENSE_PATH.unlink()
        return True
    except FileNotFoundError:
        return False


# ── One-time demo grace ─────────────────────────────────────────────────────────
#
# The demo window is granted ONCE per installation. The first unlicensed run
# anchors a deadline in DEMO_MARKER_PATH; it is never renewed by restarting, so an
# unlicensed instance can't keep resetting its own grace period. Uses wall-clock
# time (persisted), so a clock rollback can extend it — the same accepted
# limitation as the expiry check itself.


def _now() -> datetime:
    return datetime.now(timezone.utc)


# If the marker can't be persisted (read-only/unwritable data dir), we must NOT
# re-anchor `now + grace` on every poll — that would make the demo never expire
# (enforcement fail-open). Instead the first-anchored deadline is held in memory
# for this process so the window still counts down.
_unpersisted_deadline: datetime | None = None


def demo_deadline(create: bool) -> datetime | None:
    """The one-time demo grace deadline (UTC), or None if no demo is available.

    Reads the persisted marker if present. If absent and ``create`` is True, anchors
    a new window at now + grace and persists it (this is the single act that "spends"
    the one-time demo). If absent and ``create`` is False, returns None without
    consuming it — used by read-only callers such as the login-panel status.
    """
    try:
        data = json.loads(DEMO_MARKER_PATH.read_text(encoding="utf-8"))
        deadline = datetime.fromisoformat(str(data["deadline"]))
        # A hand-edited/corrupt marker may carry a naive datetime; normalise it to
        # UTC so the aware-vs-naive subtraction in demo_remaining_secs never raises
        # (which would otherwise 500 the status endpoint and kill the watchdog loop).
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline
    except (FileNotFoundError, ValueError, KeyError, TypeError, OSError):
        pass

    if not create:
        return None

    global _unpersisted_deadline
    # A marker we anchored earlier this process but couldn't persist: reuse it so an
    # unwritable data dir doesn't reset the countdown on every poll (fail-open).
    if _unpersisted_deadline is not None:
        return _unpersisted_deadline

    deadline = _now() + timedelta(seconds=LICENSE_GRACE_SECS)
    try:
        DEMO_MARKER_PATH.write_text(
            json.dumps({"started": _now().isoformat(), "deadline": deadline.isoformat()},
                       indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        # Couldn't persist — anchor in memory so the window still expires within this
        # process instead of re-anchoring (and thus never expiring) on every poll.
        _unpersisted_deadline = deadline
    return deadline


def demo_remaining_secs(create: bool) -> int:
    """Seconds left in the one-time demo window (0 when none is available/left)."""
    deadline = demo_deadline(create=create)
    if deadline is None:
        return 0
    return max(0, int((deadline - _now()).total_seconds()))


def reset_demo() -> bool:
    """Clear the one-time demo marker so a fresh window can be granted. Returns
    True if a marker was removed. (Recovery valve; see PMW_RESET_DEMO.)"""
    try:
        DEMO_MARKER_PATH.unlink()
        return True
    except FileNotFoundError:
        return False
