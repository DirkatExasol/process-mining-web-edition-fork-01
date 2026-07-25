"""SSRF guard for user-supplied outbound URLs (the configurable LLM server).

The app deliberately connects to an LLM endpoint that an admin / power user
configures, which is very commonly a *local or internal* host (Ollama, LM Studio,
an internal vLLM), so loopback/private targets are **allowed by default**. What is
*always* refused — regardless of settings — is the actual SSRF danger: non-HTTP(S)
schemes and link-local / cloud-metadata (169.254.169.254), multicast, reserved and
unspecified addresses, which are never a real LLM server.

For hardened / cloud deployments where the LLM is always external, set
``PMW_BLOCK_PRIVATE_LLM_HOSTS=1`` to also refuse loopback/private targets.

The host is resolved and *every* address it maps to is checked, so a hostname
that resolves to a blocked address (or a DNS-rebind attempt) is rejected too.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit


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


def assert_safe_url(url: str) -> None:
    """Validate an outbound URL, raising UrlNotAllowed if it must not be fetched."""
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

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _classify(ip, block_private)
        if reason is not None:
            raise UrlNotAllowed(
                f"The URL resolves to {reason} ({addr}); refused."
            )
