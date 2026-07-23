"""Administrative interface — runs on its own port (default 8090).

Owns TLS/certificate management for the main app and the user allow-list. Guarded
by an admin session cookie; seeded with Administrator / Administrator on first run.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
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
    ADMIN_SESSION_TTL_SECS,
    FRONTEND_HTTPS_PORT,
    FRONTEND_PORT,
    GUI_PID_PATH,
)
from app.services.certs import CertError  # noqa: E402
from app.store.crypto import read_session, sign_session  # noqa: E402
from app.store.security import User, store  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)

app = FastAPI(title="Process Mining Demonstrator — Administration", version="1.0.0")

COOKIE = "pmw_admin"


# ── session helpers ───────────────────────────────────────────────────────────


def _issue_session(username: str) -> str:
    return sign_session(json.dumps({"u": username}).encode("utf-8"))


def _current_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    raw = read_session(token, ADMIN_SESSION_TTL_SECS)
    if raw is None:
        return None
    try:
        username = json.loads(raw)["u"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    user = store.get_user(username)
    if user and user.is_admin and user.is_enabled:
        return user
    return None


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
        max_age=ADMIN_SESSION_TTL_SECS,
        path="/",
    )


# ── pages ─────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = _current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(
        pages.dashboard_page(user.username, FRONTEND_PORT, FRONTEND_HTTPS_PORT)
    )


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    if _current_user(request) is not None:
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(pages.login_page())


@app.post("/login", response_class=HTMLResponse)
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    # Local accounts first (break-glass), then the directory when enabled — but the
    # admin panel is admins only, so a valid non-admin (local or LDAP) is refused.
    # LDAP users become admins only after a local admin tags them in the Users tab.
    user = store.authenticate_app(username, password)
    if user is None or not user.is_admin:
        return HTMLResponse(
            pages.login_page("Invalid credentials, or the account is not an administrator."),
            status_code=401,
        )
    response = RedirectResponse("/", status_code=303)
    _set_cookie(response, request, user.username)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE, path="/")
    return response


# ── API: session / self ───────────────────────────────────────────────────────


class PasswordBody(BaseModel):
    password: str


@app.get("/api/session")
def api_session(user: User = Depends(require_admin)):
    return {
        "username": user.username,
        "isAdmin": user.is_admin,
        "defaultPasswordActive": store.default_admin_password_active,
        "requireLogin": store.require_login,
    }


class RequireLoginBody(BaseModel):
    requireLogin: bool


@app.post("/api/access/require-login")
def api_require_login(body: RequireLoginBody, user: User = Depends(require_admin)):
    store.set_require_login(body.requireLogin)
    return {"ok": True, "requireLogin": store.require_login}


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


@app.post("/api/restart")
def api_restart(user: User = Depends(require_admin)):
    """Signal the GUI launcher (SIGHUP) to rebind its listeners with the current
    TLS plan — applying a mode or certificate change without a terminal."""
    if not GUI_PID_PATH.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                "The app server is not managed by the launcher (no PID file). "
                "Start it with ./run.sh, then try again."
            ),
        )
    try:
        pid = int(GUI_PID_PATH.read_text().strip())
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
    return {"ok": True, "pid": pid}


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
            llm_models = await llm_service.list_models(body.llmURL, body.llmKey)
        else:
            llm_error = "LLM server not reachable."

    return {"dbError": db_error, "llmError": llm_error, "llmModels": llm_models}


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


@app.get("/health")
def health():
    return JSONResponse({"status": "ok"})
