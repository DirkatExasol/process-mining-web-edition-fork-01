"""TLS-aware launcher for the integration / data-source console.

Serves the integration surface over HTTP and/or HTTPS using the *same* TLS mode and
the *same* active certificate as the main application and admin interface (via the
shared `app.tls_launcher`), and rebinds on SIGHUP. See that module for the full
behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # local `server` module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import (  # noqa: E402
    INTEGRATION_HOST,
    INTEGRATION_HTTPS_PORT,
    INTEGRATION_PID_PATH,
    INTEGRATION_PORT,
)
from app.tls_launcher import run  # noqa: E402
from server import app  # noqa: E402  — the integration application

if __name__ == "__main__":
    run(
        app,
        host=INTEGRATION_HOST,
        http_port=INTEGRATION_PORT,
        https_port=INTEGRATION_HTTPS_PORT,
        pid_path=INTEGRATION_PID_PATH,
        name="integration",
    )
