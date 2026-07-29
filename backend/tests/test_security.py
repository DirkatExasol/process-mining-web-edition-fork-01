"""Security-store and certificate tests — users, TLS config and cert handling.

Each test runs against an isolated temporary data directory so the developer's
real security database and key file are never touched.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def security(tmp_path, monkeypatch):
    """A fresh SecurityStore bound to a throwaway data dir + key file."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    # Reload config + crypto + security so they pick up the temp data dir.
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs as certs

    importlib.reload(certs)
    import app.store.security as security_mod

    importlib.reload(security_mod)
    # Isolate the log store too (the lockout path logs), so tests never touch the
    # developer's real data/logs.
    import app.store.logs as logs_mod

    importlib.reload(logs_mod)
    return security_mod


# ── Users ─────────────────────────────────────────────────────────────────────


def test_default_admin_is_seeded(security):
    store = security.store
    users = store.list_users()
    assert [u.username for u in users] == ["Administrator"]
    admin = users[0]
    assert admin.is_admin and admin.is_enabled
    assert store.default_admin_password_active is True


def test_authenticate_is_case_insensitive_and_checks_enabled(security):
    store = security.store
    assert store.authenticate("Administrator", "Administrator") is not None
    assert store.authenticate("administrator", "Administrator") is not None
    assert store.authenticate("Administrator", "wrong") is None

    store.create_user("alice", "pw", is_admin=False)
    assert store.authenticate("alice", "pw") is not None
    store.set_enabled("alice", False)
    assert store.authenticate("alice", "pw") is None  # disabled users cannot sign in


def test_duplicate_username_is_rejected(security):
    store = security.store
    store.create_user("bob", "pw", is_admin=False)
    with pytest.raises(ValueError):
        store.create_user("BOB", "pw2", is_admin=False)  # case-insensitive clash


def test_changing_admin_password_clears_default_flag(security):
    store = security.store
    assert store.default_admin_password_active is True
    store.set_password("Administrator", "newpass")
    assert store.default_admin_password_active is False
    assert store.authenticate("Administrator", "newpass") is not None


def test_last_admin_cannot_be_removed(security):
    store = security.store
    # Only one admin exists → cannot demote, disable, or delete it.
    with pytest.raises(ValueError):
        store.set_admin("Administrator", False)
    with pytest.raises(ValueError):
        store.set_enabled("Administrator", False)
    with pytest.raises(ValueError):
        store.delete_user("Administrator")


def test_second_admin_allows_demotion(security):
    store = security.store
    store.create_user("alice", "pw", is_admin=True)
    # Two admins → demoting the non-built-in one is allowed.
    store.set_admin("alice", False)
    assert store.get_user("alice").is_admin is False
    # The built-in Administrator is always protected from demotion.
    with pytest.raises(ValueError):
        store.set_admin("Administrator", False)


# ── TLS config & plan ─────────────────────────────────────────────────────────


def test_tls_mode_round_trips(security):
    store = security.store
    assert store.tls_mode == security.TLS_OFF
    store.set_tls_mode(security.TLS_REQUIRED)
    assert store.tls_mode == security.TLS_REQUIRED
    with pytest.raises(ValueError):
        store.set_tls_mode("bogus")


def test_tls_plan_reflects_mode_and_active_cert(security):
    store = security.store

    # off → HTTP only, regardless of certificate presence.
    store.set_tls_mode(security.TLS_OFF)
    plan = store.tls_plan()
    assert plan["http"] and not plan["https"]

    cert = store.generate_certificate(
        name="Test", common_name="localhost", sans=["127.0.0.1"], days=30, key_size=2048
    )

    # required + active cert → HTTPS only.
    store.set_tls_mode(security.TLS_REQUIRED)
    store.activate_certificate(cert.id)
    plan = store.tls_plan()
    assert plan["https"] and not plan["http"] and plan["hasActiveCert"]
    assert plan["certPath"] and plan["keyPath"]

    # optional + active cert → both listeners.
    store.set_tls_mode(security.TLS_OPTIONAL)
    plan = store.tls_plan()
    assert plan["http"] and plan["https"]

    # required but no active cert → fall back to HTTP so the app stays reachable.
    store.set_tls_mode(security.TLS_REQUIRED)
    store.delete_certificate(cert.id)
    plan = store.tls_plan()
    assert plan["http"] and not plan["https"] and not plan["hasActiveCert"]


# ── Certificate service ───────────────────────────────────────────────────────


def test_generate_self_signed_includes_cn_and_sans(security):
    certs = importlib.import_module("app.services.certs")
    cert_pem, key_pem = certs.generate_self_signed(
        common_name="pm.example.com", sans=["localhost", "127.0.0.1"], days=10
    )
    info = certs.validate_pair(cert_pem, key_pem)
    assert info.is_self_signed
    assert "pm.example.com" in info.sans
    assert "localhost" in info.sans
    assert "127.0.0.1" in info.sans


def test_validate_pair_rejects_mismatched_key(security):
    certs = importlib.import_module("app.services.certs")
    cert_a, _ = certs.generate_self_signed(common_name="a", sans=[], days=5)
    _, key_b = certs.generate_self_signed(common_name="b", sans=[], days=5)
    with pytest.raises(certs.CertError):
        certs.validate_pair(cert_a, key_b)


def test_generate_requires_common_name(security):
    certs = importlib.import_module("app.services.certs")
    with pytest.raises(certs.CertError):
        certs.generate_self_signed(common_name="  ", sans=[], days=5)


def test_uploaded_certificate_is_stored_and_downloadable(security):
    store = security.store
    certs = importlib.import_module("app.services.certs")
    cert_pem, key_pem = certs.generate_self_signed(
        common_name="upload.test", sans=[], days=5
    )
    cert = store.upload_certificate(name="Uploaded", cert_pem=cert_pem, key_pem=key_pem)
    assert store.certificate_pem(cert.id) == cert_pem
    # The private key is encrypted at rest, not stored verbatim.
    row = store._conn.execute(
        "SELECT key_enc FROM certificates WHERE id = ?", (cert.id,)
    ).fetchone()
    assert key_pem not in row["key_enc"]


# ── Password hashing ──────────────────────────────────────────────────────────


def test_password_hash_is_salted_and_verifiable(security):
    crypto = importlib.import_module("app.store.crypto")
    h1 = crypto.hash_password("secret")
    h2 = crypto.hash_password("secret")
    assert h1 != h2  # random salt per hash
    assert h1.startswith("scrypt$")
    assert crypto.verify_password("secret", h1)
    assert not crypto.verify_password("wrong", h1)


# ── Connections & per-user assignments ────────────────────────────────────────


def _make_conn(store, **overrides):
    data = {
        "name": "Prod",
        "host": "db.example.com",
        "port": 8563,
        "username": "svc",
        "schema": "MINING",
        "password": "s3cret",
        "llmURL": "https://llm.example.com/v1",
        "llmModel": "gpt-4o",
        "llmKey": "sk-abc",
        "assignments": ["alice"],
    }
    data.update(overrides)
    return store.upsert_connection(data)


def test_connection_secrets_are_encrypted_and_hidden_from_public(security):
    store = security.store
    conn = _make_conn(store)

    # admin_public exposes presence flags but never the secret values.
    pub = conn.admin_public()
    assert pub["hasPassword"] is True and pub["hasLLMKey"] is True
    assert "s3cret" not in str(pub) and "sk-abc" not in str(pub)

    # Stored columns are ciphertext, not plaintext.
    row = store._conn.execute(
        "SELECT password_enc, llm_key_enc FROM connections WHERE id = ?", (conn.id,)
    ).fetchone()
    assert "s3cret" not in (row["password_enc"] or "")
    assert "sk-abc" not in (row["llm_key_enc"] or "")

    # The backend can retrieve decrypted secrets when it needs to connect.
    withsecrets = store.get_connection(conn.id, with_secrets=True)
    assert withsecrets.password == "s3cret"
    assert withsecrets.llm_api_key == "sk-abc"


def test_connections_are_filtered_per_assigned_user(security):
    store = security.store
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])

    assert [c.id for c in store.connections_for_user("alice")] == [conn.id]
    assert store.connections_for_user("bob") == []
    assert store.user_can_use(conn.id, "alice") is True
    assert store.user_can_use(conn.id, "bob") is False

    # user_public strips assignments and every secret / flag.
    up = store.connections_for_user("alice")[0].user_public()
    assert up["hasLLM"] is True
    assert "assignments" not in up and "hasPassword" not in up

    # No user (sign-in disabled) sees every connection.
    assert [c.id for c in store.connections_for_user(None)] == [conn.id]
    assert store.user_can_use(conn.id, None) is True


def test_reassignment_and_password_preserving_update(security):
    store = security.store
    store.create_user("alice", "pw", is_admin=False)
    store.create_user("bob", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])

    store.set_assignments(conn.id, ["bob"])
    assert store.user_can_use(conn.id, "alice") is False
    assert store.user_can_use(conn.id, "bob") is True

    # Omitting the password key keeps the stored secret; "" clears it.
    store.upsert_connection({"id": conn.id, "name": "Prod", "assignments": ["bob"]})
    assert store.get_connection(conn.id, with_secrets=True).password == "s3cret"
    store.upsert_connection(
        {"id": conn.id, "name": "Prod", "password": "", "assignments": ["bob"]}
    )
    assert store.get_connection(conn.id, with_secrets=True).password == ""


def test_delete_connection_removes_assignments(security):
    store = security.store
    store.create_user("alice", "pw", is_admin=False)
    conn = _make_conn(store, assignments=["alice"])
    store.delete_connection(conn.id)
    assert store.get_connection(conn.id) is None
    assert store.connections_for_user("alice") == []
    rows = store._conn.execute(
        "SELECT COUNT(*) AS n FROM connection_assignments WHERE connection_id = ?",
        (conn.id,),
    ).fetchone()
    assert rows["n"] == 0


# ── LDAP / directory config + app authentication ──────────────────────────────


def test_ldap_config_hides_and_encrypts_bind_password(security):
    store = security.store
    store.set_ldap_config(
        {
            "enabled": True,
            "serverURI": "ldap://dir.example.com:389",
            "bindDN": "cn=svc,dc=example,dc=com",
            "bindPassword": "s3cret",
            "baseDN": "ou=people,dc=example,dc=com",
        }
    )
    pub = store.ldap_admin_public()
    assert pub["enabled"] is True and pub["hasBindPassword"] is True
    assert "s3cret" not in str(pub)  # never returned to the admin UI

    row = store._conn.execute("SELECT bind_password_enc FROM ldap_config WHERE id=1").fetchone()
    assert "s3cret" not in (row["bind_password_enc"] or "")  # ciphertext at rest
    assert store.ldap_settings().bind_password == "s3cret"  # decrypted for auth


def test_ldap_config_password_preserving_update(security):
    store = security.store
    store.set_ldap_config({"enabled": True, "bindPassword": "s3cret"})
    # Updating without the password keeps it; passing "" clears it.
    store.set_ldap_config({"enabled": True})
    assert store.ldap_settings().bind_password == "s3cret"
    store.set_ldap_config({"enabled": True, "bindPassword": ""})
    assert store.ldap_settings().bind_password == ""


def test_ldap_admin_login_flag_round_trips_and_requires_enabled(security):
    store = security.store
    # Default off, and never on unless the directory itself is enabled.
    assert store.ldap_admin_public()["adminLoginEnabled"] is False
    assert store.ldap_admin_login_enabled is False

    store.set_ldap_config({"enabled": True, "adminLoginEnabled": True, "serverURI": "ldap://x"})
    assert store.ldap_admin_public()["adminLoginEnabled"] is True
    assert store.ldap_admin_login_enabled is True

    # Disabling the directory disables admin sign-in even if the flag stays set.
    store.set_ldap_config({"enabled": False, "adminLoginEnabled": True})
    assert store.ldap_admin_login_enabled is False
    assert store.ldap_admin_public()["hasBindPassword"] is False


def test_provision_ldap_user_creates_then_refreshes(security):
    store = security.store
    u = store.provision_ldap_user("alice", email="alice@example.com", display_name="Alice A")
    assert u.auth_source == "ldap" and u.is_enabled and not u.is_admin
    assert u.email == "alice@example.com"

    # An admin promotes/keeps flags; a later login refreshes attrs but not the role.
    store.set_admin("alice", True)
    again = store.provision_ldap_user("alice", email="alice@corp.com", display_name="Alice A")
    assert again.email == "alice@corp.com" and again.is_admin is True


def test_admin_authenticate_rejects_ldap_users(security):
    """The local-only `authenticate` (used by the admin panel) never accepts a
    directory user — they have no local password."""
    store = security.store
    store.provision_ldap_user("alice")
    assert store.authenticate("alice", "anything") is None


def _enable_stub_ldap(store, monkeypatch, result):
    """Enable LDAP and stub the directory bind to return `result` (an LdapUser or None)."""
    store.set_ldap_config({"enabled": True, "serverURI": "ldap://x", "baseDN": "dc=x"})
    import app.services.ldap_auth as ldap_auth

    monkeypatch.setattr(ldap_auth, "authenticate", lambda settings, u, p: result)
    return ldap_auth


def test_authenticate_app_local_first_then_ldap(security, monkeypatch):
    store = security.store
    # A local account keeps working (break-glass) even with LDAP on.
    store.create_user("localguy", "pw", is_admin=False)
    from app.services.ldap_auth import LdapUser

    _enable_stub_ldap(store, monkeypatch, LdapUser(username="alice", email="a@x", display_name="Alice"))

    assert store.authenticate_app("localguy", "pw") is not None  # local path
    # A directory user is JIT-provisioned and signed in, as a plain user.
    alice = store.authenticate_app("alice", "dirpw")
    assert alice is not None and alice.auth_source == "ldap" and alice.is_admin is False
    assert store.get_user("alice") is not None  # persisted locally


def test_authenticate_app_refuses_ldap_takeover_of_local_account(security, monkeypatch):
    """A directory login whose canonical username collides with a LOCAL account
    must be refused — it must never inherit that account's role/assignments."""
    store = security.store
    from app.services.ldap_auth import LdapUser

    store.create_user("admin", "strong-local-pw", is_admin=True)  # break-glass local admin
    # The directory returns the same canonical username for a different person, who
    # binds with their own directory password (local password check fails for them).
    _enable_stub_ldap(
        store, monkeypatch, LdapUser(username="admin", email="e@x", display_name="Imposter")
    )
    assert store.authenticate_app("admin", "attacker-dir-pw") is None  # refused
    u = store.get_user("admin")
    # The local admin row is untouched — still local, still admin, still enabled.
    assert u.auth_source == "local" and u.is_admin and u.is_enabled
    # The legitimate local admin still signs in with the local password.
    assert store.authenticate_app("admin", "strong-local-pw") is not None


def test_authenticate_app_refuses_whitespace_padded_ldap_collision(security, monkeypatch):
    """A directory username that only differs by surrounding whitespace still trims
    onto a local account — the collision check must strip before comparing, so this
    is refused too (regression for the raw-name bypass)."""
    store = security.store
    from app.services.ldap_auth import LdapUser

    store.create_user("admin", "local-pw", is_admin=True)  # break-glass local admin
    _enable_stub_ldap(
        store, monkeypatch, LdapUser(username="admin ", email="e@x", display_name="Imposter")
    )
    assert store.authenticate_app("admin ", "attacker-dir-pw") is None  # refused
    u = store.get_user("admin")
    assert u.auth_source == "local" and u.is_admin and u.is_enabled
    assert store.get_user("admin ") is None  # no stray padded row was provisioned


def test_security_store_enables_busy_timeout(security):
    # A cross-process writer must retry, not fail a write immediately with SQLITE_BUSY.
    assert security.store._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_backup_schedule_roundtrip_and_password_secret(security):
    store = security.store
    d = store.backup_schedule()  # secure defaults
    assert d["enabled"] is False and d["hasPassword"] is False
    assert d["cron"] == "0 2 * * *" and d["retention"] == 30

    store.set_backup_schedule({
        "enabled": True, "cron": "0 3 * * 1", "retention": 7,
        "includePasswords": False, "password": "s3cret-backup",
    })
    d = store.backup_schedule()
    assert d["enabled"] and d["cron"] == "0 3 * * 1" and d["retention"] == 7
    assert d["includePasswords"] is False and d["hasPassword"] is True
    # The password is never in the public dict and is stored encrypted at rest.
    assert "password" not in d and "s3cret-backup" not in str(d)
    assert store.backup_schedule_password() == "s3cret-backup"
    assert store._get_config("backup_sched_password_enc") != "s3cret-backup"

    # Omitting the password keeps it; an empty string clears it.
    store.set_backup_schedule({"enabled": False})
    assert store.backup_schedule()["hasPassword"] is True
    assert store.backup_schedule()["enabled"] is False
    store.set_backup_schedule({"password": ""})
    assert store.backup_schedule()["hasPassword"] is False
    assert store.backup_schedule_password() == ""


def test_backup_schedule_status_roundtrip(security):
    store = security.store
    assert store.backup_schedule()["status"] is None
    store.set_backup_schedule_status({"at": "2026-07-28T02:00:00", "ok": True, "file": "x.json"})
    assert store.backup_schedule()["status"]["file"] == "x.json"


def test_display_timezone_roundtrip(security):
    store = security.store
    assert store.display_timezone == ""  # default: server-local
    store.set_display_timezone("Europe/Berlin")
    assert store.display_timezone == "Europe/Berlin"
    store.set_display_timezone("")  # back to server-local
    assert store.display_timezone == ""


def test_authenticate_app_rejects_when_ldap_denies(security, monkeypatch):
    store = security.store
    _enable_stub_ldap(store, monkeypatch, None)  # directory rejects
    assert store.authenticate_app("alice", "bad") is None
    assert store.get_user("alice") is None  # not provisioned on failure


def test_authenticate_app_honours_local_disable_of_ldap_user(security, monkeypatch):
    store = security.store
    from app.services.ldap_auth import LdapUser

    _enable_stub_ldap(store, monkeypatch, LdapUser(username="alice"))
    assert store.authenticate_app("alice", "dirpw") is not None
    store.set_enabled("alice", False)  # admin blocks the directory account locally
    assert store.authenticate_app("alice", "dirpw") is None


def test_authenticate_app_ldap_disabled_is_local_only(security, monkeypatch):
    store = security.store
    import app.services.ldap_auth as ldap_auth

    called = {"n": 0}

    def _should_not_run(settings, u, p):
        called["n"] += 1
        return None

    monkeypatch.setattr(ldap_auth, "authenticate", _should_not_run)
    # LDAP left disabled → the directory is never consulted.
    assert store.authenticate_app("alice", "pw") is None
    assert called["n"] == 0


def test_idle_timeout_config_round_trips(security):
    store = security.store
    assert store.idle_timeout_mins == 0  # disabled by default
    store.set_idle_timeout_mins(30)
    assert store.idle_timeout_mins == 30
    store.set_idle_timeout_mins(-5)  # negatives clamp to 0 (disabled)
    assert store.idle_timeout_mins == 0


def test_builtin_administrator_cannot_be_disabled_or_demoted(security):
    store = security.store
    store.create_user("alice", "pw", is_admin=True)  # a second admin exists
    # Even with another admin present, the built-in Administrator is protected.
    with pytest.raises(ValueError):
        store.set_enabled("Administrator", False)
    with pytest.raises(ValueError):
        store.set_admin("Administrator", False)
    with pytest.raises(ValueError):  # case-insensitive
        store.set_admin("administrator", False)
    with pytest.raises(ValueError):  # nor deleted
        store.delete_user("Administrator")
    admin = store.get_user("Administrator")
    assert admin.is_enabled and admin.is_admin  # unchanged


# ── Power role & connection ownership ─────────────────────────────────────────


def _owned_conn(store, owner, **overrides):
    data = {
        "name": "Owned",
        "host": "db",
        "port": 8563,
        "username": "svc",
        "schema": "S",
        "password": "s3cret",
        "owner": owner,
        "assignments": [owner],
    }
    data.update(overrides)
    return store.upsert_connection(data)


def test_set_power_toggles_role_and_is_public(security):
    store = security.store
    store.create_user("pat", "pw", is_admin=False)
    assert store.get_user("pat").is_power is False
    store.set_power("pat", True)
    pat = store.get_user("pat")
    assert pat.is_power is True and pat.public()["isPower"] is True
    store.set_power("PAT", False)  # case-insensitive
    assert store.get_user("pat").is_power is False
    with pytest.raises(ValueError):
        store.set_power("nobody", True)


def test_connections_owned_by_filters_on_owner(security):
    store = security.store
    store.create_user("pat", "pw", is_admin=False)
    store.create_user("quinn", "pw", is_admin=False)
    mine = _owned_conn(store, "pat", name="Mine")
    _owned_conn(store, "quinn", name="Theirs")
    owned = store.connections_owned_by("PAT")  # case-insensitive
    assert [c.id for c in owned] == [mine.id]
    # owner survives in the admin_public shape and is immutable across an edit.
    assert mine.admin_public()["owner"] == "pat"
    store.upsert_connection({"id": mine.id, "name": "Mine2", "owner": "quinn"})
    assert store.get_connection(mine.id).owner == "pat"


def test_can_manage_connection_enforces_ownership(security):
    store = security.store
    store.create_user("pat", "pw", is_admin=False)
    store.set_power("pat", True)
    store.create_user("quinn", "pw", is_admin=False)
    store.set_power("quinn", True)
    store.create_user("plain", "pw", is_admin=False)
    conn = _owned_conn(store, "pat")

    assert store.can_manage_connection(conn.id, "pat") is True
    assert store.can_manage_connection(conn.id, "quinn") is False  # not the owner
    assert store.can_manage_connection(conn.id, "plain") is False  # not a power user
    assert store.can_manage_connection(conn.id, "Administrator") is True  # admin
    # A disabled power owner loses management rights.
    store.set_enabled("pat", False)
    assert store.can_manage_connection(conn.id, "pat") is False


def test_admin_idle_timeout_round_trips_and_clamps(security):
    store = security.store
    assert store.admin_idle_timeout_mins == 0  # default: never
    store.set_admin_idle_timeout_mins(25)
    assert store.admin_idle_timeout_mins == 25
    # Independent of the app's idle timeout.
    store.set_idle_timeout_mins(5)
    assert store.admin_idle_timeout_mins == 25 and store.idle_timeout_mins == 5
    store.set_admin_idle_timeout_mins(-3)  # clamps to 0
    assert store.admin_idle_timeout_mins == 0


# ── failed-sign-in lockout ────────────────────────────────────────────────────


def test_lockout_disables_account_after_threshold(security):
    store = security.store
    store.create_user("u", "pw", is_admin=False)
    store.set_max_failed_logins(3)

    assert store.authenticate("u", "wrong") is None
    assert store.authenticate("u", "wrong") is None
    assert store.get_user("u").is_enabled is True  # not yet
    assert store.authenticate("u", "wrong") is None  # 3rd → lock

    u = store.get_user("u")
    assert u.is_enabled is False and u.login_locked is True
    assert store.authenticate("u", "pw") is None  # correct pw, still locked out
    assert "locked" in store.login_block_message("u").lower()


def test_lockout_counter_resets_on_success(security):
    store = security.store
    store.create_user("u", "pw", is_admin=False)
    store.set_max_failed_logins(3)
    store.authenticate("u", "wrong")
    store.authenticate("u", "wrong")
    assert store.authenticate("u", "pw") is not None  # success resets
    assert store.get_user("u").failed_logins == 0
    # A later single failure doesn't lock (counter was reset).
    store.authenticate("u", "wrong")
    assert store.get_user("u").is_enabled is True


def test_reenabling_clears_lockout(security):
    store = security.store
    store.create_user("u", "pw", is_admin=False)
    store.set_max_failed_logins(1)
    store.authenticate("u", "wrong")  # locked immediately
    assert store.get_user("u").login_locked is True
    store.set_enabled("u", True)  # admin re-enables → unlock
    u = store.get_user("u")
    assert u.is_enabled and not u.login_locked and u.failed_logins == 0
    assert store.authenticate("u", "pw") is not None


def test_builtin_administrator_is_never_auto_locked(security):
    """The sole break-glass account must not be lockable by an unauthenticated
    attacker (that would be a DoS); the per-IP throttle guards it instead."""
    store = security.store
    store.set_max_failed_logins(2)
    for _ in range(6):
        store.authenticate("Administrator", "x")
    admin = store.get_user("Administrator")
    assert admin.is_enabled is True and admin.login_locked is False
    # A non-built-in admin, by contrast, still locks normally.
    store.create_user("ops", "pw", is_admin=True)
    store.authenticate("ops", "x")
    store.authenticate("ops", "x")
    assert store.get_user("ops").is_enabled is False


def test_zero_threshold_never_locks(security):
    store = security.store
    store.create_user("u", "pw", is_admin=False)
    store.set_max_failed_logins(0)  # explicit off
    for _ in range(10):
        store.authenticate("u", "wrong")
    assert store.get_user("u").is_enabled is True


def test_default_lockout_is_three_when_unset(security):
    # Fresh store never sets max_failed_logins → secure default of 3, not off.
    store = security.store
    assert store.max_failed_logins == 3
    store.create_user("u", "pw", is_admin=False)
    assert store.authenticate("u", "wrong") is None
    assert store.authenticate("u", "wrong") is None
    assert store.get_user("u").is_enabled is True  # 2 failures: not yet
    assert store.authenticate("u", "wrong") is None  # 3rd → lock
    assert store.get_user("u").is_enabled is False


def test_authenticate_nonexistent_user_returns_none_without_error(security):
    # The dummy-hash path (anti-enumeration) must not raise or leak.
    assert security.store.authenticate("ghost", "whatever") is None
    assert security.store.login_block_message("ghost") is None  # no account → generic


def test_lockout_is_logged(security):
    import app.store.logs as logs_mod

    store = security.store
    store.create_user("u", "pw", is_admin=False)
    store.set_max_failed_logins(2)
    store.authenticate("u", "wrong")
    assert logs_mod.store.query(operation="login") == []  # not locked yet → no entry
    store.authenticate("u", "wrong")  # 2nd → lock

    entries = logs_mod.store.query(operation="login")
    assert entries and "locked" in entries[0]["message"].lower()
    assert "'u'" in entries[0]["message"] and entries[0]["severity"] == "WARN"


def test_ldap_user_local_failures_do_not_count_toward_lockout(security):
    """A directory user has no local password; local checks 'fail' by design and
    must not trip the lockout — they authenticate via LDAP separately."""
    store = security.store
    store.set_max_failed_logins(2)
    store.provision_ldap_user("dir.user", email="d@x", display_name="Dir")
    for _ in range(5):
        assert store.authenticate("dir.user", "anything") is None
    u = store.get_user("dir.user")
    assert u.is_enabled is True and u.failed_logins == 0  # never counted / locked


def test_session_epoch_bumps_and_reads(security):
    store = security.store
    store.create_user("alice", "pw", is_admin=False)
    assert store.session_epoch("alice") == 0
    store.bump_session_epoch("alice")
    assert store.session_epoch("alice") == 1
    store.bump_session_epoch("ALICE")  # case-insensitive, like other lookups
    assert store.session_epoch("alice") == 2
    assert store.get_user("alice").session_epoch == 2  # reflected on the User
    assert store.session_epoch("nobody") == 0  # unknown user never raises


def test_note_author_display_name_prefers_ldap_cn(security, monkeypatch):
    """Note badges show the login user, and an LDAP user's real name (cn)."""
    import app.api.features as features

    store = security.store
    store.create_user("localguy", "pw", is_admin=False)
    store.provision_ldap_user("jsmith", email="j@x.io", display_name="John Smith")
    monkeypatch.setattr(features, "security_store", store)

    assert features._note_display_name("jsmith") == "John Smith"  # LDAP → cn
    assert features._note_display_name("localguy") == "localguy"  # local → login user
    assert features._note_display_name("") == ""
    assert features._note_display_name("ghost") == "ghost"  # unknown → username

    # An LDAP user with no cn falls back to the username.
    store.provision_ldap_user("nocn", email="", display_name="")
    assert features._note_display_name("nocn") == "nocn"


# ── Login-page appearance (admin Customize tab) ───────────────────────────────


def test_login_appearance_default(security):
    store = security.store
    assert store.login_appearance() == {"type": "default", "color": "", "image": ""}


def test_login_appearance_color_roundtrip(security):
    store = security.store
    saved = store.set_login_appearance(type="color", color="#1A2b3C")
    assert saved == {"type": "color", "color": "#1A2b3C", "image": ""}
    assert store.login_appearance()["color"] == "#1A2b3C"


def test_login_appearance_image_roundtrip(security):
    store = security.store
    img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    saved = store.set_login_appearance(type="image", image=img)
    assert saved["type"] == "image"
    assert saved["image"] == img


def test_login_appearance_rejects_bad_input(security):
    store = security.store
    with pytest.raises(ValueError):
        store.set_login_appearance(type="color", color="blue")
    with pytest.raises(ValueError):
        store.set_login_appearance(type="color", color="#12")
    with pytest.raises(ValueError):
        store.set_login_appearance(type="bogus")
    with pytest.raises(ValueError):
        store.set_login_appearance(type="image", image="not-a-data-uri")
    with pytest.raises(ValueError):
        store.set_login_appearance(type="image", image="data:text/html;base64,AAAA")
    with pytest.raises(ValueError):  # oversized
        store.set_login_appearance(
            type="image", image="data:image/png;base64," + "A" * 4_000_001
        )
    # An image type with nothing ever uploaded is rejected too.
    with pytest.raises(ValueError):
        store.set_login_appearance(type="image")


def test_login_appearance_validates_non_active_fields(security):
    store = security.store
    # A garbage colour is rejected even when colour is not the active type, so no
    # unvalidated (CSS-unsafe) value can ever be persisted.
    with pytest.raises(ValueError):
        store.set_login_appearance(type="default", color="garbage")
    # A garbage image is rejected even under a different active type.
    with pytest.raises(ValueError):
        store.set_login_appearance(type="color", color="#000000", image="not-a-data-uri")
    # A CSS-breaking image payload (would escape url("…")) is rejected.
    with pytest.raises(ValueError):
        store.set_login_appearance(
            type="image", image='data:image/png;base64,abc"),url(http://evil'
        )


# ── Pre-materialised transitions: per-connection flag, token, status ──────────


def test_use_materialized_flag_persists_and_defaults_off(security):
    store = security.store
    off = _make_conn(store)
    assert off.use_materialized_transitions is False  # off by default
    assert off.admin_public()["useMaterializedTransitions"] is False

    on = _make_conn(store, name="Mat", useMaterializedTransitions=True)
    assert store.get_connection(on.id).use_materialized_transitions is True

    # Updating with the flag off flips it back (it's an updatable column).
    store.upsert_connection({"id": on.id, "name": "Mat", "useMaterializedTransitions": False})
    assert store.get_connection(on.id).use_materialized_transitions is False


def test_rebuild_token_is_per_connection(security):
    store = security.store
    a, b = "conn-a", "conn-b"
    assert store.rebuild_token_set(a) is False
    assert store.verify_rebuild_token(a, "anything") is False  # none set yet

    ta = store.generate_rebuild_token(a)
    assert ta and store.rebuild_token_set(a) is True
    assert store.verify_rebuild_token(a, ta) is True
    assert store.verify_rebuild_token(a, "wrong") is False
    assert store.verify_rebuild_token(a, "") is False
    # Scoped: connection A's token is NOT valid for connection B.
    assert store.verify_rebuild_token(b, ta) is False

    # Only the hash is stored — never the plaintext.
    row = store._conn.execute(
        "SELECT value FROM security_config WHERE key = ?", (f"rebuild_token:{a}",)
    ).fetchone()
    assert row is not None and ta not in row["value"]

    # Rotating A invalidates A's previous token; B is untouched.
    tb = store.generate_rebuild_token(b)
    ta2 = store.generate_rebuild_token(a)
    assert ta2 != ta
    assert store.verify_rebuild_token(a, ta) is False
    assert store.verify_rebuild_token(a, ta2) is True
    assert store.verify_rebuild_token(b, tb) is True

    # Revoking A clears only A.
    store.clear_rebuild_token(a)
    assert store.rebuild_token_set(a) is False
    assert store.rebuild_token_set(b) is True


def test_deleting_connection_clears_its_token_and_status(security):
    store = security.store
    conn = _make_conn(store)
    store.generate_rebuild_token(conn.id)
    store.set_materialization_status(conn.id, {"ok": True, "rows": 1})
    assert store.rebuild_token_set(conn.id) is True

    store.delete_connection(conn.id)
    assert store.rebuild_token_set(conn.id) is False
    assert store.materialization_status(conn.id) is None


def test_materialization_status_round_trips_per_connection(security):
    store = security.store
    assert store.materialization_status("c1") is None  # nothing recorded yet

    store.set_materialization_status(
        "c1", {"ok": True, "rows": 12345, "built_at": "2026-07-28T00:00:00+00:00", "error": None}
    )
    st = store.materialization_status("c1")
    assert st["ok"] is True and st["rows"] == 12345
    # Independent per connection.
    assert store.materialization_status("c2") is None
