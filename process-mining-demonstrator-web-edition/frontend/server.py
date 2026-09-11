"""GUI Server.

Serves the built React SPA and proxies every `/api/*` call to the compute
backend, so the browser only ever talks to this one origin.

The whole surface — the SPA, the sign-in flow (password, TOTP two-factor, WebAuthn
passkey, mandatory enrolment) and the `/api` proxy — is built by the shared
`app.web_surface.build_surface_app` factory. This surface admits **any enabled
user**; the integration console (`integration/server.py`) reuses the same factory
with a role gate. See that module for the full behaviour.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.web_surface import build_surface_app  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)

WEB_DIR = Path(__file__).resolve().parent / "web"
DIST_DIR = WEB_DIR / "dist"
INDEX_HTML = DIST_DIR / "index.html"

# Session cookie name for this surface (audience "app").
SESSION_COOKIE = "pmw_session"

# The main application: session audience "app", cookie "pmw_session", every enabled
# user may sign in.
app = build_surface_app(
    title="Process Mining Demonstrator — GUI Server",
    audience="app",
    cookie_name=SESSION_COOKIE,
    dist_dir=DIST_DIR,
    index_html=INDEX_HTML,
    role_predicate=lambda user: True,  # any enabled user (enablement checked upstream)
    # The self-contained training guides (docs/*.html), served at /guides/… so the
    # launcher links them over HTTP/HTTPS instead of the file system.
    guides_dir=Path(__file__).resolve().parents[1] / "docs",
)
