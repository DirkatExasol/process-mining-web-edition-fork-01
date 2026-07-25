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


def test_blocks_loopback_and_private_by_default():
    assert _blocked("http://127.0.0.1:11434/v1")
    assert _blocked("http://localhost:8000/v1")
    assert _blocked("http://10.0.0.5:8000/v1")
    assert _blocked("http://192.168.1.10/v1")


def test_allows_public_host():
    # A well-known public host resolves to routable addresses.
    assert_safe_url("https://api.openai.com/v1")  # does not raise


def test_private_allowed_only_with_optin(monkeypatch):
    assert _blocked("http://127.0.0.1:11434/v1")  # default: blocked
    monkeypatch.setenv("PMW_ALLOW_PRIVATE_LLM_HOSTS", "1")
    assert_safe_url("http://127.0.0.1:11434/v1")  # opt-in: allowed
    # ...but metadata/link-local stays blocked even with the opt-in.
    assert _blocked("http://169.254.169.254/")


def test_ipv4_mapped_ipv6_is_unwrapped():
    assert _blocked("http://[::ffff:169.254.169.254]/")
