"""Compute Backend — FastAPI app.

Owns the Exasol connection, all analytics and the settings store. The browser
never talks to this service directly; the GUI server proxies to it.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import hmac

from fastapi.responses import JSONResponse

from . import log_events as logx
from .api import connections, features, projects
from .config import REQUIRE_PROXY_AUTH
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
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


@app.get("/api/health")
def health() -> dict[str, object]:
    # Liveness only — connection state is per-user (see /api/connection/status).
    return {"status": "ok"}


