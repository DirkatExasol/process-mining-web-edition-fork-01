"""Unit tests for the shared WebAuthn/passkey service (app.services.passkey).

The full authenticator ceremony (verify_registration / verify_authentication with
a real attestation) can't run headlessly, so these cover the parts that don't need
a device: RP-ID / origin derivation and the pre-auth challenge cookie.
"""

from __future__ import annotations

import pytest

import app.config as config
import app.services.passkey as passkey
import app.store.crypto as crypto


@pytest.fixture
def _isolated_key(tmp_path, monkeypatch):
    """Bind the Fernet key used to sign challenge cookies to a throwaway file."""
    monkeypatch.setattr(crypto, "SECRET_KEY_PATH", tmp_path / "secret.key")
    monkeypatch.setattr(crypto, "_fernet", None)
    yield
    monkeypatch.setattr(crypto, "_fernet", None)


# ── RP-ID / origin derivation ─────────────────────────────────────────────────


def test_resolve_rp_derives_from_request_by_default(monkeypatch):
    monkeypatch.setattr(config, "PASSKEY_RP_ID", "")
    monkeypatch.setattr(config, "PASSKEY_ORIGINS", [])
    rp_id, origins = passkey.resolve_rp("app.example.com", "https://app.example.com:8443")
    # RP ID is the bare host (no port) so app :8443 and admin :8453 share one passkey.
    assert rp_id == "app.example.com"
    assert origins == ["https://app.example.com:8443"]


def test_resolve_rp_config_overrides_win(monkeypatch):
    monkeypatch.setattr(config, "PASSKEY_RP_ID", "example.com")
    monkeypatch.setattr(config, "PASSKEY_ORIGINS", ["https://app.example.com", "https://admin.example.com"])
    rp_id, origins = passkey.resolve_rp("app.example.com", "https://app.example.com")
    assert rp_id == "example.com"
    assert origins == ["https://app.example.com", "https://admin.example.com"]


def test_resolve_rp_falls_back_to_localhost(monkeypatch):
    monkeypatch.setattr(config, "PASSKEY_RP_ID", "")
    monkeypatch.setattr(config, "PASSKEY_ORIGINS", [])
    rp_id, origins = passkey.resolve_rp("", "")
    assert rp_id == "localhost" and origins == []


# ── Challenge cookie (pre-auth safe) ─────────────────────────────────────────


def test_challenge_cookie_round_trips(_isolated_key):
    token = passkey.make_challenge_cookie(
        challenge=b"\x01\x02\x03random", username="alice", kind="auth", aud="app"
    )
    got = passkey.read_challenge_cookie(token, kind="auth", aud="app")
    assert got is not None
    assert got["challenge"] == b"\x01\x02\x03random"
    assert got["username"] == "alice"


def test_challenge_cookie_rejects_wrong_kind(_isolated_key):
    token = passkey.make_challenge_cookie(
        challenge=b"abc", username="alice", kind="reg", aud="app"
    )
    # A registration challenge must not satisfy an authentication check.
    assert passkey.read_challenge_cookie(token, kind="auth", aud="app") is None


def test_challenge_cookie_rejects_wrong_audience(_isolated_key):
    token = passkey.make_challenge_cookie(
        challenge=b"abc", username="alice", kind="auth", aud="app"
    )
    # An app challenge must not be usable to sign into the admin panel.
    assert passkey.read_challenge_cookie(token, kind="auth", aud="admin") is None


def test_challenge_cookie_rejects_tampered_token(_isolated_key):
    token = passkey.make_challenge_cookie(
        challenge=b"abc", username="alice", kind="auth", aud="app"
    )
    # Flip a character inside the signed token — the HMAC check must reject it.
    i = len(token) // 2
    tampered = token[:i] + ("A" if token[i] != "A" else "B") + token[i + 1:]
    assert passkey.read_challenge_cookie(tampered, kind="auth", aud="app") is None
    assert passkey.read_challenge_cookie("garbage", kind="auth", aud="app") is None
