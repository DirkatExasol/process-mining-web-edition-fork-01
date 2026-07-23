"""TLS-aware launcher for the GUI server.

Thin entry point around the shared launcher (`app.tls_launcher`): serves the
static + proxy application over HTTP and/or HTTPS per the admin-managed TLS plan,
and rebinds on SIGHUP. See that module for the full behaviour.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # local `server` module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import (  # noqa: E402
    FRONTEND_HOST,
    FRONTEND_HTTPS_PORT,
    FRONTEND_PORT,
    GUI_PID_PATH,
)
from app.tls_launcher import run  # noqa: E402
from server import app  # noqa: E402  — the static + proxy application

if __name__ == "__main__":
    run(
        app,
        host=FRONTEND_HOST,
        http_port=FRONTEND_PORT,
        https_port=FRONTEND_HTTPS_PORT,
        pid_path=GUI_PID_PATH,
        name="gui",
    )
