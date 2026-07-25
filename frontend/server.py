"""GUI Server.

Serves the built React SPA and proxies every `/api/*` call to the compute
backend, so the browser only ever talks to this one origin.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import log_events as logx  # noqa: E402
from app.config import BACKEND_CA_PATH, BACKEND_URL, SESSION_TTL_SECS  # noqa: E402
from app.store.crypto import read_session, sign_session  # noqa: E402
from app.store.security import User, store  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
log = logging.getLogger("gui-server")

WEB_DIR = Path(__file__).resolve().parent / "web"
DIST_DIR = WEB_DIR / "dist"
INDEX_HTML = DIST_DIR / "index.html"

# Long enough for LLM documentation runs and heavy statistics queries.
PROXY_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


def _backend_verify() -> object:
    """TLS verification for the backend connection.

    For an HTTPS backend, pin trust to the internal self-signed cert when present
    (encrypted *and* authenticated); fall back to the system trust store otherwise.
    Ignored for a plain-HTTP backend (e.g. PMW_BACKEND_URL overridden to http://).
    """
    ca = (BACKEND_CA_PATH or "").strip()
    if ca and Path(ca).exists():
        return ca
    return True

app = FastAPI(title="Process Mining Demonstrator — GUI Server", version="1.0.0")
logx.install_request_logging(app, lambda r: _current_user(r))

# The proxy client is created lazily and recreated if it was closed. This matters
# because the TLS-aware launcher (frontend/launch.py) restarts uvicorn's listeners
# in-process on SIGHUP, which fires the app's shutdown/startup lifespan events —
# the client must survive (or transparently reopen) across such a restart.
_client: httpx.AsyncClient | None = None
_client_pinned: bool = False


def _get_client() -> httpx.AsyncClient:
    global _client, _client_pinned
    verify = _backend_verify()
    pinned = verify is not True  # a CA-path string means we pin the backend cert
    # Rebuild if never built, if the launcher closed it on a SIGHUP restart, or if
    # the pinned CA has since appeared (the backend may still have been minting the
    # internal cert when this process first built its client → system-trust only).
    if _client is None or _client.is_closed or (pinned and not _client_pinned):
        _client = httpx.AsyncClient(
            base_url=BACKEND_URL, timeout=PROXY_TIMEOUT, verify=verify
        )
        _client_pinned = pinned
    return _client


@app.on_event("startup")
async def _startup() -> None:
    _get_client()

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}

# ── Authentication ────────────────────────────────────────────────────────────
#
# Sign-in is enforced here, at the single origin the browser talks to. When the
# admin requires login, every /api/* proxy call needs a valid session cookie; the
# SPA is always served so the login screen can render.

SESSION_COOKIE = "pmw_session"

# /api paths that are reachable without a session (health probes, and the auth
# endpoints themselves live outside /api).
_OPEN_API_PATHS = {"health"}


def _issue_session(username: str) -> str:
    return sign_session(json.dumps({"u": username}).encode("utf-8"))


def _session_ttl() -> int:
    """Session lifetime in seconds. When an idle timeout is configured the session
    is a *sliding* window of that length (refreshed on each authenticated request);
    otherwise it's the fixed absolute lifetime."""
    idle = store.idle_timeout_mins
    return idle * 60 if idle > 0 else SESSION_TTL_SECS


def _set_session_cookie(response: Response, request: Request, username: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _issue_session(username),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=_session_ttl(),
        path="/",
    )


def _current_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    raw = read_session(token, _session_ttl())
    if raw is None:
        return None
    try:
        username = json.loads(raw)["u"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    user = store.get_user(username)
    return user if user and user.is_enabled else None


@app.post("/auth/login")
async def auth_login(request: Request) -> Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    # App sign-in also accepts directory (LDAP) accounts when configured; the admin
    # panel deliberately stays on local-only `authenticate`.
    user = store.authenticate_app(username, password)
    if user is None:
        logx.warn(
            f"failed sign-in for username {username!r}",
            request=request,
            username=username,
            operation="login",
        )
        return JSONResponse(
            {"detail": "Invalid username or password, or the account is disabled."},
            status_code=401,
        )
    logx.usage(
        f"user {user.username} signed in ({user.auth_source})",
        request=request,
        username=user.username,
        operation="login",
    )
    response = JSONResponse(
        {
            "username": user.username,
            "isAdmin": user.is_admin,
            "isPower": user.is_power,
            "displayName": user.display_name,
            "authSource": user.auth_source,
        }
    )
    _set_session_cookie(response, request, user.username)
    return response


# Brief cache so the login panel (and any re-render) doesn't re-probe the directory
# server on every request; the probe itself runs off the event loop.
_DIR_STATUS_TTL = 20.0
_dir_status: dict = {"at": 0.0, "value": None}


@app.get("/auth/directory-status")
async def auth_directory_status() -> Response:
    """Whether a user-directory (LDAP) server is configured and currently reachable.

    Pre-auth, for the login panel's availability LED. When no directory is configured
    it reports ``configured: false`` so the client shows nothing. Reachability is the
    service-bind test used by the admin "Test connection" button, cached briefly and
    run in a worker thread so a slow/unreachable server never blocks the page.
    """
    if not store.ldap_enabled:
        return JSONResponse({"configured": False, "available": False})

    now = time.monotonic()
    cached = _dir_status["value"]
    if cached is not None and now - _dir_status["at"] < _DIR_STATUS_TTL:
        return JSONResponse(cached)

    from app.services.ldap_auth import test_settings

    settings = store.ldap_settings()
    try:
        result = await asyncio.to_thread(test_settings, settings)
        available = bool(result.get("ok"))
    except Exception:  # a probe must never break the login page
        available = False
    value = {"configured": True, "available": available}
    _dir_status.update(at=now, value=value)
    return JSONResponse(value)


@app.post("/auth/logout")
async def auth_logout(request: Request) -> Response:
    user = _current_user(request)
    logx.usage(
        f"user {user.username if user else 'unknown'} signed out",
        request=request,
        username=user.username if user else "",
        operation="logout",
    )
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/auth/session")
async def auth_session(request: Request) -> Response:
    user = _current_user(request)
    response = JSONResponse(
        {
            "authenticated": user is not None,
            "username": user.username if user else None,
            "isAdmin": user.is_admin if user else False,
            "isPower": user.is_power if user else False,
            "displayName": user.display_name if user else None,
            "authSource": user.auth_source if user else None,
            "requireLogin": store.require_login,
            "idleTimeoutMins": store.idle_timeout_mins,
        }
    )
    # Polling this (the client does so on activity) slides the idle window.
    if user is not None:
        _set_session_cookie(response, request, user.username)
    return response


@app.api_route(
    "/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
)
async def proxy(path: str, request: Request) -> Response:
    user = _current_user(request)

    # Gate every API call behind a valid session when sign-in is required.
    if store.require_login and path not in _OPEN_API_PATHS and user is None:
        return JSONResponse({"detail": "Authentication required."}, status_code=401)

    body = await request.body()
    # Strip any client-supplied identity header, then inject the validated user so
    # the backend can filter per-user data. The browser can never forge this.
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP | {"host", "x-pmw-user"}
    }
    if user is not None:
        headers["X-PMW-User"] = user.username
    try:
        upstream = await _get_client().request(
            request.method,
            f"/api/{path}",
            content=body,
            headers=headers,
            params=request.query_params,
        )
    except httpx.ConnectError:
        return Response(
            content=(
                '{"detail":"The compute backend is not reachable. '
                'Start it with ./run.sh or check PMW_BACKEND_URL."}'
            ),
            status_code=502,
            media_type="application/json",
        )
    except httpx.ReadTimeout:
        return Response(
            content='{"detail":"The compute backend timed out."}',
            status_code=504,
            media_type="application/json",
        )

    passthrough = {
        k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP
    }
    response = Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=passthrough,
        media_type=upstream.headers.get("content-type"),
    )
    # Any authenticated API activity slides the idle-timeout window.
    if user is not None:
        _set_session_cookie(response, request, user.username)
    return response


@app.on_event("shutdown")
async def shutdown() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str) -> Response:
    """Serve static files when they exist, otherwise fall back to index.html so
    client-side routing keeps working on reload."""
    candidate = (DIST_DIR / full_path).resolve()
    if full_path and DIST_DIR in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    if INDEX_HTML.is_file():
        return FileResponse(INDEX_HTML)
    return Response(
        content=(
            "<h1>Frontend not built</h1>"
            "<p>Run <code>npm install &amp;&amp; npm run build</code> in "
            "<code>frontend/web</code>, or start the Vite dev server with "
            "<code>npm run dev</code>.</p>"
        ),
        status_code=503,
        media_type="text/html",
    )
