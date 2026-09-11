"""Actions authoring surface.

A fifth browser-facing surface (on the admin port + 20), reachable only by
developers and admins. It reuses the shared surface factory
(`app.web_surface.build_surface_app`) — same SPA-serving, sign-in flow (password,
TOTP two-factor, WebAuthn passkey, mandatory enrolment) and `/api` proxy as the main
app — differing only in its session audience/cookie and a role gate. The admin can
turn the whole feature off from the admin panel (it then serves a "disabled" page,
and the app hides the node-menu "Actions" submenu).

The action-authoring UI itself (the DSL builder) is a separate SPA entry that talks
to the `/api/projects/{id}/actions*` endpoints on the compute backend.
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

# The Actions SPA is another entry point built alongside the main app, so it shares
# the same dist/ (and chunked assets) but has its own HTML shell.
WEB_DIR = Path(__file__).resolve().parents[1] / "frontend" / "web"
DIST_DIR = WEB_DIR / "dist"
INDEX_HTML = DIST_DIR / "actions.html"

# Session cookie name for this surface (audience "actions"). Distinct from the app,
# admin and integration cookies so they never collide on one host.
SESSION_COOKIE = "pmw_actions"


def _may_enter(user: User) -> bool:
    """Only developers and admins may author actions (not power/standard users)."""
    return user.is_developer or user.is_admin


app = build_surface_app(
    title="Process Mining - Action Builder",
    audience="actions",
    cookie_name=SESSION_COOKIE,
    dist_dir=DIST_DIR,
    index_html=INDEX_HTML,
    role_predicate=_may_enter,
    denied_message=(
        "You need the Developer role to author actions. "
        "Ask an administrator to grant it."
    ),
    disabled_check=lambda: not store.actions_enabled,
    disabled_message="The Actions feature has been turned off by the administrator.",
)
