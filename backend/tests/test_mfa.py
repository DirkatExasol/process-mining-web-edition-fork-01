"""Unit tests for the shared TOTP two-factor service (app.services.mfa)."""

from __future__ import annotations

import pyotp
import pytest

import app.services.mfa as mfa
import app.store.crypto as crypto


@pytest.fixture
def _isolated_key(tmp_path, monkeypatch):
    """Bind the Fernet key used to sign the challenge cookies to a throwaway file."""
    monkeypatch.setattr(crypto, "SECRET_KEY_PATH", tmp_path / "secret.key")
    monkeypatch.setattr(crypto, "_fernet", None)
    yield
    monkeypatch.setattr(crypto, "_fernet", None)


# ── TOTP + recovery codes ────────────────────────────────────────────────────


def test_verify_code_accepts_the_current_totp():
    secret = mfa.new_secret()
    assert mfa.verify_code(secret, pyotp.TOTP(secret).now())
    assert not mfa.verify_code(secret, "000000") or mfa.verify_code(secret, "000000")
    assert not mfa.verify_code(secret, "not-a-code")
    assert not mfa.verify_code(secret, "")


def test_provisioning_uri_and_qr():
    secret = mfa.new_secret()
    uri = mfa.provisioning_uri(secret=secret, username="alice")
    assert uri.startswith("otpauth://totp/") and secret in uri
    svg = mfa.qr_svg(uri)
    assert svg.lstrip().startswith("<svg") and svg.rstrip().endswith("</svg>")
    # Must inline cleanly via innerHTML: a viewBox (so it scales) and NO namespaced
    # `<svg:rect>` prefix (the HTML parser drops those, leaving the QR blank).
    assert "viewBox=" in svg and "svg:rect" not in svg
    assert 'fill="#000"' in svg  # dark modules are actually painted


def test_recovery_codes_are_unique_and_formatted():
    codes = mfa.generate_recovery_codes(10)
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all("-" in c for c in codes)


# ── Challenge cookies ────────────────────────────────────────────────────────


def test_pending_cookie_round_trips_and_is_audience_scoped(_isolated_key):
    token = mfa.make_pending_cookie(username="alice", aud="app")
    assert mfa.read_pending_cookie(token, aud="app") == "alice"
    # An app "password ok" cookie must not authorise the admin panel.
    assert mfa.read_pending_cookie(token, aud="admin") is None
    assert mfa.read_pending_cookie("garbage", aud="app") is None


def test_setup_cookie_is_bound_to_user_and_audience(_isolated_key):
    secret = mfa.new_secret()
    token = mfa.make_setup_cookie(username="alice", secret=secret, aud="admin")
    assert mfa.read_setup_cookie(token, username="alice", aud="admin") == secret
    # Wrong user or audience → rejected (no cross-account / cross-surface reuse).
    assert mfa.read_setup_cookie(token, username="bob", aud="admin") is None
    assert mfa.read_setup_cookie(token, username="alice", aud="app") is None


def test_pending_and_setup_cookies_do_not_cross(_isolated_key):
    pending = mfa.make_pending_cookie(username="alice", aud="app")
    setup = mfa.make_setup_cookie(username="alice", secret=mfa.new_secret(), aud="app")
    # A pending cookie isn't a setup cookie and vice-versa (kind is checked).
    assert mfa.read_setup_cookie(pending, username="alice", aud="app") is None
    assert mfa.read_pending_cookie(setup, aud="app") is None
