"""Integration / data-source configuration console.

A fourth browser-facing surface (on the admin port + 10), reachable only by
developers and admins. It reuses the shared surface factory
(`app.web_surface.build_surface_app`) — same SPA-serving, sign-in flow (password,
TOTP two-factor, WebAuthn passkey, mandatory enrolment) and `/api` proxy as the main
app — differing only in its session audience/cookie and a role gate. The admin can
disable the whole console from the admin panel (it then serves a "disabled" page).

The data-source configuration features themselves are built on top of this scaffold
in later stages.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.store.security import User, store  # noqa: E402
from app.web_surface import build_surface_app  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)

# The integration SPA is a second entry point built alongside the main app, so it
# shares the same dist/ (and chunked assets) but has its own HTML shell.
WEB_DIR = Path(__file__).resolve().parents[1] / "frontend" / "web"
DIST_DIR = WEB_DIR / "dist"
INDEX_HTML = DIST_DIR / "integration.html"

# Session cookie name for this surface (audience "integration"). Distinct from the
# app ("pmw_session") and admin ("pmw_admin") cookies so they never collide on one
# host, and each surface only accepts its own audience.
SESSION_COOKIE = "pmw_integration"


def _may_enter(user: User) -> bool:
    """Only developers and admins may use the integration console (not power users)."""
    return user.is_developer or user.is_admin


app = build_surface_app(
    title="Process Mining Demonstrator — Integration",
    audience="integration",
    cookie_name=SESSION_COOKIE,
    dist_dir=DIST_DIR,
    index_html=INDEX_HTML,
    role_predicate=_may_enter,
    denied_message=(
        "You need the Developer role to use the integration console. "
        "Ask an administrator to grant it."
    ),
    disabled_check=lambda: not store.integration_enabled,
    disabled_message="The integration console has been turned off by the administrator.",
)
