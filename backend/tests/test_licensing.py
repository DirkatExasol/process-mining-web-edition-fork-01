"""License verification tests.

The real signing key lives only in the offline issuer, so these tests mint an
*ephemeral* keypair and patch the module's embedded public key to match. That
exercises the whole verify/install/evaluate path without ever needing the
production private key in the repo.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import licensing


@pytest.fixture
def signer(monkeypatch):
    """Patch the verifier's public key to an ephemeral one and return a signer
    that produces documents that verifier will accept."""
    priv = Ed25519PrivateKey.generate()
    monkeypatch.setattr(licensing, "_PUBLIC_KEY", priv.public_key())

    def sign(license_obj: dict) -> dict:
        signature = priv.sign(licensing._canonical(license_obj))
        return {"license": license_obj, "signature": signature.hex()}

    return sign


def _license(expires: str, licensee: str = "Acme GmbH") -> dict:
    return {"licensee": licensee, "issued": "2026-01-01", "expires": expires, "version": 1}


def test_valid_license(signer):
    future = (date.today() + timedelta(days=30)).isoformat()
    status = licensing.verify(signer(_license(future)))
    assert status.state == "valid"
    assert status.ok
    assert status.licensee == "Acme GmbH"
    assert status.expires == future


def test_expiry_is_inclusive_of_today(signer):
    today = date.today().isoformat()
    status = licensing.verify(signer(_license(today)))
    assert status.state == "valid"


def test_expired_license(signer):
    past = (date.today() - timedelta(days=1)).isoformat()
    status = licensing.verify(signer(_license(past)))
    assert status.state == "expired"
    assert not status.ok
    assert status.licensee == "Acme GmbH"  # details still surfaced


def test_tampered_payload_is_rejected(signer):
    future = (date.today() + timedelta(days=30)).isoformat()
    doc = signer(_license(future))
    doc["license"]["licensee"] = "Evil Corp"  # signature no longer matches
    status = licensing.verify(doc)
    assert status.state == "invalid"
    assert "signature" in status.message.lower()


def test_unsigned_document_is_rejected(signer):
    future = (date.today() + timedelta(days=30)).isoformat()
    status = licensing.verify({"license": _license(future), "signature": "deadbeef"})
    assert status.state == "invalid"


def test_malformed_documents(signer):
    assert licensing.verify({}).state == "invalid"
    assert licensing.verify({"license": _license("2099-01-01")}).state == "invalid"  # no sig
    assert licensing.verify({"license": {}, "signature": "zz"}).state == "invalid"  # bad hex


def test_bad_expiry_date(signer):
    status = licensing.verify(signer(_license("not-a-date")))
    assert status.state == "invalid"
    assert "expiry" in status.message.lower()


def test_evaluate_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(licensing, "LICENSE_PATH", tmp_path / "nope.json")
    status = licensing.evaluate()
    assert status.state == "missing"


def test_evaluate_invalid_json(monkeypatch, tmp_path):
    path = tmp_path / "license.json"
    path.write_text("{ not json")
    monkeypatch.setattr(licensing, "LICENSE_PATH", path)
    assert licensing.evaluate().state == "invalid"


def test_install_stores_valid_and_rejects_forged(monkeypatch, tmp_path, signer):
    path = tmp_path / "license.json"
    monkeypatch.setattr(licensing, "LICENSE_PATH", path)

    future = (date.today() + timedelta(days=30)).isoformat()
    good = json.dumps(signer(_license(future))).encode()
    status = licensing.install(good)
    assert status.state == "valid"
    assert path.exists()
    assert licensing.evaluate().state == "valid"

    # A forged upload must not overwrite the good license already on disk.
    forged = signer(_license(future))
    forged["signature"] = "00" * 64
    status = licensing.install(json.dumps(forged).encode())
    assert status.state == "invalid"
    assert licensing.evaluate().state == "valid"  # untouched


def test_install_rejects_non_json(monkeypatch, tmp_path):
    path = tmp_path / "license.json"
    monkeypatch.setattr(licensing, "LICENSE_PATH", path)
    assert licensing.install(b"\xff\xfenonsense").state == "invalid"
    assert not path.exists()


def test_uninstall(monkeypatch, tmp_path, signer):
    path = tmp_path / "license.json"
    monkeypatch.setattr(licensing, "LICENSE_PATH", path)

    assert licensing.uninstall() is False  # nothing installed yet

    future = (date.today() + timedelta(days=30)).isoformat()
    licensing.install(json.dumps(signer(_license(future))).encode())
    assert path.exists()

    assert licensing.uninstall() is True
    assert not path.exists()
    assert licensing.evaluate().state == "missing"


def test_demo_window_is_granted_once_and_not_renewed(monkeypatch, tmp_path):
    marker = tmp_path / "demo_grace.json"
    monkeypatch.setattr(licensing, "DEMO_MARKER_PATH", marker)
    monkeypatch.setattr(licensing, "LICENSE_GRACE_SECS", 1800)

    # Read-only probe before the demo is spent: no window yet, and no marker written.
    assert licensing.demo_remaining_secs(create=False) == 0
    assert not marker.exists()

    # First consuming call anchors the window and persists the marker.
    first = licensing.demo_remaining_secs(create=True)
    assert 0 < first <= 1800
    assert marker.exists()
    anchored = marker.read_text()

    # A later consuming call (e.g. after a restart) must NOT re-anchor a new window.
    second = licensing.demo_remaining_secs(create=True)
    assert second <= first
    assert marker.read_text() == anchored  # deadline unchanged


def test_naive_datetime_marker_does_not_crash(monkeypatch, tmp_path):
    """A corrupt/hand-edited marker with a naive (tz-less) deadline must not raise
    (it would otherwise 500 the status endpoint and kill the watchdog loop)."""
    marker = tmp_path / "demo_grace.json"
    monkeypatch.setattr(licensing, "DEMO_MARKER_PATH", marker)
    # Far-future naive datetime — previously triggered a TypeError on subtraction.
    marker.write_text('{"started": "x", "deadline": "2099-01-01T00:00:00"}')
    remaining = licensing.demo_remaining_secs(create=False)  # must not raise
    assert remaining > 0


def test_spent_demo_window_reports_zero(monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    marker = tmp_path / "demo_grace.json"
    monkeypatch.setattr(licensing, "DEMO_MARKER_PATH", marker)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    marker.write_text(f'{{"started": "x", "deadline": "{past}"}}')

    assert licensing.demo_remaining_secs(create=True) == 0  # never re-anchors


def test_reset_demo(monkeypatch, tmp_path):
    marker = tmp_path / "demo_grace.json"
    monkeypatch.setattr(licensing, "DEMO_MARKER_PATH", marker)
    monkeypatch.setattr(licensing, "LICENSE_GRACE_SECS", 1800)

    assert licensing.reset_demo() is False  # nothing to clear
    licensing.demo_deadline(create=True)
    assert marker.exists()
    assert licensing.reset_demo() is True
    assert not marker.exists()
    # After a reset a brand-new window can be granted.
    assert licensing.demo_remaining_secs(create=True) > 0


def test_license_status_endpoint(monkeypatch, tmp_path):
    """The /api/license/status endpoint reports demo state + one-time countdown."""
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(licensing, "DEMO_MARKER_PATH", tmp_path / "demo_grace.json")
    monkeypatch.setattr(licensing, "LICENSE_GRACE_SECS", 600)

    # Not constructing via `with` → the lifespan (and its watchdog) never starts.
    client = TestClient(main.app)

    # Licensed: no demo, no countdown.
    monkeypatch.setattr(
        licensing, "evaluate",
        lambda: licensing.LicenseStatus("valid", licensee="X", expires="2099-01-01"),
    )
    body = client.get("/api/license/status").json()
    assert body["demoMode"] is False
    assert body["remainingSeconds"] is None

    # Unlicensed with a fresh demo window available (marker gets anchored elsewhere;
    # the read-only endpoint reports 0 until the window is actually consumed).
    monkeypatch.setattr(
        licensing, "evaluate", lambda: licensing.LicenseStatus("missing", message="none")
    )
    # Simulate the watchdog having consumed the demo window.
    licensing.demo_deadline(create=True)
    body = client.get("/api/license/status").json()
    assert body["demoMode"] is True
    assert 0 < body["remainingSeconds"] <= 600
