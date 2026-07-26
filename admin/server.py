"""Administrative interface — runs on its own port (default 8090).

Owns TLS/certificate management for the main app and the user allow-list. Guarded
by an admin session cookie; seeded with Administrator / Administrator on first run.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # local `pages` module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import (  # noqa: E402
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from pydantic import BaseModel, Field  # noqa: E402

import pages  # noqa: E402
from app.config import (  # noqa: E402
    ADMIN_PID_PATH,
    ADMIN_SESSION_TTL_SECS,
    DEFAULT_ADMIN_USERNAME,
    FRONTEND_HTTPS_PORT,
    FRONTEND_PORT,
    GUI_PID_PATH,
)
from app import licensing  # noqa: E402
from app import log_events as logx  # noqa: E402
from app.db.manager import db as legacy_db  # noqa: E402 — settings-backed backup state
from app.services import backup as backup_service  # noqa: E402
from app.services.certs import CertError  # noqa: E402
from app.store.logs import LEVELS, store as log_store  # noqa: E402
from app.store.crypto import read_session, sign_session  # noqa: E402
from app.store.security import User, store  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)

app = FastAPI(title="Process Mining Demonstrator — Administration", version="1.0.0")

COOKIE = "pmw_admin"

logx.install_request_logging(app, lambda r: _current_user(r))


# ── session helpers ───────────────────────────────────────────────────────────


def _issue_session(username: str) -> str:
    # Embed the user's session epoch so logout (which bumps it) invalidates this
    # token — otherwise the stateless Fernet token would stay valid until its TTL.
    payload = {"u": username, "e": store.session_epoch(username)}
    return sign_session(json.dumps(payload).encode("utf-8"))


def _admin_session_ttl() -> int:
    """Cookie lifetime = the admin idle timeout when set (a sliding window,
    re-issued on activity), else the absolute 8h fallback."""
    mins = store.admin_idle_timeout_mins
    return mins * 60 if mins > 0 else ADMIN_SESSION_TTL_SECS


def _current_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    raw = read_session(token, _admin_session_ttl())
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        username = data["u"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    user = store.get_user(username)
    if not (user and user.is_admin and user.is_enabled):
        return None
    # Reject tokens issued before the user's last logout (stale epoch).
    if data.get("e") != user.session_epoch:
        return None
    return user


def require_admin(request: Request) -> User:
    user = _current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _set_cookie(response: Response, request: Request, username: str) -> None:
    response.set_cookie(
        COOKIE,
        _issue_session(username),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=_admin_session_ttl(),
        path="/",
    )


# ── pages ─────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = _current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    logx.usage(
        "admin dashboard opened",
        request=request,
        username=user.username,
        operation="page",
    )
    return HTMLResponse(
        pages.dashboard_page(user.username, FRONTEND_PORT, FRONTEND_HTTPS_PORT)
    )


def _login_bg_css() -> str:
    """CSS `background` value for the admin sign-in page from the Customize tab,
    or "" to keep the theme default. Stored values are already validated by the
    security store; the guards here are defence-in-depth before CSS injection."""
    appearance = store.login_appearance()
    kind = appearance.get("type")
    if kind == "color":
        color = appearance.get("color", "")
        if (
            color.startswith("#")
            and len(color) == 7
            and all(c in "0123456789abcdefABCDEF" for c in color[1:])
        ):
            return color
    elif kind == "image":
        image = appearance.get("image", "")
        if image.startswith("data:image/") and '"' not in image:
            return f'var(--l-grouped) url("{image}") center / cover no-repeat'
    return ""


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request, inactivity: bool = False):
    if _current_user(request) is not None:
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(pages.login_page(inactivity=inactivity, bg_css=_login_bg_css()))


# Brief cache so the login screen doesn't re-probe the directory on every load.
_DIR_STATUS_TTL = 20.0
_dir_status: dict = {"at": 0.0, "value": None}


@app.get("/api/directory-status")
async def api_directory_status() -> Response:
    """Whether a directory (LDAP) server is configured and currently reachable.

    Unauthenticated, for the login screen's availability LED — mirrors the main app's
    ``/auth/directory-status``. Reports ``configured: false`` when no directory is set
    up (the client then shows nothing); reachability is the cached service-bind probe,
    run off the event loop so a slow server never blocks the page.
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
    except Exception:  # a probe must never break the login screen
        available = False
    value = {"configured": True, "available": available}
    _dir_status.update(at=now, value=value)
    return JSONResponse(value)


@app.post("/login", response_class=HTMLResponse)
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    # Local accounts always work (break-glass). Directory accounts may sign in here
    # only when the admin explicitly enabled it in the Directory tab — and, either way,
    # the panel is admins only, so a valid non-admin is refused. A directory user must
    # first be promoted to admin (Users tab) before they can get in.
    if store.ldap_admin_login_enabled:
        user = store.authenticate_app(username, password)  # local first, then directory
    else:
        user = store.authenticate(username, password)  # local-only
    if user is None or not user.is_admin:
        logx.warn(
            f"failed admin sign-in for username {username!r}",
            request=request,
            username=username,
            operation="login",
        )
        message = store.login_block_message(username) or (
            "Invalid credentials, or the account is not an administrator."
        )
        return HTMLResponse(
            pages.login_page(message, bg_css=_login_bg_css()), status_code=401
        )
    logx.usage(
        f"admin {user.username} signed in to the admin interface",
        request=request,
        username=user.username,
        operation="login",
    )
    response = RedirectResponse("/", status_code=303)
    _set_cookie(response, request, user.username)
    return response


@app.post("/logout")
def logout(request: Request):
    user = _current_user(request)
    logx.usage(
        f"admin {user.username if user else 'unknown'} signed out",
        request=request,
        username=user.username if user else "",
        operation="logout",
    )
    if user is not None:
        # Invalidate this user's outstanding session tokens server-side (not just
        # the cookie) so a captured token can't be replayed after logout.
        store.bump_session_epoch(user.username)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE, path="/")
    return response


# ── API: session / self ───────────────────────────────────────────────────────


class PasswordBody(BaseModel):
    password: str


@app.get("/api/session")
def api_session(request: Request, response: Response, user: User = Depends(require_admin)):
    # Polling this on activity slides the admin idle window (re-issues the cookie).
    _set_cookie(response, request, user.username)
    return {
        "username": user.username,
        "isAdmin": user.is_admin,
        "defaultPasswordActive": store.default_admin_password_active,
        "requireLogin": store.require_login,
        "idleTimeoutMins": store.idle_timeout_mins,
        "adminIdleTimeoutMins": store.admin_idle_timeout_mins,
        "maxFailedLogins": store.max_failed_logins,
        "builtinAdmin": DEFAULT_ADMIN_USERNAME,
        "license": licensing.evaluate().public(),
    }


class RequireLoginBody(BaseModel):
    requireLogin: bool


@app.post("/api/access/require-login")
def api_require_login(body: RequireLoginBody, user: User = Depends(require_admin)):
    store.set_require_login(body.requireLogin)
    return {"ok": True, "requireLogin": store.require_login}


class IdleTimeoutBody(BaseModel):
    minutes: int


@app.post("/api/access/idle-timeout")
def api_idle_timeout(body: IdleTimeoutBody, user: User = Depends(require_admin)):
    store.set_idle_timeout_mins(body.minutes)
    return {"ok": True, "idleTimeoutMins": store.idle_timeout_mins}


@app.post("/api/access/admin-idle-timeout")
def api_admin_idle_timeout(body: IdleTimeoutBody, user: User = Depends(require_admin)):
    """Idle timeout for the admin interface itself — separate from the app's."""
    store.set_admin_idle_timeout_mins(body.minutes)
    return {"ok": True, "adminIdleTimeoutMins": store.admin_idle_timeout_mins}


class MaxFailedLoginsBody(BaseModel):
    count: int


@app.post("/api/access/max-failed-logins")
def api_max_failed_logins(body: MaxFailedLoginsBody, user: User = Depends(require_admin)):
    store.set_max_failed_logins(body.count)
    logx.usage(
        f"admin {user.username} set the failed-sign-in lockout to "
        f"{store.max_failed_logins or 'off'}",
        username=user.username,
        operation="config",
    )
    return {"ok": True, "maxFailedLogins": store.max_failed_logins}


# ── License ─────────────────────────────────────────────────────────────────────


class LicenseUploadBody(BaseModel):
    content: str  # base64-encoded license.json bytes


# A signed license is a few hundred bytes; this cap just stops an absurd upload.
_MAX_LICENSE_B64 = 100_000


@app.get("/api/license")
def api_license(user: User = Depends(require_admin)):
    return licensing.evaluate().public()


@app.post("/api/license")
def api_license_upload(body: LicenseUploadBody, user: User = Depends(require_admin)):
    if len(body.content) > _MAX_LICENSE_B64:
        raise HTTPException(status_code=413, detail="License file is too large.")
    try:
        raw = base64.b64decode(body.content)
    except ValueError as exc:  # binascii.Error is a ValueError subclass
        raise HTTPException(status_code=400, detail="Invalid file content.") from exc

    status = licensing.install(raw)
    if status.state in ("invalid", "missing"):
        # Forged/corrupt/unparseable — nothing was stored.
        logx.warn(
            f"admin {user.username} uploaded a license that was rejected: {status.message}",
            username=user.username,
            operation="license",
        )
        raise HTTPException(status_code=400, detail=status.message)

    logx.usage(
        f"admin {user.username} installed a license — {status.message}",
        username=user.username,
        operation="license",
    )
    return {"ok": True, "license": status.public()}


@app.delete("/api/license")
def api_license_delete(user: User = Depends(require_admin)):
    removed = licensing.uninstall()
    if removed:
        logx.usage(
            f"admin {user.username} removed the installed license — the backend "
            "drops to Demo Mode",
            username=user.username,
            operation="license",
        )
    return {"ok": True, "removed": removed, "license": licensing.evaluate().public()}


# ── Logging ───────────────────────────────────────────────────────────────────


_LOG_PAGE_SIZES = (10, 25, 50, 100)


@app.get("/api/logs")
def api_logs(
    request: Request,
    level: str = "",
    severities: str = "",
    clientIp: str = "",
    operation: str = "",
    search: str = "",
    page: int = 1,
    perPage: int = 25,
    user: User = Depends(require_admin),
):
    sev_list = [s for s in severities.split(",") if s] if severities else None
    filt = dict(
        level=level or None,
        severities=sev_list,
        client_ip=clientIp,
        operation=operation,
        search=search,
    )
    per_page = perPage if perPage in _LOG_PAGE_SIZES else 25
    # The filter (incl. search) spans the whole log; paging only slices the view.
    total = log_store.count(**filt)
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    entries = log_store.query(**filt, limit=per_page, offset=(page - 1) * per_page)
    return {
        "entries": entries,
        "total": total,
        "page": page,
        "perPage": per_page,
        "pages": pages,
        "config": log_store.config(),
        "operations": log_store.operations(),
        "severities": list(LEVELS),
    }


class LogConfigBody(BaseModel):
    level: str | None = None
    maxBytes: int | None = None


@app.post("/api/logs/config")
def api_logs_config(body: LogConfigBody, user: User = Depends(require_admin)):
    if body.level is not None:
        log_store.set_level(body.level)
    if body.maxBytes is not None:
        log_store.set_max_bytes(body.maxBytes)
    logx.info(
        f"admin {user.username} updated logging config "
        f"(level={log_store.level}, maxBytes={log_store.max_bytes})",
        username=user.username,
        operation="config",
    )
    return {"ok": True, "config": log_store.config()}


@app.post("/api/logs/clear")
def api_logs_clear(user: User = Depends(require_admin)):
    log_store.clear()
    logx.warn(
        f"admin {user.username} cleared the live log",
        username=user.username,
        operation="config",
    )
    return {"ok": True}


@app.get("/api/logs/download")
def api_logs_download(
    level: str = "",
    severities: str = "",
    clientIp: str = "",
    operation: str = "",
    search: str = "",
    user: User = Depends(require_admin),
):
    sev_list = [s for s in severities.split(",") if s] if severities else None
    text = log_store.render(
        level=level or None,
        severities=sev_list,
        client_ip=clientIp,
        operation=operation,
        search=search,
        limit=5000,
    )
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": 'attachment; filename="pmw-log.log"'},
    )


# ── Backup / restore (moved here from the app's left panel) ───────────────────


class BackupExportBody(BaseModel):
    includePasswords: bool = False
    includeUsername: bool = True
    includeLlmApiKey: bool = False
    password: str = ""


class BackupInspectBody(BaseModel):
    content: str  # base64-encoded file bytes
    password: str = ""


class BackupRestoreBody(BackupInspectBody):
    options: dict[str, bool] = {}


# A real backup is well under this; the cap stops an oversized upload from being
# base64-decoded / decrypted / JSON-parsed into several full in-memory copies.
_MAX_BACKUP_B64 = 25_000_000  # ~18 MB decoded


def _decode_backup(body: BackupInspectBody) -> dict:
    if len(body.content) > _MAX_BACKUP_B64:
        raise HTTPException(status_code=413, detail="Backup file is too large.")
    try:
        raw = base64.b64decode(body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file content.") from exc
    if backup_service.is_encrypted(raw):
        if not body.password:
            # 400 (a client error), NOT 401 — the admin fetch helper redirects to
            # /login on any 401, which would bounce the page instead of prompting
            # for the encryption password.
            raise HTTPException(
                status_code=400,
                detail="This backup is encrypted — enter its password and Inspect again.",
            )
        try:
            raw = backup_service.decrypt(raw, body.password)
        except backup_service.BackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="The backup file format is invalid or corrupted."
        ) from exc


def _export_desc(body: BackupExportBody) -> str:
    inc = []
    if body.includeUsername:
        inc.append("usernames")
    if body.includePasswords:
        inc.append("passwords")
    if body.includeLlmApiKey:
        inc.append("LLM keys")
    return (
        f"includes: {', '.join(inc) or 'none'}; "
        f"{'encrypted' if body.password else 'PLAINTEXT'}"
    )


def _restore_opts_desc(options: dict[str, bool]) -> str:
    if not options:
        return "all (default)"
    enabled = [k for k, v in options.items() if v]
    return ", ".join(enabled) if enabled else "none"


@app.post("/api/backup/export")
def api_backup_export(
    body: BackupExportBody, request: Request, user: User = Depends(require_admin)
):
    try:
        payload = backup_service.export_payload(
            legacy_db,
            include_passwords=body.includePasswords,
            include_username=body.includeUsername,
            include_llm_api_key=body.includeLlmApiKey,
        )
        data = backup_service.encode(payload)
        if body.password:
            data = backup_service.encrypt(data, body.password)
    except Exception as exc:  # noqa: BLE001
        logx.error(
            f"admin {user.username} backup export failed: {exc}",
            request=request, username=user.username, operation="backup",
        )
        raise
    logx.usage(
        f"admin {user.username} exported a settings backup — {_export_desc(body)}",
        request=request, username=user.username, operation="backup",
    )
    stamp = datetime.datetime.now().strftime("%Y-%m-%d")
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ProcessMining-Backup-{stamp}.json"'
            )
        },
    )


@app.post("/api/backup/inspect")
def api_backup_inspect(
    body: BackupInspectBody, request: Request, user: User = Depends(require_admin)
):
    try:
        payload = _decode_backup(body)
    except HTTPException as exc:
        logx.warn(
            f"admin {user.username} backup inspect failed: {exc.detail}",
            request=request, username=user.username, operation="backup",
        )
        raise
    logx.usage(
        f"admin {user.username} inspected a backup file",
        request=request, username=user.username, operation="backup",
    )
    return backup_service.summarize(payload)


@app.post("/api/backup/restore")
def api_backup_restore(
    body: BackupRestoreBody, request: Request, user: User = Depends(require_admin)
):
    try:
        payload = _decode_backup(body)
    except HTTPException as exc:
        logx.warn(
            f"admin {user.username} backup restore failed (decode): {exc.detail}",
            request=request, username=user.username, operation="backup",
        )
        raise
    try:
        backup_service.restore(legacy_db, payload, body.options)
    except Exception as exc:  # noqa: BLE001
        logx.error(
            f"admin {user.username} backup restore failed: {exc}",
            request=request, username=user.username, operation="backup",
        )
        raise
    logx.warn(
        f"admin {user.username} restored a settings backup — options: "
        f"{_restore_opts_desc(body.options)}",
        request=request, username=user.username, operation="backup",
    )
    return {"ok": True}


@app.post("/api/self/password")
def api_self_password(body: PasswordBody, user: User = Depends(require_admin)):
    try:
        store.set_password(user.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# ── API: users ────────────────────────────────────────────────────────────────


class NewUserBody(BaseModel):
    username: str
    password: str
    isAdmin: bool = False


class EnabledBody(BaseModel):
    enabled: bool


class AdminBody(BaseModel):
    isAdmin: bool


class PowerBody(BaseModel):
    isPower: bool


@app.get("/api/users")
def api_users(user: User = Depends(require_admin)):
    return [u.public() for u in store.list_users()]


@app.post("/api/users")
def api_create_user(body: NewUserBody, user: User = Depends(require_admin)):
    try:
        return store.create_user(body.username, body.password, body.isAdmin).public()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/users/{username}/enabled")
def api_set_enabled(username: str, body: EnabledBody, user: User = Depends(require_admin)):
    try:
        store.set_enabled(username, body.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/users/{username}/admin")
def api_set_admin(username: str, body: AdminBody, user: User = Depends(require_admin)):
    try:
        store.set_admin(username, body.isAdmin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/users/{username}/power")
def api_set_power(username: str, body: PowerBody, user: User = Depends(require_admin)):
    try:
        store.set_power(username, body.isPower)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/users/{username}/password")
def api_set_user_password(
    username: str, body: PasswordBody, user: User = Depends(require_admin)
):
    if store.get_user(username) is None:
        raise HTTPException(status_code=404, detail="No such user.")
    try:
        store.set_password(username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/users/{username}")
def api_delete_user(username: str, user: User = Depends(require_admin)):
    try:
        store.delete_user(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# ── API: TLS & certificates ───────────────────────────────────────────────────


class TlsModeBody(BaseModel):
    mode: str


class GenerateBody(BaseModel):
    name: str = ""
    commonName: str
    sans: list[str] = []
    days: int = 825
    keySize: int = 2048
    activate: bool = False


class UploadBody(BaseModel):
    name: str = ""
    certPem: str
    keyPem: str
    activate: bool = False


@app.get("/api/tls")
def api_tls(user: User = Depends(require_admin)):
    return {
        "mode": store.tls_mode,
        "activeCertId": store.active_cert_id,
        "plan": store.tls_plan(),
        "certs": [c.public() for c in store.list_certificates()],
    }


@app.post("/api/tls/mode")
def api_tls_mode(body: TlsModeBody, user: User = Depends(require_admin)):
    try:
        store.set_tls_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "plan": store.tls_plan()}


@app.post("/api/certs/generate")
def api_generate_cert(body: GenerateBody, user: User = Depends(require_admin)):
    try:
        cert = store.generate_certificate(
            name=body.name,
            common_name=body.commonName,
            sans=body.sans,
            days=body.days,
            key_size=body.keySize,
        )
    except (CertError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.activate:
        store.activate_certificate(cert.id)
    return cert.public()


@app.post("/api/certs/upload")
def api_upload_cert(body: UploadBody, user: User = Depends(require_admin)):
    try:
        cert = store.upload_certificate(
            name=body.name, cert_pem=body.certPem, key_pem=body.keyPem
        )
    except (CertError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.activate:
        store.activate_certificate(cert.id)
    return cert.public()


@app.post("/api/certs/{cert_id}/activate")
def api_activate_cert(cert_id: str, user: User = Depends(require_admin)):
    try:
        store.activate_certificate(cert_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/certs/{cert_id}")
def api_delete_cert(cert_id: str, user: User = Depends(require_admin)):
    store.delete_certificate(cert_id)
    return {"ok": True}


@app.get("/api/certs/{cert_id}/download")
def api_download_cert(cert_id: str, user: User = Depends(require_admin)):
    pem = store.certificate_pem(cert_id)
    if pem is None:
        raise HTTPException(status_code=404, detail="No such certificate.")
    cert = store.get_certificate(cert_id)
    filename = (cert.name if cert else "certificate").replace(" ", "_") + ".crt"
    return PlainTextResponse(
        pem,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── API: restart the GUI server ───────────────────────────────────────────────


def _signal_launcher(pid_path) -> int:
    """SIGHUP the launcher named by its PID file so it rebinds its listeners.
    Returns the PID; raises HTTPException on any problem."""
    if not pid_path.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                "The app server is not managed by the launcher (no PID file). "
                "Start it with ./run.sh, then try again."
            ),
        )
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail="Invalid PID file.") from exc
    try:
        os.kill(pid, 0)  # probe: is the process alive?
    except ProcessLookupError as exc:
        raise HTTPException(
            status_code=409, detail="The app server process is not running."
        ) from exc
    except PermissionError:
        pass  # alive but owned by another user — signalling may still work
    try:
        os.kill(pid, signal.SIGHUP)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Could not signal the app server: {exc}"
        ) from exc
    return pid


@app.post("/api/restart")
def api_restart(user: User = Depends(require_admin)):
    """Signal the GUI *and* admin launchers (SIGHUP) to rebind their listeners with
    the current TLS plan — applying a mode or certificate change without a terminal.

    The admin interface follows the same TLS mode, so it restarts itself too: this
    request's connection may drop and, if the mode changed, the admin moves to a
    different scheme/port — reconnect there if this page stops responding."""
    logx.info(
        f"admin {user.username} restarted the app + admin servers",
        username=user.username,
        operation="restart",
    )
    gui_pid = _signal_launcher(GUI_PID_PATH)
    # Restart the admin launcher too, best-effort: signalling our own launcher tears
    # down this very listener, so don't fail the request if the response races it.
    admin_pid: int | None = None
    if ADMIN_PID_PATH.exists():
        try:
            admin_pid = int(ADMIN_PID_PATH.read_text().strip())
            os.kill(admin_pid, signal.SIGHUP)
        except (ValueError, OSError):
            admin_pid = None
    return {"ok": True, "pid": gui_pid, "adminPid": admin_pid}


# ── API: connections (admin-defined, assigned to users) ───────────────────────


class ConnectionBody(BaseModel):
    id: str | None = None
    name: str
    comment: str = ""
    host: str = ""
    port: int = 8563
    username: str = ""
    schema_: str = Field(default="", alias="schema")
    useTLS: bool = False
    certModeRaw: str = "verify"
    fingerprint: str = ""
    minRSAKeySizeBits: int = 2048
    password: str | None = None  # omit to keep, "" to clear, value to set
    llmURL: str = ""
    llmModel: str = ""
    llmKey: str | None = None
    assignments: list[str] = []

    model_config = {"populate_by_name": True}


class AssignmentsBody(BaseModel):
    assignments: list[str]


class ConnectionTestBody(BaseModel):
    host: str
    port: int = 8563
    username: str = ""
    password: str = ""
    schema_: str = Field(default="", alias="schema")
    useTLS: bool = False
    certModeRaw: str = "verify"
    fingerprint: str = ""
    minRSAKeySizeBits: int = 2048
    llmURL: str = ""
    llmKey: str = ""

    model_config = {"populate_by_name": True}


def _connection_payload(body: ConnectionBody) -> dict:
    data: dict = {
        "id": body.id,
        "name": body.name,
        "comment": body.comment,
        "host": body.host,
        "port": body.port,
        "username": body.username,
        "schema": body.schema_,
        "useTLS": body.useTLS,
        "certModeRaw": body.certModeRaw,
        "fingerprint": body.fingerprint,
        "minRSAKeySizeBits": body.minRSAKeySizeBits,
        "llmURL": body.llmURL,
        "llmModel": body.llmModel,
        "assignments": body.assignments,
    }
    # Only forward secrets that were explicitly provided (None ⇒ keep existing).
    if body.password is not None:
        data["password"] = body.password
    if body.llmKey is not None:
        data["llmKey"] = body.llmKey
    return data


@app.get("/api/connections")
def api_connections(user: User = Depends(require_admin)):
    return [c.admin_public() for c in store.list_connections()]


@app.post("/api/connections")
def api_upsert_connection(body: ConnectionBody, user: User = Depends(require_admin)):
    try:
        conn = store.upsert_connection(_connection_payload(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return conn.admin_public()


@app.post("/api/connections/{conn_id}/assignments")
def api_set_assignments(
    conn_id: str, body: AssignmentsBody, user: User = Depends(require_admin)
):
    try:
        store.set_assignments(conn_id, body.assignments)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/connections/{conn_id}")
def api_delete_connection(conn_id: str, user: User = Depends(require_admin)):
    store.delete_connection(conn_id)
    return {"ok": True}


@app.post("/api/connections/test")
async def api_test_connection(body: ConnectionTestBody, user: User = Depends(require_admin)):
    from app.db.manager import check_llm_reachable, test_db_connection
    from app.models import LLMServer
    from app.services import llm as llm_service

    db_error = await test_db_connection(
        host=body.host,
        port=body.port,
        username=body.username,
        password=body.password,
        schema=body.schema_,
        use_tls=body.useTLS,
        cert_mode=body.certModeRaw,
        fingerprint=body.fingerprint,
        min_rsa_bits=body.minRSAKeySizeBits,
    )

    llm_error: str | None = None
    llm_models: list[str] = []
    if body.llmURL.strip():
        llm = LLMServer(serverURL=body.llmURL, apiKey=body.llmKey)
        if await check_llm_reachable(llm):
            try:
                llm_models = await llm_service.list_models(body.llmURL, body.llmKey)
            except Exception as exc:  # noqa: BLE001
                llm_error = str(exc)
                logx.warn(
                    f"LLM server test failed — {body.llmURL}: {exc}",
                    operation="llm-test",
                )
        else:
            llm_error = "LLM server not reachable."  # check_llm_reachable logged the cause

    return {"dbError": db_error, "llmError": llm_error, "llmModels": llm_models}


@app.post("/api/connections/provision-schema")
async def api_provision_schema(body: ConnectionTestBody, user: User = Depends(require_admin)):
    """Create the process-mining schema + tables using the supplied credentials.

    Requires elevated database privileges (CREATE SCHEMA / CREATE TABLE) that only a
    database administrator can grant — the app cannot.
    """
    from app.db.schema_ddl import provision_process_mining_schema

    return await provision_process_mining_schema(
        host=body.host,
        port=body.port,
        username=body.username,
        password=body.password,
        schema=body.schema_,
        use_tls=body.useTLS,
        cert_mode=body.certModeRaw,
        fingerprint=body.fingerprint,
        min_rsa_bits=body.minRSAKeySizeBits,
    )


# ── LDAP / directory ──────────────────────────────────────────────────────────


class LdapConfigBody(BaseModel):
    enabled: bool = False
    serverURI: str = ""
    startTLS: bool = False
    verifyCert: bool = True
    caCert: str = ""
    bindDN: str = ""
    bindPassword: str | None = None  # omit to keep, "" to clear, value to set
    baseDN: str = ""
    userFilter: str = "(uid={username})"
    loginAttr: str = "uid"
    emailAttr: str = "mail"
    displayAttr: str = "cn"
    adminLoginEnabled: bool = False


class LdapTestBody(LdapConfigBody):
    testUsername: str = ""
    testPassword: str = ""


def _ldap_payload(body: LdapConfigBody) -> dict:
    data: dict = {
        "enabled": body.enabled,
        "serverURI": body.serverURI,
        "startTLS": body.startTLS,
        "verifyCert": body.verifyCert,
        "caCert": body.caCert,
        "bindDN": body.bindDN,
        "baseDN": body.baseDN,
        "userFilter": body.userFilter,
        "loginAttr": body.loginAttr,
        "emailAttr": body.emailAttr,
        "displayAttr": body.displayAttr,
        "adminLoginEnabled": body.adminLoginEnabled,
    }
    if body.bindPassword is not None:
        data["bindPassword"] = body.bindPassword
    return data


@app.get("/api/ldap")
def api_ldap(user: User = Depends(require_admin)):
    return store.ldap_admin_public()


@app.post("/api/ldap")
def api_save_ldap(body: LdapConfigBody, user: User = Depends(require_admin)):
    store.set_ldap_config(_ldap_payload(body))
    return store.ldap_admin_public()


@app.post("/api/ldap/test")
def api_test_ldap(body: LdapTestBody, user: User = Depends(require_admin)):
    from app.services.ldap_auth import LdapSettings, test_settings

    # Test the *submitted* settings; fall back to the stored bind password when the
    # field was left blank (so testing an already-saved config needs no re-typing).
    bind_password = body.bindPassword
    if bind_password is None:
        bind_password = store.ldap_settings().bind_password
    settings = LdapSettings(
        enabled=body.enabled,
        server_uri=body.serverURI,
        start_tls=body.startTLS,
        verify_cert=body.verifyCert,
        ca_cert=body.caCert,
        bind_dn=body.bindDN,
        bind_password=bind_password or "",
        base_dn=body.baseDN,
        user_filter=body.userFilter or "(uid={username})",
        login_attr=body.loginAttr or "uid",
        email_attr=body.emailAttr or "mail",
        display_attr=body.displayAttr or "cn",
    )
    return test_settings(settings, body.testUsername, body.testPassword)


class CustomizeLoginBody(BaseModel):
    type: str
    color: str = ""
    image: str | None = None


@app.get("/api/customize/login")
def api_customize_login(user: User = Depends(require_admin)):
    return store.login_appearance()


@app.post("/api/customize/login")
def api_save_customize_login(
    body: CustomizeLoginBody, user: User = Depends(require_admin)
):
    try:
        appearance = store.set_login_appearance(
            type=body.type, color=body.color, image=body.image
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logx.usage(
        f"admin {user.username} set the login page background to {appearance['type']}",
        username=user.username,
        operation="customize",
    )
    return appearance


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})
