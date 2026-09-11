"""Main-app authentication tests — the GUI server's sign-in gate.

Drives the real GUI-server FastAPI app (`frontend/server.py`) with an isolated
security store, verifying that /api/* is gated when sign-in is required and open
otherwise, and that the login/session/logout cookie flow works.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def gui(tmp_path, monkeypatch):
    """A TestClient over the GUI server, wired to a throwaway security store."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))

    # Reload the config + security stack against the temp data dir.
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security

    import app.store.security as security_mod

    importlib.reload(security_mod)

    # The auth flow now lives in the shared surface factory; reload it (after the
    # security/crypto/config reloads) so it binds to THIS test's store instance.
    import app.web_surface as web_surface

    importlib.reload(web_surface)

    # Load frontend/server.py as a module (it lives outside the app package).
    frontend_dir = Path(config.PROJECT_ROOT) / "frontend"
    sys.path.insert(0, str(frontend_dir))
    for name in ("server",):
        sys.modules.pop(name, None)
    server = importlib.import_module("server")
    importlib.reload(server)

    # Point the GUI's proxy at a stub backend so gated calls don't need Exasol.
    class _StubResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        content = b'{"stub": true}'

    class _StubClient:
        async def request(self, *args, **kwargs):
            return _StubResponse()

    # The surface reaches the backend through this hook — stub the whole backend.
    server.app.state.get_backend_client = lambda: _StubClient()

    return server, security_mod.store


def test_backend_proxy_pins_the_internal_ca(gui, monkeypatch, tmp_path):
    """The GUI→backend hop is HTTPS and verified against the pinned internal CA;
    it falls back to system trust only when the pinned CA file is absent."""
    import app.web_surface as web_surface

    assert web_surface.BACKEND_URL.startswith("https://")  # encrypted hop

    ca = tmp_path / "internal.crt"
    ca.write_text("x", encoding="utf-8")
    monkeypatch.setattr(web_surface, "BACKEND_CA_PATH", str(ca))
    assert web_surface._backend_verify() == str(ca)  # pinned

    monkeypatch.setattr(web_surface, "BACKEND_CA_PATH", str(tmp_path / "missing.crt"))
    assert web_surface._backend_verify() is True  # system trust fallback


def test_health_is_open_even_when_login_required(gui):
    server, store = gui
    assert store.require_login is True
    client = TestClient(server.app)
    # /api/health is exempt from the gate.
    assert client.get("/api/health").status_code == 200


def test_api_is_gated_without_a_session(gui):
    server, store = gui
    client = TestClient(server.app)
    resp = client.get("/api/projects")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_session_reports_unauthenticated_and_require_login(gui):
    server, _ = gui
    client = TestClient(server.app)
    body = client.get("/auth/session").json()
    assert body == {
        "authenticated": False,
        "username": None,
        "isAdmin": False,
        "isPower": False,
        "isDeveloper": False,
        "displayName": None,
        "authSource": None,
        "requireLogin": True,
        "idleTimeoutMins": 0,
        "actionsEnabled": False,
        "passkeyAllowed": False,
        "mfaAllowed": False,
        "mfaEnabled": False,
    }


def test_session_reports_actions_enabled_flag(gui):
    server, store = gui
    client = TestClient(server.app)
    # Opt-in feature: off by default, flips when the admin enables it.
    assert client.get("/auth/session").json()["actionsEnabled"] is False
    store.set_actions_enabled(True)
    assert client.get("/auth/session").json()["actionsEnabled"] is True


def test_session_reports_and_refreshes_with_idle_timeout(gui):
    server, store = gui
    client = TestClient(server.app)
    # Default: disabled.
    assert client.get("/auth/session").json()["idleTimeoutMins"] == 0
    store.set_idle_timeout_mins(20)
    assert client.get("/auth/session").json()["idleTimeoutMins"] == 20

    # Signing in issues a session; polling /auth/session slides it (re-sets cookie).
    client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    )
    resp = client.get("/auth/session")
    assert resp.json()["authenticated"] is True
    assert server.SESSION_COOKIE in resp.cookies  # sliding refresh on activity


def test_login_wrong_password_is_rejected(gui):
    server, _ = gui
    client = TestClient(server.app)
    resp = client.post("/auth/login", json={"username": "Administrator", "password": "nope"})
    assert resp.status_code == 401
    assert server.SESSION_COOKIE not in resp.cookies


def test_login_then_access_then_logout(gui):
    server, _ = gui
    client = TestClient(server.app)

    # Sign in with the seeded administrator.
    resp = client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    )
    assert resp.status_code == 200
    assert server.SESSION_COOKIE in client.cookies

    # The session is now recognised, and gated API calls pass the guard.
    session = client.get("/auth/session").json()
    assert session["authenticated"] is True
    assert session["username"] == "Administrator"
    assert client.get("/api/projects").status_code == 200

    # Logging out clears the cookie and re-gates the API.
    client.post("/auth/logout")
    assert client.get("/auth/session").json()["authenticated"] is False
    assert client.get("/api/projects").status_code == 401


def test_disabled_user_cannot_sign_in(gui):
    server, store = gui
    store.create_user("bob", "pw", is_admin=False)
    store.set_enabled("bob", False)
    client = TestClient(server.app)
    resp = client.post("/auth/login", json={"username": "bob", "password": "pw"})
    assert resp.status_code == 401


def test_open_access_when_login_not_required(gui):
    server, store = gui
    store.set_require_login(False)
    client = TestClient(server.app)
    # No session, but the API is reachable because sign-in is not required.
    assert client.get("/api/projects").status_code == 200
    assert client.get("/auth/session").json()["requireLogin"] is False


# ── Directory (LDAP) availability indicator ───────────────────────────────────


def test_directory_status_not_configured_reports_unconfigured(gui):
    server, _ = gui
    client = TestClient(server.app)
    # No LDAP configured ⇒ the login panel shows no indicator.
    assert client.get("/auth/directory-status").json() == {
        "configured": False,
        "available": False,
    }


def test_directory_status_probes_when_configured(gui, monkeypatch):
    server, store = gui
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://dir", "baseDN": "dc=x"})

    import app.services.ldap_auth as ldap_auth

    # Reachable — the service-bind probe succeeds.
    monkeypatch.setattr(ldap_auth, "test_settings", lambda *a, **k: {"ok": True})
    client = TestClient(server.app)
    assert client.get("/auth/directory-status").json() == {
        "configured": True,
        "available": True,
    }


def test_directory_status_hidden_when_admin_switch_off(gui, monkeypatch):
    server, store = gui
    # Directory configured and reachable, but the admin hid the login LED.
    store.set_ldap_config(
        {"enabled": True, "serverURI": "ldap://dir", "baseDN": "dc=x", "showStatusOnLogin": False}
    )
    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(ldap_auth, "test_settings", lambda *a, **k: {"ok": True})
    client = TestClient(server.app)
    # Reported as unconfigured ⇒ the login panel renders no indicator.
    assert client.get("/auth/directory-status").json() == {
        "configured": False,
        "available": False,
    }


def test_directory_status_reports_unavailable_on_probe_failure(gui, monkeypatch):
    server, store = gui
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://dir", "baseDN": "dc=x"})

    import app.services.ldap_auth as ldap_auth

    # Unreachable — the probe returns ok:false (or raises); the endpoint must not error.
    def _boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ldap_auth, "test_settings", _boom)
    client = TestClient(server.app)
    assert client.get("/auth/directory-status").json() == {
        "configured": True,
        "available": False,
    }


# ── Session invalidation on logout ────────────────────────────────────────────


def test_app_responses_carry_security_headers(gui):
    server, _ = gui
    r = TestClient(server.app).get("/auth/session")
    assert r.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in (r.headers.get("content-security-policy") or "")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_app_rejects_admin_audience_cookie(gui):
    """An admin session cookie (audience "admin") must not authenticate the main
    app, even though both are signed with the same key and name a valid user."""
    import json as _json

    import app.store.crypto as crypto

    server, store = gui
    epoch = store.session_epoch("Administrator")
    forged = crypto.sign_session(
        _json.dumps({"u": "Administrator", "e": epoch, "a": "admin"}).encode("utf-8")
    )
    client = TestClient(server.app)
    client.cookies.set(server.SESSION_COOKIE, forged)
    assert client.get("/api/projects").status_code == 401


def test_logout_invalidates_captured_token(gui):
    """A token captured before logout must be rejected afterwards — server-side
    invalidation via the per-user session epoch, not just clearing the cookie."""
    server, _ = gui
    client = TestClient(server.app)
    client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    )
    token = client.cookies.get(server.SESSION_COOKIE)
    assert token

    def _replay_status() -> int:
        c = TestClient(server.app)
        c.cookies.set(server.SESSION_COOKIE, token)
        return c.get("/api/projects").status_code

    assert _replay_status() == 200  # the captured token works before logout
    client.post("/auth/logout")  # bumps the user's session epoch
    assert _replay_status() == 401  # the same token no longer passes the gate


# ── License / Demo Mode status (pre-auth, computed locally) ────────────────────


def test_license_status_demo_and_licensed(gui, monkeypatch):
    server, _ = gui
    import app.licensing as licensing

    client = TestClient(server.app)

    # No valid license → Demo Mode with the remaining grace seconds.
    monkeypatch.setattr(
        licensing, "evaluate", lambda: licensing.LicenseStatus("missing", message="none")
    )
    monkeypatch.setattr(licensing, "demo_remaining_secs", lambda create: 300)
    body = client.get("/auth/license-status").json()
    assert body["demoMode"] is True
    assert body["remainingSeconds"] == 300

    # Valid license → not demo, no countdown.
    monkeypatch.setattr(
        licensing,
        "evaluate",
        lambda: licensing.LicenseStatus("valid", licensee="Acme", expires="2099-01-01"),
    )
    body = client.get("/auth/license-status").json()
    assert body["demoMode"] is False
    assert body["remainingSeconds"] is None
    assert body["licensee"] == "Acme"


def test_login_appearance_endpoint_is_open(gui):
    """The login background is served pre-auth (the login page needs it)."""
    server, store = gui
    client = TestClient(server.app)
    body = client.get("/auth/login-appearance").json()
    assert {k: body[k] for k in ("type", "color", "image")} == {
        "type": "default",
        "color": "",
        "image": "",
    }
    assert body["version"]  # release label shown on the sign-in panel
    store.set_login_appearance(type="color", color="#0a84ff")
    body = client.get("/auth/login-appearance").json()
    assert {k: body[k] for k in ("type", "color", "image")} == {
        "type": "color",
        "color": "#0a84ff",
        "image": "",
    }


# ── Passkeys (WebAuthn) — the app's sign-in alternative ──────────────────────


def test_session_reports_passkey_allowed_for_signed_in_user(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_passkey_allowed("alice", True)
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})
    body = client.get("/auth/session").json()
    assert body["authenticated"] is True and body["passkeyAllowed"] is True


def test_login_response_includes_passkey_allowed(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_passkey_allowed("alice", True)
    client = TestClient(server.app)
    body = client.post("/auth/login", json={"username": "alice", "password": "pw"}).json()
    assert body["passkeyAllowed"] is True


def test_passkey_auth_begin_is_enumeration_resistant(gui):
    # An ineligible-but-real account, an unknown username and an eligible account
    # must all return the SAME shape (200 + challenge + one allowCredentials + a
    # challenge cookie), so a scripted probe can't tell which usernames have
    # passkeys. Only genuine WebAuthn verification (finish) separates them.
    from app.services import passkey
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)  # exists, no passkey
    store.create_user("carol", "pw", is_admin=False)
    store.set_passkey_allowed("carol", True)
    store.add_credential("carol", credential_id="cred-a", public_key="K", sign_count=0)

    def shape(username: str) -> tuple:
        client = TestClient(server.app)
        r = client.post("/auth/passkey/auth/begin", json={"username": username})
        body = r.json()
        return (
            r.status_code,
            "detail" in body,
            len(body.get("allowCredentials", [])),
            passkey.CHALLENGE_COOKIE in client.cookies,
        )

    eligible = shape("carol")
    assert eligible == (200, False, 1, True)
    # Same signature for a real-but-ineligible account and a nonexistent one.
    assert shape("alice") == eligible          # exists, passkeys not enabled
    assert shape("ghost") == eligible          # no such user
    assert shape("") == eligible               # empty username


def test_passkey_auth_begin_decoy_ids_are_stable_but_not_real(gui):
    from webauthn.helpers import bytes_to_base64url
    server, store = gui
    cid = bytes_to_base64url(b"carol-credential")  # clean base64url (round-trips)
    store.create_user("carol", "pw", is_admin=False)
    store.set_passkey_allowed("carol", True)
    store.add_credential("carol", credential_id=cid, public_key="K", sign_count=0)

    def allow_id(username: str) -> str:
        r = TestClient(server.app).post(
            "/auth/passkey/auth/begin", json={"username": username})
        return r.json()["allowCredentials"][0]["id"]

    # A decoy id is deterministic per-username (repeat probes get the same answer)…
    assert allow_id("ghost") == allow_id("ghost")
    # …but differs per username and is not the real credential id.
    assert allow_id("ghost") != allow_id("other")
    assert allow_id("carol") == cid            # eligible → the genuine id
    assert allow_id("ghost") != cid


def test_passkey_register_begin_requires_a_session(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_passkey_allowed("alice", True)
    client = TestClient(server.app)
    # No session cookie → enrolment is refused.
    r = client.post("/auth/passkey/register/begin")
    assert r.status_code in (401, 403)


# ── Two-factor (TOTP) — the app's second sign-in step ────────────────────────


def _enrol_mfa(store, username: str) -> str:
    """Give `username` a confirmed TOTP secret; returns it for code generation."""
    import app.services.mfa as mfa
    secret = mfa.new_secret()
    store.set_mfa_allowed(username, True)
    store.set_totp_secret(username, secret)
    return secret


def test_password_login_asks_for_a_code_when_mfa_active(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    secret = _enrol_mfa(store, "alice")
    client = TestClient(server.app)

    r = client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 200
    body = r.json()
    assert body == {"mfaRequired": True, "username": "alice"}
    # No session yet — a pending cookie is set instead, and the API stays gated.
    assert server.SESSION_COOKIE not in client.cookies
    assert client.get("/api/projects").status_code == 401


def test_mfa_verify_with_totp_signs_in(gui):
    import pyotp
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    secret = _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})

    r = client.post("/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert r.json()["username"] == "alice" and r.json()["mfaEnabled"] is True
    assert server.SESSION_COOKIE in client.cookies
    assert client.get("/auth/session").json()["authenticated"] is True


def test_mfa_verify_rejects_a_wrong_code(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})

    r = client.post("/auth/mfa/verify", json={"code": "000000"})
    assert r.status_code == 401
    assert server.SESSION_COOKIE not in client.cookies


def test_mfa_verify_accepts_a_recovery_code(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    _enrol_mfa(store, "alice")
    store.set_recovery_codes("alice", ["aaaa1111-bbbb2222"])
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})

    r = client.post("/auth/mfa/verify", json={"code": "aaaa1111-bbbb2222"})
    assert r.status_code == 200 and server.SESSION_COOKIE in client.cookies
    assert store.recovery_codes_remaining("alice") == 0  # consumed


def test_mfa_verify_without_a_pending_cookie_is_rejected(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    _enrol_mfa(store, "alice")
    client = TestClient(server.app)  # never did the password step
    r = client.post("/auth/mfa/verify", json={"code": "000000"})
    assert r.status_code == 401


def _sign_in(client, username="alice", password="pw"):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_mfa_setup_requires_allow_and_confirms_a_code(gui):
    import pyotp
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    client = TestClient(server.app)
    _sign_in(client)

    # Not allowed yet → setup is refused.
    assert client.post("/auth/mfa/setup/begin").status_code == 403

    store.set_mfa_allowed("alice", True)
    begin = client.post("/auth/mfa/setup/begin")
    assert begin.status_code == 200
    secret = begin.json()["secret"]
    assert begin.json()["otpauthUri"].startswith("otpauth://") and begin.json()["qrSvg"]

    # A wrong confirmation code doesn't enable it.
    assert client.post("/auth/mfa/setup/finish", json={"code": "000000"}).status_code == 400
    assert store.get_user("alice").mfa_enabled is False

    fin = client.post("/auth/mfa/setup/finish", json={"code": pyotp.TOTP(secret).now()})
    assert fin.status_code == 200 and len(fin.json()["recoveryCodes"]) == 10
    assert store.get_user("alice").mfa_enabled is True
    assert client.get("/auth/mfa/status").json() == {
        "mfaAllowed": True, "enabled": True, "recoveryRemaining": 10}


def test_mfa_disable_requires_the_current_code(gui):
    import pyotp
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    secret = _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    _sign_in(client)
    # Enrolled server-side; a fresh session is needed for the authed endpoints —
    # sign-in above is mfa-gated, so complete it via the pending cookie.
    client.post("/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})

    # A hijacked session can't strip the second factor without the code.
    assert client.post("/auth/mfa/disable", json={}).status_code == 401
    assert client.post("/auth/mfa/disable", json={"code": "000000"}).status_code == 401
    assert store.get_user("alice").mfa_enabled is True

    # The current code turns it off.
    r = client.post("/auth/mfa/disable", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert store.get_user("alice").mfa_enabled is False


def test_passkey_login_skips_the_mfa_step(gui):
    # A passkey is already strong auth, so an mfa-enrolled user signing in with a
    # passkey is NOT asked for a code. The password path is the one that triggers
    # MFA (covered above); here we just confirm the passkey begin stays reachable
    # (enumeration-resistant 200, not a leaky refusal) for an mfa-enrolled account.
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    assert client.post("/auth/passkey/auth/begin", json={"username": "alice"}).status_code == 200


# ── App sign-in throttle + MFA hardening (findings 1, 2, 4) ──────────────────


def test_app_login_is_ip_throttled(gui):
    # The app relies on account lockout, which exempts the built-in Administrator;
    # the per-IP throttle covers that gap. After _LOGIN_IP_MAX failures the host is
    # told to wait (429), even for the exempt Administrator.
    server, _ = gui
    client = TestClient(server.app)
    for _ in range(server.app.state.login_throttle.max_fails):
        r = client.post("/auth/login",
                        json={"username": "Administrator", "password": "nope"})
        assert r.status_code == 401
    r = client.post("/auth/login", json={"username": "Administrator", "password": "nope"})
    assert r.status_code == 429
    # Even a correct password is refused while the cooldown is active.
    assert client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"}
    ).status_code == 429


def test_app_login_throttle_clears_on_success(gui):
    server, _ = gui
    client = TestClient(server.app)
    for _ in range(server.app.state.login_throttle.max_fails - 1):  # stay below the threshold
        client.post("/auth/login", json={"username": "Administrator", "password": "nope"})
    ok = client.post(
        "/auth/login", json={"username": "Administrator", "password": "Administrator"})
    assert ok.status_code == 200  # (Administrator has no MFA here)
    # A fresh burst of failures is allowed — the counter was cleared on success.
    for _ in range(server.app.state.login_throttle.max_fails - 1):
        assert client.post(
            "/auth/login", json={"username": "Administrator", "password": "nope"}
        ).status_code == 401


def test_mfa_wrong_code_does_not_lock_the_account(gui):
    # A mistyped/expired TOTP is throttled per-IP but must NOT count toward the
    # account lockout — otherwise fat-fingering the code disables the account.
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_max_failed_logins(3)
    _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})

    for _ in range(3):
        assert client.post("/auth/mfa/verify", json={"code": "000000"}).status_code == 401
    # Still enabled and not locked, despite 3 wrong codes.
    u = store.get_user("alice")
    assert u.is_enabled is True and u.login_locked is False


def test_mfa_pending_cookie_cannot_be_used_as_a_session(gui):
    # The pre-auth pending cookie shares the Fernet key with the session cookie, so
    # confirm it is NOT accepted as one (distinct name, namespaced audience, no epoch).
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    r = client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert r.json().get("mfaRequired") is True
    from app.services import mfa
    pending = client.cookies.get(mfa.PENDING_COOKIE)
    assert pending

    forged = TestClient(server.app)
    forged.cookies.set(server.SESSION_COOKIE, pending)
    assert forged.get("/auth/session").json()["authenticated"] is False
    assert forged.get("/api/projects").status_code == 401


def test_mfa_disable_is_ip_throttled(gui):
    # The re-auth code check on disable must itself be throttled, or a hijacked
    # session could brute-force the 6-digit code to strip the second factor.
    import pyotp
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    secret = _enrol_mfa(store, "alice")
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})
    client.post("/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})  # clears throttle

    for _ in range(server.app.state.login_throttle.max_fails):
        assert client.post("/auth/mfa/disable", json={"code": "000000"}).status_code == 401
    # Now throttled — even a correct code is refused, so 2FA stays on.
    assert client.post("/auth/mfa/disable", json={"code": "000000"}).status_code == 429
    assert client.post(
        "/auth/mfa/disable", json={"code": pyotp.TOTP(secret).now()}).status_code == 429
    assert store.get_user("alice").mfa_enabled is True


# ── Mandatory 2FA enrolment (enabled but not configured) ─────────────────────


def test_login_forces_2fa_setup_when_required(gui):
    # 2FA allowed for the user but never configured → the password alone must NOT
    # sign them in; they're told to set it up, and no session is issued.
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_mfa_allowed("alice", True)  # allowed, but no secret enrolled
    client = TestClient(server.app)

    r = client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 200
    assert r.json() == {"mfaSetupRequired": True, "username": "alice"}
    assert server.SESSION_COOKIE not in client.cookies
    assert client.get("/api/projects").status_code == 401  # still gated


def test_mfa_enroll_flow_signs_in_and_enables_2fa(gui):
    import pyotp
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_mfa_allowed("alice", True)
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})

    begin = client.post("/auth/mfa/enroll/begin")
    assert begin.status_code == 200
    secret = begin.json()["secret"]
    assert begin.json()["otpauthUri"].startswith("otpauth://") and begin.json()["qrSvg"]

    # A wrong code doesn't enrol or sign in.
    assert client.post("/auth/mfa/enroll/finish", json={"code": "000000"}).status_code == 400
    assert store.get_user("alice").mfa_enabled is False
    assert server.SESSION_COOKIE not in client.cookies

    fin = client.post("/auth/mfa/enroll/finish", json={"code": pyotp.TOTP(secret).now()})
    assert fin.status_code == 200
    body = fin.json()
    assert body["username"] == "alice" and body["mfaEnabled"] is True
    assert len(body["recoveryCodes"]) == 10
    assert server.SESSION_COOKIE in client.cookies
    assert store.get_user("alice").mfa_enabled is True
    assert client.get("/api/projects").status_code == 200  # now signed in


def test_mfa_enroll_endpoints_require_the_pending_cookie(gui):
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_mfa_allowed("alice", True)
    client = TestClient(server.app)  # never did the password step
    assert client.post("/auth/mfa/enroll/begin").status_code == 401
    assert client.post("/auth/mfa/enroll/finish", json={"code": "000000"}).status_code == 401


def test_mfa_enroll_denied_once_already_enrolled(gui):
    # An already-enrolled user goes through the code step, not the setup step.
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    store.set_mfa_allowed("alice", True)
    import app.services.mfa as mfa
    store.set_totp_secret("alice", mfa.new_secret())
    client = TestClient(server.app)
    r = client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert r.json() == {"mfaRequired": True, "username": "alice"}  # not setup-required
    # The enroll endpoints refuse when setup isn't required.
    assert client.post("/auth/mfa/enroll/begin").status_code == 401


def test_proxy_rejects_dot_segments_escaping_the_api_prefix(gui):
    """httpx resolves dot segments when merging with the base URL, so "/api/../x" would
    leave the /api prefix and reach a backend route WITH the proxy-auth header attached.
    The proxy must reject traversal before forwarding."""
    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    client = TestClient(server.app)
    assert client.post("/auth/login", json={"username": "alice", "password": "pw"}).status_code == 200

    # Percent-encoded traversal is the real vector: an HTTP client normalises a literal
    # "/api/../x" away, but "%2e%2e" survives the wire and Starlette decodes it INTO the
    # path param, so the check has to happen in the handler.
    for bad in ["/api/%2e%2e/openapi.json", "/api/..%2fopenapi.json", "/api/a/%2e%2e/%2e%2e/docs"]:
        resp = client.request("GET", bad)
        assert resp.status_code == 400, f"{bad} should be rejected, got {resp.status_code}"
        assert "stub" not in resp.text  # never reached the (stubbed) backend
    # A normal API path still proxies through.
    assert client.get("/api/projects").status_code == 200


def test_session_has_an_absolute_lifetime_cap(gui, monkeypatch):
    """The cookie is re-minted on every authenticated request, so without a hard cap a
    captured cookie could be kept alive forever by one request per idle window."""
    import json as _json
    import app.web_surface as web_surface
    from app.store.crypto import read_session, sign_session

    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    client = TestClient(server.app)
    assert client.post("/auth/login", json={"username": "alice", "password": "pw"}).status_code == 200
    assert client.get("/api/projects").status_code == 200  # fresh session works

    # Forge the same session with an "iat" older than the cap — everything else valid.
    raw = read_session(client.cookies["pmw_session"], 12 * 3600)
    payload = _json.loads(raw)
    payload["iat"] = int(time.time()) - web_surface.SESSION_MAX_LIFETIME_SECS - 60
    client.cookies.set("pmw_session", sign_session(_json.dumps(payload).encode()))

    assert client.get("/api/projects").status_code == 401, "aged-out session must be refused"
    assert client.get("/auth/session").json()["authenticated"] is False


def test_refreshing_a_session_does_not_restart_the_absolute_clock(gui):
    """Activity slides the idle window but must NOT reset the absolute lifetime."""
    import json as _json
    from app.store.crypto import read_session

    server, store = gui
    store.create_user("alice", "pw", is_admin=False)
    client = TestClient(server.app)
    client.post("/auth/login", json={"username": "alice", "password": "pw"})
    first = _json.loads(read_session(client.cookies["pmw_session"], 12 * 3600))["iat"]

    # Any authenticated call re-issues the cookie (that is the sliding window).
    client.get("/api/projects")
    after = _json.loads(read_session(client.cookies["pmw_session"], 12 * 3600))["iat"]
    assert after == first, "the original sign-in time must be carried through a refresh"
