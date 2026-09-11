"""Compute-backend entry point — serves the API over TLS on loopback.

The GUI server proxies ``/api/*`` to this backend; that hop is always encrypted
with the internal self-signed certificate (``app.services.internal_tls``), so
frontend↔backend traffic is never plain text regardless of the user-facing TLS
mode. Started by ``run.sh``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the `app` package

import uvicorn  # noqa: E402

from app.config import BACKEND_HOST, BACKEND_PORT  # noqa: E402
from app.main import app  # noqa: E402
from app.services.internal_tls import ensure_internal_cert  # noqa: E402

if __name__ == "__main__":
    cert_path, key_path = ensure_internal_cert()
    uvicorn.run(
        app,
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        log_level="info",
    )
