"""Shared symmetric-crypto helpers for the local data stores.

A single Fernet key (``data/secret.key``, mode 0600) protects secrets at rest —
database passwords, LLM API keys and TLS private keys — and signs admin session
tokens. Passwords use scrypt with a random salt (never reversible).
"""

from __future__ import annotations

import hashlib
import hmac
import os

from cryptography.fernet import Fernet

from ..config import SECRET_KEY_PATH

_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    """Load (or create on first use) the process-wide Fernet instance."""
    global _fernet
    if _fernet is None:
        if not SECRET_KEY_PATH.exists():
            SECRET_KEY_PATH.write_bytes(Fernet.generate_key())
            SECRET_KEY_PATH.chmod(0o600)
        _fernet = Fernet(SECRET_KEY_PATH.read_bytes())
    return _fernet


# ── Password hashing (scrypt) ─────────────────────────────────────────────────

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def hash_password(password: str) -> str:
    """Return a self-describing scrypt hash: ``scrypt$n$r$p$salt$hash`` (hex)."""
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification against a stored scrypt hash."""
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
        )
        return hmac.compare_digest(digest, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


# ── Secret value encryption ───────────────────────────────────────────────────


def encrypt_text(plaintext: str) -> str:
    """Encrypt a UTF-8 string, returning a base64 token safe for SQLite TEXT."""
    return get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_text(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt_text`. Empty on failure."""
    from cryptography.fernet import InvalidToken

    try:
        return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def sign_session(payload: bytes) -> str:
    """Encrypt a session payload; the Fernet TTL check happens on read."""
    return get_fernet().encrypt(payload).decode("ascii")


def read_session(token: str, ttl_secs: int) -> bytes | None:
    """Decrypt a session token, honouring its age. None if invalid or expired."""
    from cryptography.fernet import InvalidToken

    try:
        return get_fernet().decrypt(token.encode("ascii"), ttl=ttl_secs)
    except (InvalidToken, ValueError):
        return None
