"""TLS-aware launcher for the administrative interface.

Serves the admin app over HTTP and/or HTTPS using the *same* TLS mode and the
*same* active certificate as the main application (via the shared
`app.tls_launcher`), and rebinds on SIGHUP. See that module for the full
behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # local `server`/`pages`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import (  # noqa: E402
    ADMIN_HOST,
    ADMIN_HTTPS_PORT,
    ADMIN_PID_PATH,
    ADMIN_PORT,
)
from app.tls_launcher import run  # noqa: E402
from server import app  # noqa: E402  — the admin application

if __name__ == "__main__":
    run(
        app,
        host=ADMIN_HOST,
        http_port=ADMIN_PORT,
        https_port=ADMIN_HTTPS_PORT,
        pid_path=ADMIN_PID_PATH,
        name="admin",
    )
