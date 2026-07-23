"""Runtime configuration for the compute backend."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("PMW_DATA_DIR", PROJECT_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "settings.sqlite3"
SECRET_KEY_PATH = DATA_DIR / "secret.key"

# Multi-user security: the admin service owns a separate database and a directory
# of certificates. The active certificate is materialised to disk so uvicorn's
# TLS listener can read it as files.
SECURITY_DB_PATH = DATA_DIR / "security.sqlite3"
CERTS_DIR = DATA_DIR / "certs"
CERTS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_CERT_PATH = CERTS_DIR / "active.crt"
ACTIVE_KEY_PATH = CERTS_DIR / "active.key"

# Each TLS-aware launcher (GUI + admin) writes its PID here so the admin service
# can signal a restart (SIGHUP → rebind listeners with the current TLS plan).
GUI_PID_PATH = DATA_DIR / "gui.pid"
ADMIN_PID_PATH = DATA_DIR / "admin.pid"

BACKEND_HOST = os.environ.get("PMW_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("PMW_BACKEND_PORT", "8000"))

FRONTEND_HOST = os.environ.get("PMW_FRONTEND_HOST", "127.0.0.1")
FRONTEND_PORT = int(os.environ.get("PMW_FRONTEND_PORT", "8080"))
# HTTPS listener port for the GUI server (used when TLS is optional or required).
FRONTEND_HTTPS_PORT = int(os.environ.get("PMW_FRONTEND_HTTPS_PORT", "8443"))

# The administrative interface runs on its own port.
ADMIN_HOST = os.environ.get("PMW_ADMIN_HOST", "127.0.0.1")
ADMIN_PORT = int(os.environ.get("PMW_ADMIN_PORT", "8090"))
# HTTPS listener port for the admin interface — it follows the same TLS mode and
# active certificate as the main app (used when TLS is optional or required).
ADMIN_HTTPS_PORT = int(os.environ.get("PMW_ADMIN_HTTPS_PORT", "8453"))

# Admin session lifetime.
ADMIN_SESSION_TTL_SECS = int(os.environ.get("PMW_ADMIN_SESSION_TTL", str(8 * 3600)))

# Main-app sign-in session lifetime.
SESSION_TTL_SECS = int(os.environ.get("PMW_SESSION_TTL", str(12 * 3600)))

# Default bootstrap administrator (created on first run if no users exist).
DEFAULT_ADMIN_USERNAME = os.environ.get("PMW_DEFAULT_ADMIN_USER", "Administrator")
DEFAULT_ADMIN_PASSWORD = os.environ.get("PMW_DEFAULT_ADMIN_PASSWORD", "Administrator")

# URL the GUI server uses to reach the compute backend.
BACKEND_URL = os.environ.get("PMW_BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

# Wall-clock limit for the heavy statistics queries (Swift used 30 s).
QUERY_TIMEOUT_SECS = float(os.environ.get("PMW_QUERY_TIMEOUT", "30"))

# Same default prompt as AppViewModel.defaultLLMPrompt.
DEFAULT_LLM_PROMPT = (
    "Analyze the transitions table and identify outliers, min, max, avg values "
    "for transitions. Use project name as a title, make a decent layout."
)
