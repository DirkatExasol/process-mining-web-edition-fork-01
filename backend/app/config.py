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

# Structured application/admin log (shared by all three processes). The live log
# is the SQLite store; rotated segments are written to LOGS_DIR as .log files.
LOGS_DB_PATH = DATA_DIR / "logs.sqlite3"
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

CERTS_DIR = DATA_DIR / "certs"
CERTS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_CERT_PATH = CERTS_DIR / "active.crt"
ACTIVE_KEY_PATH = CERTS_DIR / "active.key"

# Automatic (scheduled) encrypted backups are written here as .json envelopes.
BACKUPS_DIR = DATA_DIR / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

# Always-on self-signed cert for the internal GUI → compute-backend hop (loopback).
# Independent of the user-facing TLS mode; minted on backend start (internal_tls).
INTERNAL_CERT_PATH = CERTS_DIR / "internal.crt"
INTERNAL_KEY_PATH = CERTS_DIR / "internal.key"

# Each TLS-aware launcher (GUI + admin) writes its PID here so the admin service
# can signal a restart (SIGHUP → rebind listeners with the current TLS plan).
GUI_PID_PATH = DATA_DIR / "gui.pid"
ADMIN_PID_PATH = DATA_DIR / "admin.pid"
INTEGRATION_PID_PATH = DATA_DIR / "integration.pid"

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

# The integration / data-source configuration surface runs on its own port — by
# convention the admin port + 10 (HTTP 8100 / HTTPS 8463 with the defaults). It
# follows the same shared TLS plan as the app + admin, and only developers and
# admins may sign in (power users are refused).
INTEGRATION_HOST = os.environ.get("PMW_INTEGRATION_HOST", ADMIN_HOST)
INTEGRATION_PORT = int(os.environ.get("PMW_INTEGRATION_PORT", str(ADMIN_PORT + 10)))
INTEGRATION_HTTPS_PORT = int(
    os.environ.get("PMW_INTEGRATION_HTTPS_PORT", str(ADMIN_HTTPS_PORT + 10))
)

# File sources for the integration console read from this sandbox directory by default —
# nothing outside it can be opened (path traversal / symlink escapes are rejected). Set
# PMW_INTEGRATION_ALLOW_ANY_PATH=1 to instead allow any absolute path the server can read
# (developer-trusted deployments only — it enables reading arbitrary server files).
INTEGRATION_FILES_DIR = Path(
    os.environ.get("PMW_INTEGRATION_FILES_DIR", str(DATA_DIR / "integration_files"))
)
INTEGRATION_FILES_DIR.mkdir(parents=True, exist_ok=True)
INTEGRATION_ALLOW_ANY_PATH = os.environ.get(
    "PMW_INTEGRATION_ALLOW_ANY_PATH", ""
).strip().lower() in ("1", "true", "yes", "on")

# File-source watchdog: a background loop that auto-imports newly-appended lines of a
# File source when its file grows. PMW_INTEGRATION_WATCHDOG=0 disables it globally; the
# base tick is how often the loop wakes (each source also has its own poll interval).
INTEGRATION_WATCHDOG_ENABLED = os.environ.get(
    "PMW_INTEGRATION_WATCHDOG", "1"
).strip().lower() in ("1", "true", "yes", "on")
INTEGRATION_WATCHDOG_TICK_SECS = max(
    5, int(os.environ.get("PMW_INTEGRATION_WATCHDOG_TICK", "10"))
)

# Admin session lifetime.
ADMIN_SESSION_TTL_SECS = int(os.environ.get("PMW_ADMIN_SESSION_TTL", str(8 * 3600)))

# Main-app sign-in session lifetime.
SESSION_TTL_SECS = int(os.environ.get("PMW_SESSION_TTL", str(12 * 3600)))

# Hard cap on how long ONE sign-in can live, regardless of activity. The session cookie
# is re-minted on every authenticated request (that is what makes the idle timeout a
# sliding window), so without this a captured cookie could be kept valid forever by
# issuing one request per window. Measured from the original sign-in, carried through
# every refresh; reaching it forces a fresh sign-in.
SESSION_MAX_LIFETIME_SECS = int(
    os.environ.get("PMW_SESSION_MAX_LIFETIME", str(7 * 24 * 3600))
)

# Default bootstrap administrator (created on first run if no users exist).
DEFAULT_ADMIN_USERNAME = os.environ.get("PMW_DEFAULT_ADMIN_USER", "Administrator")

# Passkey (WebAuthn) login. The Relying Party ID is the registrable domain (host,
# NO port), so the app and admin on the same host share one passkey. Leave unset to
# derive it from the request Host header (correct for localhost and single-host
# deployments); set it to the parent domain for split app/admin subdomains.
PASSKEY_RP_ID = os.environ.get("PMW_PASSKEY_RP_ID", "").strip()
PASSKEY_RP_NAME = os.environ.get("PMW_PASSKEY_RP_NAME", "Process Mining Demonstrator")
# Optional comma-separated allowlist of expected origins (scheme://host[:port]).
# Empty → accept the request's own origin (works for localhost / single host).
PASSKEY_ORIGINS = [
    o.strip()
    for o in os.environ.get("PMW_PASSKEY_ORIGINS", "").split(",")
    if o.strip()
]
# TOTP two-factor: the issuer label shown in the user's authenticator app.
MFA_ISSUER = os.environ.get("PMW_MFA_ISSUER", "Process Mining Demonstrator").strip() \
    or "Process Mining Demonstrator"
DEFAULT_ADMIN_PASSWORD = os.environ.get("PMW_DEFAULT_ADMIN_PASSWORD", "Administrator")

# URL the GUI server uses to reach the compute backend. HTTPS by default: the
# backend serves TLS with the internal cert, so the frontend↔backend hop is
# encrypted even on loopback.
BACKEND_URL = os.environ.get("PMW_BACKEND_URL", f"https://{BACKEND_HOST}:{BACKEND_PORT}")

# CA bundle the GUI proxy verifies the backend against. Defaults to the pinned
# internal self-signed cert; point PMW_BACKEND_CA at a real CA when the backend is
# fronted by one, or set it empty to fall back to the system trust store.
BACKEND_CA_PATH = os.environ.get("PMW_BACKEND_CA", str(INTERNAL_CERT_PATH))

# Signed license file (shared: the admin writes it on upload, the backend verifies
# it at startup and stops after a grace period if it is missing/invalid/expired).
LICENSE_PATH = DATA_DIR / "license.json"

# Marker that makes the demo grace a ONE-TIME window: the first unlicensed run
# anchors a deadline here, and it is never renewed by restarting. Delete this file
# (or set PMW_RESET_DEMO=1) to grant a fresh demo window.
DEMO_MARKER_PATH = DATA_DIR / "demo_grace.json"

# Grace period (seconds) the backend keeps running with no valid license before it
# stops itself — enough time to upload a real license via the admin panel.
LICENSE_GRACE_SECS = int(os.environ.get("PMW_LICENSE_GRACE_SECS", str(30 * 60)))

# How often the backend re-reads the license during a grace period. Short enough
# that an admin upload cancels a pending shutdown within seconds.
LICENSE_POLL_SECS = float(os.environ.get("PMW_LICENSE_POLL_SECS", "15"))

# The compute backend requires a proxy-auth secret on /api/* so only the GUI proxy
# (which validated the session) can reach it — not a local process forging
# X-PMW-User. Disable only for `run.sh --dev`, where Vite proxies straight to the
# backend with no GUI in between.
REQUIRE_PROXY_AUTH = os.environ.get("PMW_REQUIRE_PROXY_AUTH", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)

# Wall-clock limit for the heavy statistics queries (Swift used 30 s).
QUERY_TIMEOUT_SECS = float(os.environ.get("PMW_QUERY_TIMEOUT", "30"))

# Same default prompt as AppViewModel.defaultLLMPrompt.
DEFAULT_LLM_PROMPT = (
    "Analyze the transitions table and identify outliers, min, max, avg values "
    "for transitions. Use project name as a title, make a decent layout."
)
