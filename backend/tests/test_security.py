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
