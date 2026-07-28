"""Always-on TLS for the internal GUI → compute-backend hop.

The compute backend binds loopback and the GUI server proxies ``/api/*`` to it.
That hop is encrypted with a dedicated self-signed certificate so frontend↔backend
traffic is never plain text — independent of the admin-managed *user-facing* TLS
mode (which governs the browser↔server listeners). The certificate is minted once
into ``data/certs/internal.{crt,key}`` and reused across restarts; it is renewed
automatically once it is missing, unparseable, or close to expiry.

The GUI proxy pins its trust to this certificate (``PMW_BACKEND_CA`` →
``BACKEND_CA_PATH``), so the connection is both encrypted and authenticated.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from .. import config
from . import certs
from ..store.crypto import write_private_file

# Loopback identities the backend is reached by; BACKEND_HOST is prepended.
_BASE_SANS = ["127.0.0.1", "localhost", "::1"]
# Renew when this little validity remains, so a long-lived deployment never trips
# over an expired internal cert.
_RENEW_WITHIN = datetime.timedelta(days=30)


def _is_current(cert_path: Path, key_path: Path) -> bool:
    if not (cert_path.exists() and key_path.exists()):
        return False
    try:
        info = certs.inspect(cert_path.read_text(encoding="utf-8"))
        not_after = datetime.datetime.fromisoformat(info.not_after)
    except Exception:  # noqa: BLE001 — any problem → regenerate
        return False
    now = datetime.datetime.now(not_after.tzinfo)
    return now + _RENEW_WITHIN < not_after


def ensure_internal_cert() -> tuple[Path, Path]:
    """Return (cert_path, key_path), minting/renewing the internal cert if needed."""
    cert_path, key_path = config.INTERNAL_CERT_PATH, config.INTERNAL_KEY_PATH
    if _is_current(cert_path, key_path):
        return cert_path, key_path

    host = (config.BACKEND_HOST or "127.0.0.1").strip()
    sans = list(dict.fromkeys([host, *_BASE_SANS]))
    cert_pem, key_pem = certs.generate_self_signed(common_name=host, sans=sans)

    config.CERTS_DIR.mkdir(parents=True, exist_ok=True)
    cert_path.write_text(cert_pem, encoding="utf-8")
    # The private key is written 0600-from-birth (no world-readable window between
    # a plain write and a later chmod).
    write_private_file(key_path, key_pem)
    return cert_path, key_path
