"""SSRF guard for user-supplied outbound URLs (the configurable LLM server).

The app deliberately connects to an LLM endpoint that an admin / power user
configures, which is very commonly a *local or internal* host (Ollama, LM Studio,
an internal vLLM), so loopback/private targets are **allowed by default**. What is
*always* refused — regardless of settings — is the actual SSRF danger: non-HTTP(S)
schemes and link-local / cloud-metadata (169.254.169.254), multicast, reserved and
unspecified addresses, which are never a real LLM server.

For hardened / cloud deployments where the LLM is always external, set
``PMW_BLOCK_PRIVATE_LLM_HOSTS=1`` to also refuse loopback/private targets.

The host is resolved and *every* address it maps to is checked. Crucially, the
outbound connection is then **pinned to the vetted IP** (see ``safe_async_client``)
rather than re-resolving the hostname, so a DNS-rebind attack — pass the check with
a benign IP, then flip DNS to 169.254.169.254 for the actual connect — cannot slip
through the check-then-connect gap.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit

import httpx


class UrlNotAllowed(ValueError):
    """Raised when an outbound URL is refused by the SSRF guard."""


def _block_private() -> bool:
    """Opt-in hardening: also refuse loopback/private LLM targets. Off by default
    because local/internal LLM servers are a primary, legitimate use case."""
    return os.environ.get("PMW_BLOCK_PRIVATE_LLM_HOSTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _classify(ip, block_private: bool) -> str | None:
    """Return a human reason if this address is disallowed, else None."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:  # unwrap ::ffff:a.b.c.d so v4 rules apply
        ip = mapped
    # Loopback (127/8, ::1) is a first-class local-LLM case — checked first so the
    # IPv6 ::1 isn't swept up by the reserved-range block below. Allowed by default.
    if ip.is_loopback:
        return "a loopback address" if block_private else None
    # Always blocked — never a legitimate LLM host, and the crown-jewel SSRF target.
    if ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return "a link-local/metadata, multicast or reserved address"
    # Private (RFC1918) — allowed by default, blocked only under hardening.
    if block_private and ip.is_private:
        return "a private address"
    return None


def resolve_safe(url: str) -> tuple[str, str]:
    """Validate an outbound URL and return ``(host, vetted_ip)``.

    Every address the host resolves to is checked; if any is disallowed the whole
    URL is refused (a split-horizon host that also maps to a bad address can't be
    used). The returned IP is the address the caller should actually connect to, so
    the connection uses the exact address that was vetted (no re-resolution).
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https"):
        raise UrlNotAllowed("Only http:// and https:// URLs are allowed.")
    host = parts.hostname
    if not host:
        raise UrlNotAllowed("The URL has no host.")

    block_private = _block_private()
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlNotAllowed(f"The host could not be resolved: {host}") from exc

    vetted: str | None = None
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _classify(ip, block_private)
        if reason is not None:
            raise UrlNotAllowed(f"The URL resolves to {reason} ({addr}); refused.")
        if vetted is None:
            vetted = addr
    if vetted is None:
        raise UrlNotAllowed(f"The host could not be resolved: {host}")
    return host, vetted


def assert_safe_url(url: str) -> None:
    """Validate an outbound URL, raising UrlNotAllowed if it must not be fetched."""
    resolve_safe(url)


class _PinnedTransport(httpx.AsyncHTTPTransport):
    """An httpx transport that forces every request for ``host`` onto the already
    vetted ``ip``, while preserving the Host header and TLS SNI/cert hostname — so
    the connection cannot be re-pointed by a DNS rebind between check and connect."""

    def __init__(self, host: str, ip: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._host = host
        self._ip = ip

    @staticmethod
    def _canonical_host(value: str) -> str:
        """Fold a hostname to a single comparable form.

        `urlsplit().hostname` yields the ASCII/punycode form while
        `httpx.Request.url.host` yields the DECODED unicode form, so for an
        internationalised name ("xn--bcher-kva.example" vs "bücher.example") a plain
        equality test fails — the pin would silently not be applied and httpx would
        re-resolve the name at connect time, reopening exactly the DNS-rebinding
        window this transport exists to close.
        """
        text = (value or "").strip().rstrip(".").lower()
        try:
            return text.encode("idna").decode("ascii")
        except (UnicodeError, UnicodeDecodeError):
            return text  # already ASCII, or not encodable — compare as-is

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._canonical_host(request.url.host) == self._canonical_host(self._host):
            # Keep SNI + cert verification bound to the real hostname; the Host
            # header was already set from the original URL at build time.
            request.extensions = {**request.extensions, "sni_hostname": self._host}
            request.url = request.url.copy_with(host=self._ip)
        return await super().handle_async_request(request)


def safe_async_client(url: str, **client_kwargs) -> httpx.AsyncClient:
    """An ``httpx.AsyncClient`` that validates ``url`` now and pins all requests to
    it onto the vetted IP. Raises UrlNotAllowed if the URL is refused. Redirects are
    disabled so a 3xx can't bounce the client to an unvetted host."""
    host, ip = resolve_safe(url)
    client_kwargs.setdefault("follow_redirects", False)
    return httpx.AsyncClient(transport=_PinnedTransport(host, ip), **client_kwargs)
