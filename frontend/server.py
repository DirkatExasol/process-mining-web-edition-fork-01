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
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import licensing  # noqa: E402
from app import log_events as logx  # noqa: E402
from app.config import BACKEND_CA_PATH, BACKEND_URL, SESSION_TTL_SECS  # noqa: E402
from app.services import mfa, passkey  # noqa: E402
from app.services.login_throttle import LoginThrottle  # noqa: E402
from app.store.crypto import (  # noqa: E402
    proxy_auth_secret,
    read_session,
    sign_session,
)
from app.store.security import User, store  # noqa: E402
from app.web_security import install_security_headers  # noqa: E402

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # The TLS-aware launcher restarts uvicorn's listeners in-process on SIGHUP,
    # which re-runs this lifespan: warm the proxy client on startup, close it on
    # shutdown so the next cycle rebuilds it cleanly.
    _get_client()
    yield
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


app = FastAPI(
    title="Process Mining Demonstrator — GUI Server",
    version="1.0.0",
    lifespan=lifespan,
)
logx.install_request_logging(app, lambda r: _current_user(r))
install_security_headers(app)

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
            base_url=BACKEND_URL,
            timeout=PROXY_TIMEOUT,
            verify=verify,
            # Prove to the backend that this request came through the proxy. Sent on
            # every backend call (proxy + logout disconnect); the browser cannot
            # supply it (stripped below).
            headers={"X-PMW-Proxy-Auth": proxy_auth_secret()},
        )
        _client_pinned = pinned
    return _client



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


_SESSION_AUDIENCE = "app"  # this cookie is only valid for the main application

# Per-source-IP sign-in throttle (password + TOTP). The account lockout doesn't
# apply to the break-glass Administrator or to the code step, so without this an
# attacker who reached the app could brute-force those unthrottled.
_login_throttle = LoginThrottle()


def _issue_session(username: str) -> str:
    # Embed the user's session epoch so logout (which bumps it) invalidates this
    # token — otherwise the stateless Fernet token would stay valid until its TTL.
    # The audience ("a") binds the token to THIS interface: the admin panel signs
    # its cookie with the same Fernet key, so without it an admin session cookie
    # would be structurally valid here (and vice-versa).
    payload = {"u": username, "e": store.session_epoch(username), "a": _SESSION_AUDIENCE}
    return sign_session(json.dumps(payload).encode("utf-8"))


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
        data = json.loads(raw)
        username = data["u"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if data.get("a") != _SESSION_AUDIENCE:
        return None  # an admin session cookie is not accepted here
    user = store.get_user(username)
    if user is None or not user.is_enabled:
        return None
    # Reject tokens issued before the user's last logout (stale epoch).
    if data.get("e") != user.session_epoch:
        return None
    return user


@app.post("/auth/login")
async def auth_login(request: Request) -> Response:
    ip = _login_throttle.client_ip(request)
    if _login_throttle.retry_after(ip) > 0:
        # Per-IP cooldown — covers accounts the lockout doesn't (the built-in admin).
        return JSONResponse(
            {"detail": "Too many attempts. Try again shortly."}, status_code=429)
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
        _login_throttle.record_failure(ip)
        # Tell the user when the account is disabled/locked; otherwise stay generic.
        detail = store.login_block_message(username) or "Invalid username or password."
        logx.warn(
            f"failed sign-in for username {username!r}",
            request=request,
            username=username,
            operation="login",
        )
        return JSONResponse({"detail": detail}, status_code=401)
    # Two-factor: if the user has confirmed TOTP (and it's still allowed), the
    # password alone isn't enough — hold a signed "password ok" cookie and ask for
    # the code. A passkey sign-in is already strong auth, so it skips this step.
    # The IP throttle is cleared only after the *full* sign-in (the code step).
    if store.mfa_active(user.username):
        response = JSONResponse({"mfaRequired": True, "username": user.username})
        _set_pending_cookie(response, request, mfa.make_pending_cookie(
            username=user.username, aud="app"))
        return response
    _login_throttle.clear(ip)
    logx.usage(
        f"user {user.username} signed in ({user.auth_source})",
        request=request,
        username=user.username,
        operation="login",
    )
    return _app_login_response(user, request)


def _user_payload(user) -> dict:
    return {
        "username": user.username,
        "isAdmin": user.is_admin,
        "isPower": user.is_power,
        "displayName": user.display_name,
        "authSource": user.auth_source,
        "passkeyAllowed": user.passkey_allowed,
        "mfaAllowed": user.mfa_allowed,
        "mfaEnabled": user.mfa_enabled,
    }


def _app_login_response(user, request: Request) -> JSONResponse:
    """The successful-sign-in response: the user payload + a session cookie."""
    response = JSONResponse(_user_payload(user))
    _set_session_cookie(response, request, user.username)
    return response


# ── Passkey (WebAuthn) sign-in — an alternative to the password ───────────────


def _rp_and_origins(request: Request):
    host = request.url.hostname or "localhost"
    origin = request.headers.get("origin") or f"{request.url.scheme}://{request.url.netloc}"
    return passkey.resolve_rp(host, origin)


def _set_challenge_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        passkey.CHALLENGE_COOKIE, token,
        httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
        max_age=passkey.CHALLENGE_TTL_SECS, path="/",
    )


def _set_pending_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        mfa.PENDING_COOKIE, token,
        httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
        max_age=mfa.PENDING_TTL_SECS, path="/",
    )


def _set_mfa_setup_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        mfa.SETUP_COOKIE, token,
        httponly=True, samesite="lax",
        secure=request.url.scheme == "https",
        max_age=mfa.SETUP_TTL_SECS, path="/",
    )


@app.post("/auth/passkey/auth/begin")
async def passkey_auth_begin(request: Request) -> Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    username = str(data.get("username") or "").strip()
    # Do the SAME two lookups for any supplied username — an existing account must
    # not run one extra query a nonexistent one skips, or response timing would
    # re-open the enumeration channel the decoy response closes.
    user = store.get_user(username) if username else None
    ids = store.credential_ids_for(username) if username else []
    eligible = user is not None and user.is_enabled and user.passkey_allowed and bool(ids)
    # Enumeration-resistant: answer identically whether or not the account exists /
    # is eligible. Eligible → the account's real credential ids; otherwise → a stable
    # decoy id that looks the same but can never verify. Same 200 shape, same cookie,
    # so a scripted probe learns nothing about which usernames have passkeys.
    allow_ids = ids if eligible else passkey.decoy_allow_ids(username)
    cookie_username = user.username if eligible else username
    rp_id, _ = _rp_and_origins(request)
    options_json, challenge = passkey.authentication_options(rp_id=rp_id, allow_ids=allow_ids)
    response = Response(content=options_json, media_type="application/json")
    _set_challenge_cookie(
        response, request,
        passkey.make_challenge_cookie(
            challenge=challenge, username=cookie_username, kind="auth", aud="app"
        ),
    )
    return response


@app.post("/auth/passkey/auth/finish")
async def passkey_auth_finish(request: Request) -> Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    ch = passkey.read_challenge_cookie(
        request.cookies.get(passkey.CHALLENGE_COOKIE) or "", kind="auth", aud="app"
    )
    if ch is None:
        return JSONResponse({"detail": "Passkey challenge expired. Try again."}, status_code=400)
    credential = data.get("credential")
    cred_id = credential.get("id") if isinstance(credential, dict) else None
    row = store.get_credential(cred_id) if cred_id else None
    user = store.get_user(row["username"]) if row else None
    rp_id, origins = _rp_and_origins(request)
    ok = False
    if (row is not None and user is not None and user.is_enabled and user.passkey_allowed
            and (row["username"] or "").lower() == (ch["username"] or "").lower()):
        try:
            new_count = passkey.verify_authentication(
                credential=credential, challenge=ch["challenge"], rp_id=rp_id,
                origins=origins, public_key=row["public_key"], sign_count=row["sign_count"],
            )
            store.set_credential_sign_count(cred_id, new_count)
            ok = True
        except Exception as exc:  # noqa: BLE001
            logx.warn(
                f"passkey verification failed for {ch['username']!r}: {exc}",
                request=request, operation="login",
            )
    if not ok:
        r = JSONResponse({"detail": "Passkey sign-in failed."}, status_code=401)
        r.delete_cookie(passkey.CHALLENGE_COOKIE, path="/")
        return r
    logx.usage(
        f"user {user.username} signed in with a passkey",
        request=request, username=user.username, operation="login",
    )
    # A passkey is already strong (phishing-resistant) auth, so it satisfies MFA
    # on its own — no TOTP step here even if the user also has TOTP enrolled.
    response = _app_login_response(user, request)
    response.delete_cookie(passkey.CHALLENGE_COOKIE, path="/")
    return response


@app.post("/auth/passkey/register/begin")
async def passkey_register_begin(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    if not user.passkey_allowed:
        return JSONResponse({"detail": "Passkeys are not enabled for your account."}, status_code=403)
    rp_id, _ = _rp_and_origins(request)
    options_json, challenge = passkey.registration_options(
        rp_id=rp_id, username=user.username,
        display_name=user.display_name or user.username,
        existing_ids=store.credential_ids_for(user.username),
    )
    response = Response(content=options_json, media_type="application/json")
    _set_challenge_cookie(
        response, request,
        passkey.make_challenge_cookie(
            challenge=challenge, username=user.username, kind="reg", aud="app"
        ),
    )
    return response


@app.post("/auth/passkey/register/finish")
async def passkey_register_finish(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    if not user.passkey_allowed:
        return JSONResponse({"detail": "Passkeys are not enabled for your account."}, status_code=403)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    ch = passkey.read_challenge_cookie(
        request.cookies.get(passkey.CHALLENGE_COOKIE) or "", kind="reg", aud="app"
    )
    if ch is None or (ch["username"] or "").lower() != user.username.lower():
        return JSONResponse({"detail": "Passkey challenge expired. Try again."}, status_code=400)
    rp_id, origins = _rp_and_origins(request)
    try:
        cred = passkey.verify_registration(
            credential=data.get("credential"), challenge=ch["challenge"],
            rp_id=rp_id, origins=origins,
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"detail": f"Could not register passkey: {exc}"}, status_code=400)
    store.add_credential(
        user.username, credential_id=cred["credential_id"], public_key=cred["public_key"],
        sign_count=cred["sign_count"], transports=str(data.get("transports") or ""),
        name=str(data.get("name") or "").strip()[:60],
    )
    logx.usage(
        f"user {user.username} registered a passkey",
        request=request, username=user.username, operation="login",
    )
    r = JSONResponse({"ok": True})
    r.delete_cookie(passkey.CHALLENGE_COOKIE, path="/")
    return r


@app.get("/auth/passkey/credentials")
async def passkey_credentials(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    return JSONResponse(
        {"passkeyAllowed": user.passkey_allowed, "credentials": store.list_credentials(user.username)}
    )


@app.delete("/auth/passkey/credentials/{cred_id}")
async def passkey_delete_credential(cred_id: str, request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    store.delete_credential(cred_id, user.username)
    return JSONResponse({"ok": True})


# ── Two-factor (TOTP) — the second step of the password sign-in ──────────────


@app.post("/auth/mfa/verify")
async def mfa_verify(request: Request) -> Response:
    """Step 2 of sign-in: with the password already verified (proven by the pending
    cookie), check the 6-digit code — or a one-time recovery code — and issue the
    session. Wrong codes are throttled per-IP but do NOT count toward the account
    lockout, so a mistyped/expired code can never disable the account."""
    ip = _login_throttle.client_ip(request)
    if _login_throttle.retry_after(ip) > 0:
        return JSONResponse(
            {"detail": "Too many attempts. Try again shortly."}, status_code=429)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    username = mfa.read_pending_cookie(
        request.cookies.get(mfa.PENDING_COOKIE) or "", aud="app")
    user = store.get_user(username) if username else None
    secret = store.get_totp_secret(username) if username else None
    if user is None or not user.is_enabled or secret is None:
        r = JSONResponse({"detail": "Your sign-in session expired. Start again."}, status_code=401)
        r.delete_cookie(mfa.PENDING_COOKIE, path="/")
        return r
    code = str(data.get("code") or "")
    ok = mfa.verify_code(secret, code) or store.consume_recovery_code(user.username, code)
    if not ok:
        _login_throttle.record_failure(ip)  # per-IP only, not account lockout
        logx.warn(f"failed 2FA for {user.username!r}", request=request,
                  username=user.username, operation="login")
        return JSONResponse({"detail": "Incorrect code. Try again."}, status_code=401)
    _login_throttle.clear(ip)
    logx.usage(f"user {user.username} signed in ({user.auth_source}) with 2FA",
               request=request, username=user.username, operation="login")
    response = _app_login_response(user, request)
    response.delete_cookie(mfa.PENDING_COOKIE, path="/")
    return response


@app.get("/auth/mfa/status")
async def mfa_status(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    return JSONResponse({
        "mfaAllowed": user.mfa_allowed,
        "enabled": user.mfa_enabled,
        "recoveryRemaining": store.recovery_codes_remaining(user.username),
    })


@app.post("/auth/mfa/setup/begin")
async def mfa_setup_begin(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    if not user.mfa_allowed:
        return JSONResponse(
            {"detail": "Two-factor authentication is not enabled for your account."},
            status_code=403)
    secret = mfa.new_secret()
    uri = mfa.provisioning_uri(secret=secret, username=user.username)
    response = JSONResponse({"secret": secret, "otpauthUri": uri, "qrSvg": mfa.qr_svg(uri)})
    _set_mfa_setup_cookie(response, request, mfa.make_setup_cookie(
        username=user.username, secret=secret, aud="app"))
    return response


@app.post("/auth/mfa/setup/finish")
async def mfa_setup_finish(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    if not user.mfa_allowed:
        return JSONResponse(
            {"detail": "Two-factor authentication is not enabled for your account."},
            status_code=403)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    secret = mfa.read_setup_cookie(
        request.cookies.get(mfa.SETUP_COOKIE) or "", username=user.username, aud="app")
    if secret is None:
        return JSONResponse({"detail": "Setup expired. Start again."}, status_code=400)
    if not mfa.verify_code(secret, str(data.get("code") or "")):
        return JSONResponse({"detail": "That code didn't match. Try again."}, status_code=400)
    store.set_totp_secret(user.username, secret)
    codes = mfa.generate_recovery_codes()
    store.set_recovery_codes(user.username, codes)
    logx.usage(f"user {user.username} enabled two-factor authentication",
               request=request, username=user.username, operation="login")
    r = JSONResponse({"recoveryCodes": codes})
    r.delete_cookie(mfa.SETUP_COOKIE, path="/")
    return r


@app.post("/auth/mfa/recovery/regenerate")
async def mfa_recovery_regenerate(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    if not user.mfa_enabled:
        return JSONResponse({"detail": "Two-factor authentication isn't set up."}, status_code=400)
    codes = mfa.generate_recovery_codes()
    store.set_recovery_codes(user.username, codes)
    logx.usage(f"user {user.username} regenerated 2FA recovery codes",
               request=request, username=user.username, operation="login")
    return JSONResponse({"recoveryCodes": codes})


@app.post("/auth/mfa/disable")
async def mfa_disable(request: Request) -> Response:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"detail": "Not signed in."}, status_code=401)
    # Re-authenticate the downgrade: turning off the second factor requires the
    # current code (or a recovery code), so a hijacked session alone can't strip it.
    # Throttled per-IP so that re-auth can't itself be brute-forced from a session.
    ip = _login_throttle.client_ip(request)
    if _login_throttle.retry_after(ip) > 0:
        return JSONResponse(
            {"detail": "Too many attempts. Try again shortly."}, status_code=429)
    try:
        data = await request.json()
    except json.JSONDecodeError:
        data = {}
    secret = store.get_totp_secret(user.username)
    if secret is None:
        return JSONResponse({"detail": "Two-factor authentication isn't set up."}, status_code=400)
    code = str(data.get("code") or "")
    if not (mfa.verify_code(secret, code) or store.consume_recovery_code(user.username, code)):
        _login_throttle.record_failure(ip)
        return JSONResponse(
            {"detail": "Enter your current authentication code to turn off two-factor."},
            status_code=401)
    _login_throttle.clear(ip)
    store.clear_mfa(user.username)
    logx.usage(f"user {user.username} disabled two-factor authentication",
               request=request, username=user.username, operation="login")
    return JSONResponse({"ok": True})


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


@app.get("/auth/login-appearance")
async def auth_login_appearance() -> Response:
    """Login-page background chosen in the admin Customize tab (pre-auth).

    Returns ``{type, color, image}``; the client applies it to the sign-in
    backdrop. ``type: "default"`` means keep the built-in theme colour.
    """
    return JSONResponse(store.login_appearance())


@app.get("/auth/license-status")
async def auth_license_status() -> Response:
    """Demo-mode / license state for the login panel (pre-auth).

    Computed here from the shared license + demo-marker files, NOT by asking the
    compute backend — so the login panel still reports "Demo Mode" / "No License
    installed" even after an unlicensed backend has stopped itself. Read-only
    (create=False): showing the login page never starts or renews the demo window.
    """
    try:
        status = licensing.evaluate()
        remaining = None if status.ok else licensing.demo_remaining_secs(create=False)
        return JSONResponse(
            {
                "state": status.state,
                "demoMode": not status.ok,
                "remainingSeconds": remaining,
                "licensee": status.licensee,
                "expires": status.expires,
            }
        )
    except Exception:  # noqa: BLE001 — a license probe must never break the login page
        return JSONResponse({"state": "unknown", "demoMode": False, "remainingSeconds": None})


@app.post("/auth/logout")
async def auth_logout(request: Request) -> Response:
    user = _current_user(request)
    logx.usage(
        f"user {user.username if user else 'unknown'} signed out",
        request=request,
        username=user.username if user else "",
        operation="logout",
    )
    if user is not None:
        # Invalidate this user's outstanding session tokens server-side (not just
        # the cookie) so a captured token can't be replayed after logout.
        store.bump_session_epoch(user.username)
        # Release this user's per-user Exasol connection on the backend (best-effort).
        try:
            await _get_client().post(
                "/api/disconnect", headers={"X-PMW-User": user.username}, timeout=5.0
            )
        except Exception:  # noqa: BLE001 — never block sign-out on the backend
            pass
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
            "passkeyAllowed": user.passkey_allowed if user else False,
            "mfaAllowed": user.mfa_allowed if user else False,
            "mfaEnabled": user.mfa_enabled if user else False,
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
        if k.lower() not in _HOP_BY_HOP | {"host", "x-pmw-user", "x-pmw-proxy-auth"}
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
