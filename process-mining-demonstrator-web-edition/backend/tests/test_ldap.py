"""LDAP search+bind tests, driven by ldap3's in-memory MOCK_SYNC server.

No real directory is contacted: a fake connection factory is injected that loads a
handful of entries and validates binds against their ``userPassword`` attribute,
exactly like a real server would for the search+bind flow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from ldap3 import MOCK_SYNC, Connection, Server

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import ldap_auth  # noqa: E402

DIRECTORY = {
    "cn=svc,dc=example,dc=com": {
        "objectClass": ["inetOrgPerson"],
        "userPassword": "svcpw",
        "cn": "svc",
    },
    "uid=alice,ou=people,dc=example,dc=com": {
        "objectClass": ["inetOrgPerson"],
        "userPassword": "alicepw",
        "uid": "alice",
        "mail": "alice@example.com",
        "cn": "Alice Anders",
    },
    "uid=bob,ou=people,dc=example,dc=com": {
        "objectClass": ["inetOrgPerson"],
        "userPassword": "bobpw",
        "uid": "bob",
        "mail": "bob@example.com",
        "cn": "Bob Baker",
    },
}


@pytest.fixture
def mock_ldap(monkeypatch):
    """Point ldap_auth at an in-memory directory instead of a real server."""
    mock_server = Server("mock-server")

    def factory(server, user=None, password=None, **kwargs):
        conn = Connection(
            mock_server, user=user, password=password, client_strategy=MOCK_SYNC
        )
        for dn, attrs in DIRECTORY.items():
            conn.strategy.add_entry(dn, attrs)
        return conn

    monkeypatch.setattr(ldap_auth, "Connection", factory)
    return ldap_auth.LdapSettings(
        enabled=True,
        server_uri="ldap://mock:389",
        bind_dn="cn=svc,dc=example,dc=com",
        bind_password="svcpw",
        base_dn="ou=people,dc=example,dc=com",
        user_filter="(uid={username})",
        login_attr="uid",
        email_attr="mail",
        display_attr="cn",
    )


def test_valid_login_resolves_user(mock_ldap):
    user = ldap_auth.authenticate(mock_ldap, "alice", "alicepw")
    assert user is not None
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert user.display_name == "Alice Anders"
    assert user.dn == "uid=alice,ou=people,dc=example,dc=com"


def test_wrong_password_returns_none(mock_ldap):
    assert ldap_auth.authenticate(mock_ldap, "alice", "nope") is None


def test_unknown_user_returns_none(mock_ldap):
    assert ldap_auth.authenticate(mock_ldap, "carol", "whatever") is None


def test_empty_password_is_rejected_without_binding(mock_ldap):
    # An empty password must never reach the server (unauthenticated-bind guard).
    assert ldap_auth.authenticate(mock_ldap, "alice", "") is None


def test_filter_injection_is_escaped(mock_ldap):
    # A crafted username must not turn into an OR filter matching everyone.
    assert ldap_auth.authenticate(mock_ldap, "*)(uid=*", "alicepw") is None


def test_canonical_username_comes_from_directory(mock_ldap):
    # Logging in as "ALICE" resolves to the directory's canonical "alice".
    user = ldap_auth.authenticate(mock_ldap, "ALICE", "alicepw")
    # The mock matches case-insensitively on uid; the returned name is the stored one.
    assert user is not None and user.username == "alice"


def test_missing_base_dn_raises(mock_ldap):
    mock_ldap.base_dn = ""
    with pytest.raises(ldap_auth.LdapError):
        ldap_auth.authenticate(mock_ldap, "alice", "alicepw")


def test_test_settings_reports_service_and_user(mock_ldap):
    result = ldap_auth.test_settings(mock_ldap, "alice", "alicepw")
    assert result["ok"] is True and result["userOk"] is True
    assert result["user"]["username"] == "alice"

    bad = ldap_auth.test_settings(mock_ldap, "alice", "wrong")
    assert bad["ok"] is True and bad["userOk"] is False
