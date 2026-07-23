"""LDAP / Active Directory authentication (search + bind).

The flow, per the admin-configured directory settings:

1. Bind to the server with a read-only *service account* (or anonymously).
2. Search the configured base DN for the login name, using a filter such as
   ``(uid={username})`` (OpenLDAP) or ``(sAMAccountName={username})`` (AD).
3. Re-bind as the found user's DN with the password they supplied. A successful
   bind proves the password; a failure means bad credentials.

Only used for the *main application* login — the admin panel stays local-only.
Configuration errors and unreachable servers raise :class:`LdapError` (surfaced by
the admin "Test" button); genuine bad credentials return ``None``.
"""

from __future__ import annotations

import contextlib
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ldap3 import ALL, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

# Keep logins snappy: a misconfigured or unreachable directory must fail fast
# rather than hang the sign-in request.
_CONNECT_TIMEOUT = 8


@dataclass
class LdapSettings:
    """Directory connection + search configuration (secrets already decrypted)."""

    enabled: bool = False
    server_uri: str = ""  # ldap://host:389 or ldaps://host:636
    start_tls: bool = False  # upgrade a plain ld:// connection with StartTLS
    verify_cert: bool = True
    ca_cert: str = ""  # optional CA certificate (PEM) to trust
    bind_dn: str = ""  # service-account DN (empty ⇒ anonymous search)
    bind_password: str = ""
    base_dn: str = ""
    user_filter: str = "(uid={username})"
    login_attr: str = "uid"  # attribute used as the canonical username
    email_attr: str = "mail"
    display_attr: str = "cn"


@dataclass
class LdapUser:
    """A directory user resolved by a successful bind."""

    username: str  # canonical name from the directory (login_attr)
    email: str = ""
    display_name: str = ""
    dn: str = ""


class LdapError(Exception):
    """A configuration or connectivity problem (not a bad-password result)."""


@contextlib.contextmanager
def _ca_file(ca_cert: str) -> Iterator[str | None]:
    """Materialise an inline CA certificate to a temp file for the TLS handshake."""
    if not ca_cert.strip():
        yield None
        return
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".pem", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(ca_cert)
        tmp.close()
        yield tmp.name
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _server(settings: LdapSettings, ca_path: str | None) -> Server:
    uri = settings.server_uri.strip()
    if not uri:
        raise LdapError("No LDAP server URI is configured.")
    use_ssl = uri.lower().startswith("ldaps://")
    tls = Tls(
        validate=ssl.CERT_REQUIRED if settings.verify_cert else ssl.CERT_NONE,
        ca_certs_file=ca_path,
    )
    return Server(uri, use_ssl=use_ssl, tls=tls, get_info=ALL, connect_timeout=_CONNECT_TIMEOUT)


def _open(server: Server, settings: LdapSettings, dn: str, password: str) -> Connection:
    """Open + bind a connection, applying StartTLS first when requested."""
    conn = Connection(
        server,
        user=dn or None,
        password=password or None,
        receive_timeout=_CONNECT_TIMEOUT,
        auto_bind=False,
    )
    # open() returns None on success and raises on a socket/TLS failure.
    try:
        conn.open()
    except LDAPException as exc:
        raise LdapError(f"Cannot connect to {settings.server_uri}: {exc}") from exc
    if settings.start_tls and not server.ssl:
        if not conn.start_tls():
            raise LdapError("StartTLS negotiation failed.")
    if not conn.bind():
        # For the service account this is a config error; for the user re-bind the
        # caller interprets a False bind as bad credentials before reaching here.
        raise LdapError(conn.result.get("description", "bind failed"))
    return conn


def authenticate(settings: LdapSettings, username: str, password: str) -> LdapUser | None:
    """Resolve + verify a user against the directory.

    Returns the directory user on success, ``None`` on bad credentials, and raises
    :class:`LdapError` for configuration/connectivity problems.
    """
    username = (username or "").strip()
    # An empty password would trigger an unauthenticated LDAP bind (which many
    # servers accept as anonymous) — always reject it outright.
    if not username or not password:
        return None
    if not settings.base_dn.strip():
        raise LdapError("No search base DN is configured.")

    with _ca_file(settings.ca_cert) as ca_path:
        server = _server(settings, ca_path)
        try:
            search_conn = _open(server, settings, settings.bind_dn, settings.bind_password)
        except LDAPException as exc:  # pragma: no cover - network/library errors
            raise LdapError(f"Service bind failed: {exc}") from exc

        try:
            matches = _search_users(search_conn, settings, username)
        finally:
            search_conn.unbind()

        # Exactly one entry must match; 0 (not found) or >1 (ambiguous) both fail.
        if len(matches) != 1:
            return None
        found = matches[0]

        # Re-bind as the user with the supplied password — the actual proof.
        try:
            user_conn = _open(server, settings, found.dn, password)
        except LdapError:
            return None  # bad password / user cannot bind
        except LDAPException:  # pragma: no cover
            return None
        user_conn.unbind()

    return found


def _search_users(search_conn, settings: LdapSettings, username: str) -> list[LdapUser]:
    """Search the base DN for the login name; return every matching entry."""
    if not settings.base_dn.strip():
        raise LdapError("No search base DN is configured.")
    flt = settings.user_filter.replace("{username}", escape_filter_chars(username))
    attrs = [
        a for a in {settings.login_attr, settings.email_attr, settings.display_attr} if a
    ]
    try:
        search_conn.search(settings.base_dn, flt, search_scope=SUBTREE, attributes=attrs)
    except LDAPException as exc:
        raise LdapError(f"Search failed: {exc}") from exc
    # A non-existent base DN surfaces here as a distinct, actionable error.
    if search_conn.result.get("result") == 32:  # noSuchObject
        raise LdapError(f"Base DN not found: {settings.base_dn!r}.")
    return [
        LdapUser(
            username=_attr(entry, settings.login_attr) or username,
            email=_attr(entry, settings.email_attr),
            display_name=_attr(entry, settings.display_attr),
            dn=entry.entry_dn,
        )
        for entry in search_conn.entries
    ]


def test_settings(
    settings: LdapSettings, test_username: str = "", test_password: str = ""
) -> dict:
    """Validate the configuration for the admin "Test connection" button.

    Always checks that the service bind + search machinery works; if a test user
    and password are supplied it also verifies a full user bind.
    """
    try:
        with _ca_file(settings.ca_cert) as ca_path:
            server = _server(settings, ca_path)
            search_conn = _open(server, settings, settings.bind_dn, settings.bind_password)

            if not test_username:
                search_conn.unbind()
                return {"ok": True, "error": None, "userOk": None, "matched": None}

            # Stage 2 — search (distinguishes "0 matches" from a real bad password).
            try:
                matches = _search_users(search_conn, settings, test_username)
            except LdapError as exc:
                return {"ok": True, "error": str(exc), "userOk": False, "matched": None}
            finally:
                search_conn.unbind()

            if len(matches) == 0:
                return {
                    "ok": True, "userOk": False, "matched": 0,
                    "error": "No entry matched the filter under the base DN — check the "
                             "Base DN, User filter and Login attribute.",
                }
            if len(matches) > 1:
                return {
                    "ok": True, "userOk": False, "matched": len(matches),
                    "error": f"The filter matched {len(matches)} entries (must be exactly "
                             "one) — make the User filter more specific.",
                }

            found = matches[0]
            if not test_password:
                return {"ok": True, "userOk": None, "matched": 1, "foundDN": found.dn, "error": None}

            # Stage 3 — bind as the found user with the test password.
            try:
                user_conn = _open(server, settings, found.dn, test_password)
                user_conn.unbind()
            except (LdapError, LDAPException):
                return {
                    "ok": True, "userOk": False, "matched": 1, "foundDN": found.dn,
                    "error": f"Found {found.dn}, but that password was rejected.",
                }
            return {
                "ok": True, "error": None, "userOk": True, "matched": 1,
                "user": {
                    "username": found.username, "email": found.email,
                    "displayName": found.display_name, "dn": found.dn,
                },
            }
    except (LdapError, LDAPException) as exc:
        return {"ok": False, "error": str(exc), "userOk": None}


def _attr(entry, name: str) -> str:
    if not name:
        return ""
    try:
        value = entry[name].value
    except (LDAPException, KeyError, TypeError):
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "")
