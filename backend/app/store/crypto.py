"""Shared symmetric-crypto helpers for the local data stores.

A single Fernet key (``data/secret.key``, mode 0600) protects secrets at rest —
database passwords, LLM API keys and TLS private keys — and signs admin session
tokens. Passwords use scrypt with a random salt (never reversible).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from cryptography.fernet import Fernet

from ..config import SECRET_KEY_PATH

log = logging.getLogger("crypto")

_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    """Load (or create on first use) the process-wide Fernet instance."""
    global _fernet
    if _fernet is None:
        # A symlinked key isn't blocked (Docker/k8s mount their secrets that way),
        # but surface it once: the target holds the master key, so if it was
        # pre-planted by someone else every stored secret is readable by them.
        if SECRET_KEY_PATH.is_symlink():
            log.warning(
                "secret.key is a symlink (%s); its target holds the master "
                "encryption key — verify it points where you intend.",
                SECRET_KEY_PATH,
            )
        if not SECRET_KEY_PATH.exists():
            _create_key_atomically()
        _fernet = Fernet(_read_key())
    return _fernet


def _create_key_atomically() -> None:
    """Create ``secret.key`` exactly once, 0600 from birth.

    The compute backend, GUI proxy and admin server all reach this on a fresh
    install at the same time (``run.sh`` boots them together). A plain
    ``write_bytes`` + ``chmod`` race would let two processes generate *different*
    keys (mutually unreadable secrets / proxy-auth mismatch until restart) and
    briefly leave the file world-readable. ``O_CREAT | O_EXCL`` with mode 0600 makes
    creation atomic: the winner writes the key; every loser gets ``FileExistsError``
    and reads the winner's key (see ``_read_key`` for the empty-file window)."""
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(SECRET_KEY_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return  # another process created it first — read it below
    try:
        os.write(fd, Fernet.generate_key())
        os.fsync(fd)  # ensure the bytes are visible to a losing reader
    finally:
        os.close(fd)


def _read_key() -> bytes:
    """Read the key, tolerating the brief window between a winner's ``O_EXCL``
    create and its ``os.write``. A loser can observe the file as it exists but is
    still empty; wait briefly for the bytes. If the file stays empty (a creator was
    killed mid-write, leaving a 0-byte key that would wedge every service), recreate
    it rather than raising on ``Fernet(b'')``."""
    for _ in range(100):  # ~1s of 10 ms polls
        data = SECRET_KEY_PATH.read_bytes()
        if data:
            return data
        time.sleep(0.01)
    try:
        SECRET_KEY_PATH.unlink()  # discard the wedged 0-byte key and re-create
    except FileNotFoundError:
        pass
    _create_key_atomically()
    return SECRET_KEY_PATH.read_bytes()


def write_private_file(path, text: str) -> None:
    """Write ``text`` to ``path`` as an owner-only (0600) file with no world/group
    window — used for TLS private keys. A plain ``write_text`` + ``chmod`` leaves the
    key readable at the default umask between the two calls; creating with mode 0600
    closes that window. ``O_NOFOLLOW`` refuses to write *through* a pre-planted
    symlink at the path (which we own as an output file, so nothing legitimately
    symlinks it) — that would otherwise redirect the private key onto, or truncate,
    an attacker-chosen file. The trailing ``chmod`` re-asserts 0600 on a pre-existing
    regular file with looser permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


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


def proxy_auth_secret() -> str:
    """Shared secret the GUI proxy and the compute backend both derive from the
    Fernet key (which both processes load from ``data/secret.key``). The backend
    requires it on every ``/api/*`` call, proving the request came through the
    trusted proxy rather than a local process forging the X-PMW-User header.
    Deterministic from the shared key — no separate file, no generation race.
    """
    get_fernet()  # ensure the key exists on disk
    key = SECRET_KEY_PATH.read_bytes()
    return hashlib.sha256(key + b"pmw-proxy-auth-v1").hexdigest()
