"""SSRF guard for user-supplied LLM URLs (app.services.net_guard)."""

from __future__ import annotations

import pytest

from app.services.net_guard import UrlNotAllowed, assert_safe_url


def _blocked(url: str) -> bool:
    try:
        assert_safe_url(url)
        return False
    except UrlNotAllowed:
        return True


def test_blocks_cloud_metadata_and_link_local_always():
    assert _blocked("http://169.254.169.254/latest/meta-data/")
    assert _blocked("http://[fe80::1]/v1")


def test_blocks_non_http_schemes():
    for u in ("file:///etc/passwd", "gopher://x/", "ftp://host/", "//host/v1"):
        assert _blocked(u), u


def test_allows_loopback_and_private_by_default():
    # Local/internal LLM servers are a primary, legitimate use case.
    assert_safe_url("http://127.0.0.1:11434/v1")  # Ollama default — must not raise
    assert_safe_url("http://localhost:1234/v1")
    assert_safe_url("http://10.0.0.5:8000/v1")
    assert_safe_url("http://192.168.1.10/v1")


def test_allows_public_host():
    # A well-known public host resolves to routable addresses.
    assert_safe_url("https://api.openai.com/v1")  # does not raise


def test_private_blocked_only_with_optin(monkeypatch):
    assert not _blocked("http://127.0.0.1:11434/v1")  # default: allowed
    monkeypatch.setenv("PMW_BLOCK_PRIVATE_LLM_HOSTS", "1")
    assert _blocked("http://127.0.0.1:11434/v1")  # hardening opt-in: blocked
    # ...and metadata/link-local stays blocked either way.
    assert _blocked("http://169.254.169.254/")


def test_ipv4_mapped_ipv6_is_unwrapped():
    assert _blocked("http://[::ffff:169.254.169.254]/")


# ── DNS-rebind pinning (resolve_safe + safe_async_client) ─────────────────────

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from app.services.net_guard import _PinnedTransport, resolve_safe, safe_async_client


def test_resolve_safe_returns_ip_and_blocks_metadata():
    host, ip = resolve_safe("http://127.0.0.1:11434/v1")
    assert host == "127.0.0.1" and ip == "127.0.0.1"
    with pytest.raises(UrlNotAllowed):
        resolve_safe("http://169.254.169.254/latest/meta-data/")


def test_safe_async_client_refuses_blocked_url():
    with pytest.raises(UrlNotAllowed):
        safe_async_client("http://169.254.169.254/")


def test_pinned_transport_connects_to_vetted_ip_and_keeps_host():
    """The connection must land on the pinned IP while the Host header stays the
    original hostname — this is what closes the DNS-rebind window."""
    seen: dict[str, str] = {}

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["host"] = self.headers.get("Host", "")
            seen["client"] = self.client_address[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:

        async def go():
            # A rebind would resolve "evil.example" to a bad IP at connect time;
            # the pinned transport forces the vetted 127.0.0.1 instead.
            client = httpx.AsyncClient(
                transport=_PinnedTransport("evil.example", "127.0.0.1")
            )
            async with client:
                r = await client.get(f"http://evil.example:{port}/")
            return r

        r = asyncio.run(go())
        assert r.status_code == 200
        assert seen["client"] == "127.0.0.1"  # connected to the vetted IP
        assert seen["host"] == f"evil.example:{port}"  # Host preserved
    finally:
        srv.shutdown()
