"""Compute Backend — FastAPI app.

Owns the Exasol connection, all analytics and the settings store. The browser
never talks to this service directly; the GUI server proxies to it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import hmac

from fastapi.responses import JSONResponse

from . import licensing
from . import log_events as logx
from .api import connections, features, integration, projects
from .config import LICENSE_GRACE_SECS, LICENSE_POLL_SECS, REQUIRE_PROXY_AUTH
from .db.manager import db, registry, reset_current_user, set_current_user
from .store.crypto import proxy_auth_secret

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)

# Only the GUI proxy knows this (both derive it from the shared Fernet key).
if REQUIRE_PROXY_AUTH:
    _PROXY_SECRET = proxy_auth_secret()
else:
    _PROXY_SECRET = ""
    logging.getLogger("compute-backend").warning(
        "SECURITY: PMW_REQUIRE_PROXY_AUTH is DISABLED — the compute backend trusts the "
        "X-PMW-User header unconditionally, so any process that can reach its port can "
        "impersonate any user. This is for local development only; never run a deployed "
        "or shared instance with it off."
    )
# Liveness probe stays open (the Docker healthcheck hits it directly).
_PROXY_AUTH_EXEMPT = {"/api/health"}


# How often the watchdog re-reads the license file during a grace period. Short
# enough that an admin upload cancels a pending shutdown within a few seconds.
_LICENSE_POLL_SECS = LICENSE_POLL_SECS


def _stop_backend() -> None:
    # SIGTERM triggers uvicorn's graceful shutdown (which runs lifespan cleanup).
    os.kill(os.getpid(), signal.SIGTERM)


async def _license_watchdog() -> None:
    """Enforce the license. With no valid license the backend runs only for the
    remainder of the ONE-TIME demo window (persisted in the demo marker) and then
    stops. An admin who uploads a valid license mid-demo cancels the shutdown; a
    restart after the demo is spent gets no fresh window.
    """
    if licensing.evaluate().ok:
        logx.info(f"License OK — {licensing.evaluate().message}", operation="license")
    in_demo = False

    while True:
        status = licensing.evaluate()
        if status.ok:
            if in_demo:
                logx.info(
                    f"Valid license applied — {status.message} Shutdown cancelled.",
                    operation="license",
                )
                in_demo = False
            await asyncio.sleep(_LICENSE_POLL_SECS)
            continue

        # No valid license: consume/resume the one-time demo window.
        remaining = licensing.demo_remaining_secs(create=True)
        if remaining <= 0:
            logx.error(
                f"No valid license and the one-time demo period is over — stopping "
                f"the backend. ({status.message})",
                operation="license",
            )
            _stop_backend()
            return
        if not in_demo:
            in_demo = True
            logx.warn(
                f"No valid license — {status.message} Demo mode: the backend will "
                f"stop in ~{(remaining + 59) // 60} min unless a valid license is applied.",
                operation="license",
            )
        await asyncio.sleep(_LICENSE_POLL_SECS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Recovery valve: clear the one-time demo marker so a fresh window is granted.
    if os.environ.get("PMW_RESET_DEMO", "").strip().lower() in ("1", "true", "yes", "on"):
        if licensing.reset_demo():
            logging.getLogger("compute-backend").warning(
                "PMW_RESET_DEMO set — cleared the one-time demo marker."
            )
    # Seed the bundled example log(s) into the integration files sandbox (first run).
    from .integration.files import seed_demo_files

    seed_demo_files()
    watchdog = asyncio.create_task(_license_watchdog())
    # File-source watchdog: auto-import newly-appended lines of watched File sources.
    from .integration.watchdog import watchdog_loop

    file_watchdog = asyncio.create_task(watchdog_loop())
    yield
    watchdog.cancel()
    file_watchdog.cancel()
    # Release every per-user Exasol connection (and the legacy one) on shutdown.
    await registry.disconnect_all()
    await db.disconnect()


class UserContextMiddleware:
    """Bind the request's user (from the GUI-injected, trusted X-PMW-User header)
    to a ContextVar so each request resolves to that user's own DatabaseManager.

    A pure-ASGI middleware (not BaseHTTPMiddleware) so the ContextVar set here
    propagates into the endpoint's context — and into its asyncio.to_thread work.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        username: str | None = None
        proxy_auth = ""
        for key, value in scope.get("headers", []):
            if key == b"x-pmw-user":
                username = value.decode("latin-1").strip() or None
            elif key == b"x-pmw-proxy-auth":
                proxy_auth = value.decode("latin-1")

        # Reject anything that did not come through the GUI proxy (which alone
        # validated the session) — a local process can't forge X-PMW-User without
        # the shared secret. Health stays open for the container liveness probe.
        if (
            _PROXY_SECRET
            and scope.get("path", "") not in _PROXY_AUTH_EXEMPT
            and not hmac.compare_digest(proxy_auth, _PROXY_SECRET)
        ):
            return await JSONResponse(
                {"detail": "Direct access to the compute backend is not allowed."},
                status_code=403,
            )(scope, receive, send)

        token = set_current_user(username)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user(token)


app = FastAPI(
    title="Process Mining Demonstrator — Compute Backend",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(UserContextMiddleware)

# The GUI server proxies same-origin, but allowing localhost keeps the Vite dev
# server usable against this backend directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Log unhandled failures (5xx / crashes such as an oversized simulation) and 4xx
# gate hits. The user comes from the trusted X-PMW-User header the GUI injects.
logx.install_request_logging(app, lambda r: r.headers.get("x-pmw-user", ""))

app.include_router(connections.router)
app.include_router(projects.router)
app.include_router(features.router)
app.include_router(integration.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    # Liveness only — connection state is per-user (see /api/connection/status).
    return {"status": "ok"}


@app.get("/api/license/status")
def license_status() -> dict[str, object]:
    """Demo/license state (global, no per-user context). `remainingSeconds` is the
    one-time demo grace left before an unlicensed backend stops (0 once spent).
    Read-only: does not itself start/consume the demo window.
    """
    status = licensing.evaluate()
    return {
        "state": status.state,
        "demoMode": not status.ok,
        "remainingSeconds": None if status.ok else licensing.demo_remaining_secs(create=False),
        "licensee": status.licensee,
        "expires": status.expires,
    }


