"""The internal GUI → compute-backend hop is always TLS-encrypted.

`ensure_internal_cert` mints a dedicated self-signed loopback certificate the
backend serves and the GUI proxy pins its trust to.
"""

from __future__ import annotations

import os
import stat

import pytest


@pytest.fixture
def certdir(tmp_path, monkeypatch):
    import app.config as config

    d = tmp_path / "certs"
    d.mkdir()
    monkeypatch.setattr(config, "CERTS_DIR", d)
    monkeypatch.setattr(config, "INTERNAL_CERT_PATH", d / "internal.crt")
    monkeypatch.setattr(config, "INTERNAL_KEY_PATH", d / "internal.key")
    monkeypatch.setattr(config, "BACKEND_HOST", "127.0.0.1")
    return d


def test_mints_loopback_cert(certdir):
    from app.services import certs, internal_tls

    cert_p, key_p = internal_tls.ensure_internal_cert()
    assert cert_p.exists() and key_p.exists()

    info = certs.inspect(cert_p.read_text(encoding="utf-8"))
    assert info.is_self_signed
    assert "127.0.0.1" in info.sans and "localhost" in info.sans

    # The private key is owner-only.
    assert stat.S_IMODE(os.stat(key_p).st_mode) == 0o600


def test_is_idempotent(certdir):
    from app.services import internal_tls

    cert_p, _ = internal_tls.ensure_internal_cert()
    body = cert_p.read_text(encoding="utf-8")
    internal_tls.ensure_internal_cert()  # a valid cert is reused, not reminted
    assert cert_p.read_text(encoding="utf-8") == body


def test_regenerates_when_missing_or_unparseable(certdir):
    from app.services import internal_tls

    cert_p, _ = internal_tls.ensure_internal_cert()
    original = cert_p.read_text(encoding="utf-8")

    cert_p.unlink()
    regenerated, _ = internal_tls.ensure_internal_cert()
    assert regenerated.exists()

    cert_p.write_text("not a cert", encoding="utf-8")
    fixed, _ = internal_tls.ensure_internal_cert()
    body = fixed.read_text(encoding="utf-8")
    assert "BEGIN CERTIFICATE" in body and body != "not a cert"
    assert body != original  # a fresh keypair, not the deleted one
