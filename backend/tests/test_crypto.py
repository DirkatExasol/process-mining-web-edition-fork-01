"""Tests for the shared symmetric-crypto helpers (app.store.crypto)."""

from __future__ import annotations

import stat

import pytest

import app.store.crypto as crypto


def test_secret_key_is_created_once_atomically_and_0600(tmp_path, monkeypatch):
    key_path = tmp_path / "sub" / "secret.key"  # parent doesn't exist yet
    monkeypatch.setattr(crypto, "SECRET_KEY_PATH", key_path)
    monkeypatch.setattr(crypto, "_fernet", None)

    f1 = crypto.get_fernet()
    assert key_path.exists()
    # Private from birth — no world/group bits (O_EXCL + mode 0600, no chmod window).
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600

    # A concurrent/second creation attempt must NOT overwrite the existing key.
    original = key_path.read_bytes()
    crypto._create_key_atomically()
    assert key_path.read_bytes() == original

    # A fresh load yields the same working key (round-trips a token from f1).
    monkeypatch.setattr(crypto, "_fernet", None)
    f2 = crypto.get_fernet()
    assert f1.decrypt(f2.encrypt(b"secret")) == b"secret"


def test_zero_byte_key_is_recreated(tmp_path, monkeypatch):
    # A creator killed between O_EXCL-create and write leaves a 0-byte key that would
    # otherwise wedge every service on `Fernet(b"")`. It must be recreated, not fatal.
    key_path = tmp_path / "secret.key"
    key_path.write_bytes(b"")
    monkeypatch.setattr(crypto, "SECRET_KEY_PATH", key_path)
    monkeypatch.setattr(crypto, "_fernet", None)
    f = crypto.get_fernet()
    assert key_path.stat().st_size > 0
    assert f.decrypt(f.encrypt(b"x")) == b"x"


def test_write_private_file_is_0600_from_birth(tmp_path):
    p = tmp_path / "sub" / "active.key"  # parent doesn't exist yet
    crypto.write_private_file(p, "PRIVATE-KEY-PEM")
    assert p.read_text() == "PRIVATE-KEY-PEM"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_write_private_file_refuses_symlink(tmp_path):
    # A pre-planted symlink at the key path must not redirect the private-key write
    # onto its target (O_NOFOLLOW) — it fails closed instead of truncating the target.
    target = tmp_path / "target"
    target.write_text("original")
    link = tmp_path / "active.key"
    link.symlink_to(target)
    with pytest.raises(OSError):
        crypto.write_private_file(link, "SECRET-KEY")
    assert target.read_text() == "original"  # target untouched through the symlink
