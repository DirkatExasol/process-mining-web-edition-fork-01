"""Structural guards for the server-rendered admin pages.

The admin interface (`admin/pages.py`) ships its UI as inline HTML/CSS/JS with no
build step and no DOM tests, so these cheap substring checks stop the affordances
added over time — the theme control, combined role badges, the LDAP admin-login
opt-in and the shared section border — from being silently dropped by an edit.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def pages(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs  # noqa: F401 — reloaded transitively by security

    import app.store.security as security_mod

    importlib.reload(security_mod)

    admin_dir = Path(config.PROJECT_ROOT) / "admin"
    sys.path.insert(0, str(admin_dir))
    for name in ("server", "pages"):
        sys.modules.pop(name, None)
    return importlib.import_module("pages")


@pytest.fixture
def dashboard(pages):
    return pages.dashboard_page("Administrator", 8090, 8453)


# ── Theme control (System / Light / Dark), analog to the main app ─────────────


def test_login_page_is_theme_aware(pages):
    html = pages.login_page()
    assert "pmw_admin_theme" in html  # early theme-boot script resolves before paint
    assert "[data-theme='dark']" in html  # dark palette override
    assert "color-scheme: light" in html  # light is the default


def test_dashboard_has_theme_control(dashboard):
    assert 'id="themeSeg"' in dashboard
    assert "function setTheme" in dashboard and "initTheme()" in dashboard
    assert "prefers-color-scheme: dark" in dashboard


# ── Role badges ───────────────────────────────────────────────────────────────


def test_dashboard_combined_role_badge_floats(dashboard):
    # An admin carries two roles in one gradient badge that floats between colours.
    assert "function roleBadge" in dashboard
    assert ".pill.combo" in dashboard
    assert "@keyframes pillFloat" in dashboard
    assert "prefers-reduced-motion" in dashboard  # animation opt-out


def test_dashboard_neutral_badge_is_visible_on_light(dashboard):
    # The 'user'/'local' pill uses a theme-aware fill (the old near-white tint was
    # invisible on the light card).
    assert ".pill.neutral" in dashboard
    assert "var(--fill2)" in dashboard


# ── Directory (LDAP) admin sign-in opt-in ─────────────────────────────────────


def test_dashboard_directory_admin_login_optin(dashboard):
    assert 'id="l_adminLogin"' in dashboard
    assert "adminLoginEnabled" in dashboard
    assert "this admin interface" in dashboard


def test_directory_grid_shares_a_bottom_border(dashboard):
    # The Server and Service-account columns terminate on one common border.
    assert "border-bottom:1px solid var(--border)" in dashboard
