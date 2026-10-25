"""Web Push (browser push notifications) — VAPID + message encryption on `cryptography`.

There is no `pywebpush` dependency (and no internet to add one), so this implements the two
relevant specs directly:

- **RFC 8292 (VAPID)** — an ES256 JWT identifying this application server, sent in the
  ``Authorization: vapid t=<jwt>,k=<public key>`` header so the push service accepts the request.
- **RFC 8291 (Message Encryption, ``aes128gcm``)** — the payload is encrypted to the
  subscription's public key so only the subscriber's browser can read it.

The crypto here is pure (no store/DB) so it is unit-testable; a spec round-trip (``_encrypt`` on
the sender side, ``_decrypt`` on the user-agent side) guards the derivation. VAPID keys and
subscriptions are persisted by the security store; `send` takes them as arguments.
"""

from __future__ import annotations

import base64
import json
import os
import time
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_ENC = serialization.Encoding
_PUBF = serialization.PublicFormat


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_dec(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


# ── VAPID keys ─────────────────────────────────────────────────────────────────


def generate_vapid() -> tuple[bytes, str]:
    """A fresh VAPID key: returns (private PEM bytes, public key as base64url of the
    uncompressed P-256 point — the `applicationServerKey` the browser subscribes with)."""
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = priv.public_key().public_bytes(_ENC.X962, _PUBF.UncompressedPoint)
    pem = priv.private_bytes(
        _ENC.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return pem, b64u(pub)


def _load_private(pem: bytes) -> ec.EllipticCurvePrivateKey:
    return serialization.load_pem_private_key(pem, password=None)


def _es256(private: ec.EllipticCurvePrivateKey, signing_input: bytes) -> bytes:
    """JOSE-style raw (r||s) signature for an ES256 JWT (cryptography emits DER)."""
    der = private.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def vapid_authorization(endpoint: str, private_pem: bytes, public_b64: str, subject: str) -> str:
    """The ``Authorization: vapid …`` header value for a push to `endpoint`."""
    parts = urlparse(endpoint)
    aud = f"{parts.scheme}://{parts.netloc}"
    header = {"typ": "JWT", "alg": "ES256"}
    payload = {"aud": aud, "exp": int(time.time()) + 12 * 3600, "sub": subject}
    si = f"{b64u(json.dumps(header).encode())}.{b64u(json.dumps(payload).encode())}".encode()
    sig = b64u(_es256(_load_private(private_pem), si))
    return f"vapid t={si.decode()}.{sig},k={public_b64}"


# ── aes128gcm message encryption (RFC 8291) ──────────────────────────────────────

_RECORD_SIZE = 4096


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _encrypt(
    plaintext: bytes, ua_public: bytes, auth: bytes,
    as_private: ec.EllipticCurvePrivateKey, as_public: bytes, salt: bytes,
) -> bytes:
    """One aes128gcm record (RFC 8291 §3.4 + RFC 8188). Deterministic given `as_private`/`salt`
    so the round-trip test can pin it; `encrypt` wraps it with a fresh key + random salt."""
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    ecdh = as_private.exchange(ec.ECDH(), ua_key)
    # IKM: HKDF over the ECDH secret, salted with the subscription's auth secret.
    key_info = b"WebPush: info\x00" + ua_public + as_public
    ikm = _hkdf(auth, ecdh, key_info, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    # Single, last record: plaintext + 0x02 delimiter, AES-128-GCM (tag appended).
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    # Content-coding header: salt(16) | rs(4) | idlen(1) | keyid(=as_public, 65).
    header = salt + _RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + ciphertext


def encrypt(plaintext: bytes, ua_public_b64: str, auth_b64: str) -> bytes:
    """Encrypt `plaintext` for a subscription's p256dh/auth keys, with a fresh ephemeral key
    and random salt. Returns the ``aes128gcm`` body to POST."""
    as_private = ec.generate_private_key(ec.SECP256R1())
    as_public = as_private.public_key().public_bytes(_ENC.X962, _PUBF.UncompressedPoint)
    return _encrypt(
        plaintext, b64u_dec(ua_public_b64), b64u_dec(auth_b64),
        as_private, as_public, os.urandom(16),
    )


def _decrypt(body: bytes, ua_private: ec.EllipticCurvePrivateKey, auth: bytes) -> bytes:
    """The user-agent side of RFC 8291 — only used to verify `_encrypt` in tests."""
    salt, idlen = body[:16], body[20]
    as_public = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    ua_public = ua_private.public_key().public_bytes(_ENC.X962, _PUBF.UncompressedPoint)
    as_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public)
    ecdh = ua_private.exchange(ec.ECDH(), as_key)
    ikm = _hkdf(auth, ecdh, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    record = AESGCM(cek).decrypt(nonce, ciphertext, None)
    return record[:-1].rstrip(b"\x00") if record.endswith(b"\x00") else record[:-1]


# ── sending ──────────────────────────────────────────────────────────────────


class PushGone(Exception):
    """The subscription is no longer valid (404/410) — the caller should delete it."""


async def send(
    subscription: dict, payload: bytes, *, private_pem: bytes, public_b64: str,
    subject: str, ttl: int = 2419200,
) -> None:
    """POST an encrypted push to one subscription. Raises PushGone on 404/410, or httpx errors
    for other failures. `subscription` = {endpoint, p256dh, auth}."""
    endpoint = subscription["endpoint"]
    body = encrypt(payload, subscription["p256dh"], subscription["auth"])
    headers = {
        "Authorization": vapid_authorization(endpoint, private_pem, public_b64, subject),
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": str(ttl),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(endpoint, content=body, headers=headers)
    if resp.status_code in (404, 410):
        raise PushGone(endpoint)
    if resp.status_code >= 400:
        detail = (resp.text or "").strip().replace("\n", " ")[:300]
        raise httpx.HTTPStatusError(
            f"push service returned {resp.status_code}{': ' + detail if detail else ''}",
            request=resp.request, response=resp,
        )
