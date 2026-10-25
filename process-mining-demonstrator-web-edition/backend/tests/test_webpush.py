"""Web Push crypto (no pywebpush): the aes128gcm round-trip (RFC 8291) and the VAPID ES256
JWT (RFC 8292). Pure crypto — no DB, no network."""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.notifications import webpush as wp


def test_b64url_roundtrip_no_padding():
    raw = bytes(range(20))
    enc = wp.b64u(raw)
    assert "=" not in enc and wp.b64u_dec(enc) == raw


def test_message_encryption_roundtrips_to_the_subscriber():
    # A subscriber (user agent) keypair + auth secret, as a browser would produce.
    ua_priv = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua_priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"  # 16-byte auth secret

    plaintext = "⚠ Security check slow: Avg Time 17:00 (limit 16:00)".encode()
    body = wp.encrypt(plaintext, wp.b64u(ua_pub), wp.b64u(auth))

    # The aes128gcm header: 16-byte salt, 4-byte record size, 1-byte key id length (65).
    assert body[20] == 65
    assert wp._decrypt(body, ua_priv, auth) == plaintext


def test_vapid_header_is_a_verifiable_es256_jwt():
    pem, pub_b64 = wp.generate_vapid()
    # The public key is an uncompressed P-256 point (65 bytes).
    assert len(wp.b64u_dec(pub_b64)) == 65

    endpoint = "https://push.example.com/send/abc123"
    header = wp.vapid_authorization(endpoint, pem, pub_b64, "mailto:ops@example.com")
    assert header.startswith("vapid t=") and f",k={pub_b64}" in header

    token = header[len("vapid t="):].split(",k=")[0]
    hdr_b64, pay_b64, sig_b64 = token.split(".")
    payload = json.loads(wp.b64u_dec(pay_b64))
    assert payload["aud"] == "https://push.example.com"
    assert payload["sub"] == "mailto:ops@example.com" and payload["exp"] > 0

    # The signature verifies against the VAPID public key (raw r||s → DER for cryptography).
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), wp.b64u_dec(pub_b64))
    sig = wp.b64u_dec(sig_b64)
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    pub.verify(der, f"{hdr_b64}.{pay_b64}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if bad


def test_wrong_key_cannot_decrypt():
    ua_priv = ec.generate_private_key(ec.SECP256R1())
    ua_pub = ua_priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    body = wp.encrypt(b"secret", wp.b64u(ua_pub), wp.b64u(b"0123456789abcdef"))
    other = ec.generate_private_key(ec.SECP256R1())
    try:
        wp._decrypt(body, other, b"0123456789abcdef")
        assert False, "decryption with the wrong key should fail"
    except Exception:
        pass
