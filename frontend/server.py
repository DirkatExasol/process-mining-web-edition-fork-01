"""GUI Server.

Serves the built React SPA and proxies every `/api/*` call to the compute
backend, so the browser only ever talks to this one origin.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import BACKEND_URL, SESSION_TTL_SECS  # noqa: E402
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

app = FastAPI(title="Process Mining Demonstrator — GUI Server", version="1.0.0")

# The proxy client is created lazily and recreated if it was closed. This matters
# because the TLS-aware launcher (frontend/launch.py) restarts uvicorn's listeners
# in-process on SIGHUP, which fires the app's shutdown/startup lifespan events —
# the client must survive (or transparently reopen) across such a restart.
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=BACKEND_URL, timeout=PROXY_TIMEOUT)
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


def _current_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    raw = read_session(token, SESSION_TTL_SECS)
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
        return JSONResponse(
            {"detail": "Invalid username or password, or the account is disabled."},
            status_code=401,
        )
    response = JSONResponse({"username": user.username, "isAdmin": user.is_admin})
    response.set_cookie(
        SESSION_COOKIE,
        _issue_session(user.username),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=SESSION_TTL_SECS,
        path="/",
    )
    return response


@app.post("/auth/logout")
async def auth_logout() -> Response:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@app.get("/auth/session")
async def auth_session(request: Request) -> dict:
    user = _current_user(request)
    return {
        "authenticated": user is not None,
        "username": user.username if user else None,
        "isAdmin": user.is_admin if user else False,
        "requireLogin": store.require_login,
    }


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
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=passthrough,
        media_type=upstream.headers.get("content-type"),
    )


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
