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


# ── Schema provisioning affordance ────────────────────────────────────────────


def test_connection_editor_offers_schema_provisioning(dashboard):
    assert "function provisionSchema" in dashboard
    assert 'id="c_provisionResult"' in dashboard
    # The privilege advisory must be present (the app cannot grant these rights).
    assert "CREATE SCHEMA" in dashboard and "CREATE TABLE" in dashboard
    assert "database\n          administrator can grant" in dashboard or (
        "database administrator can grant" in " ".join(dashboard.split())
    )
    assert "PROJECTS, JOURNEYS, STEPS, METAS, NOTES" in dashboard


def test_login_page_has_directory_indicator(pages):
    html = pages.login_page()
    assert 'id="dirStatus"' in html
    assert "/api/directory-status" in html
    assert "Directory server" in html


def test_login_page_has_passkey_button(pages):
    html = pages.login_page()
    assert 'id="pkbtn"' in html
    assert "Sign with Passkey" in html
    assert "/login/passkey/begin" in html and "/login/passkey/finish" in html
    assert "navigator.credentials.get" in html


def test_dashboard_has_passkey_management_card(dashboard):
    assert "function loadAdminPasskeys" in dashboard
    assert "function addAdminPasskey" in dashboard
    assert "/api/passkey/register/begin" in dashboard
    assert "/api/passkey/register/finish" in dashboard
    assert 'id="pkAdminList"' in dashboard
    # The Users tab gates who may use passkeys.
    assert "togglePasskey" in dashboard
    assert "/api/access/passkey-all" in dashboard


def test_dashboard_has_admin_idle_logout(dashboard):
    assert 'id="adminIdleTimeout"' in dashboard
    assert "function setAdminIdle" in dashboard
    assert "_onIdleTimeout" in dashboard  # client-side auto-logout
    assert "/api/access/admin-idle-timeout" in dashboard
    assert "/login?inactivity=1" in dashboard  # idle logout lands on the notice


def test_dashboard_has_failed_login_lockout_control(dashboard):
    assert 'id="maxFailedLogins"' in dashboard
    assert "function saveMaxFailedLogins" in dashboard
    assert "/api/access/max-failed-logins" in dashboard
    assert "Unlock" in dashboard  # a locked account can be unlocked from the Users tab


def test_dashboard_has_logging_tab(dashboard):
    assert 'data-tab="logging"' in dashboard and 'id="tab-logging"' in dashboard
    assert "function loadLogs" in dashboard
    assert "function saveLogConfig" in dashboard  # max level + max file size
    assert 'id="logSeverityFilter"' in dashboard  # severity filter
    assert 'id="logSearch"' in dashboard  # regex/wildcard search
    assert "/api/logs/download" in dashboard
    # Paginated view: per-page dropdown (10/25/50/100) + pager.
    assert 'id="logPerPage"' in dashboard and "function setLogPerPage" in dashboard
    assert "function renderLogPager" in dashboard and "function logGoto" in dashboard
    assert '<option value="10">' in dashboard and '<option value="100">' in dashboard


def test_dashboard_escapes_single_quote_and_avoids_inline_onclick_injection(dashboard):
    # esc() must also escape ' (values sit in single-quoted JS strings inside
    # onclick attributes; without this an LDAP/connection name with a quote
    # becomes admin-context script execution).
    assert "&#39;" in dashboard  # esc() maps ' -> &#39;
    # The user/cert/connection actions read values from data-* via this.dataset,
    # never interpolate them into inline JS string literals.
    for safe in (
        "delUser(this.dataset.user)",
        "toggleAdmin(this.dataset.user",
        "deleteCert(this.dataset.id, this.dataset.name)",
        "editConnection(this.dataset.id)",
    ):
        assert safe in dashboard, safe
    for vulnerable in ("delUser('", "editConnection('", "deleteCert('"):
        assert vulnerable not in dashboard, vulnerable


def test_dashboard_has_backup_tab(dashboard):
    # Backup/restore moved from the app's left panel to its own admin tab; the manual
    # download and the automatic-backup scheduler share one combined "Backup" card.
    assert 'data-tab="backup"' in dashboard and 'id="tab-backup"' in dashboard
    assert "function downloadBackup" in dashboard and "function restoreBackup" in dashboard
    assert 'id="bkFile"' in dashboard  # restore file picker
    assert "/api/backup/export" in dashboard and "/api/backup/inspect" in dashboard


def test_dashboard_has_timezone_control(dashboard):
    # App Control carries the display-timezone selector, populated from the browser's
    # IANA list, and fmtDate honours the chosen zone.
    assert "<h2>Timezone</h2>" in dashboard and 'id="displayTz"' in dashboard
    assert "function saveDisplayTimezone" in dashboard and "supportedValuesOf" in dashboard
    assert "/api/access/timezone" in dashboard and "DISPLAY_TZ" in dashboard


def test_dashboard_backup_card_is_unified(dashboard):
    # One password/include-flags set drives both download and automatic backups; the
    # separate "Export" card is gone.
    assert "function downloadBackup" in dashboard and "function saveSchedule" in dashboard
    assert "function runBackupNow" in dashboard and 'id="schedFreq"' in dashboard
    assert 'id="schedPw"' in dashboard and "/api/backup/schedule" in dashboard
    assert 'id="bkExportPw"' not in dashboard  # the old Export card's own password is gone


def test_login_page_shows_inactivity_notice(pages):
    # Same label the app's LoginView shows; the idle auto-logout redirects here.
    plain = pages.login_page()
    assert "signed out due to inactivity" not in plain
    notice = pages.login_page(inactivity=True)
    assert "You were signed out due to inactivity." in notice
    assert "login-notice" in notice
    # An error takes precedence over the inactivity notice (mirrors the app).
    both = pages.login_page(error="Invalid credentials", inactivity=True)
    assert "signed out due to inactivity" not in both
    assert "Invalid credentials" in both


def test_login_page_uses_the_app_master_design(pages):
    html = pages.login_page()
    assert "login-splash" in html  # the centred card, like the app's LoginView
    assert "btn-prominent" in html  # full-width prominent Sign-in button
    assert "Sign in to continue" in html  # master subtitle
    # The master's exact field + button classes (identical sizing/layout).
    assert 'class="text-input"' in html
    assert "5px 8px" in html and "font-size: 12px" in html  # master field metrics


def test_login_page_title_is_two_lines(pages):
    html = pages.login_page()
    # Title spans two lines; only the title differs from the app master.
    assert ">Process Mining Demonstrator<" in html
    assert ">Administration<" in html
    assert html.count('class="t-title3"') == 2


def test_login_page_matches_master_behaviour(pages):
    html = pages.login_page()
    # Submit starts disabled and enables only once a username is entered (like the
    # app) — so no prefilled username, and the button ships with `disabled`.
    assert 'value="Administrator"' not in html  # fields start empty, as in the app
    assert 'id="signin" disabled' in html
    assert "btn.disabled = !u.value.trim()" in html


def test_dashboard_has_customize_login_section(dashboard):
    assert 'data-tab="customize"' in dashboard
    assert 'id="tab-customize"' in dashboard
    assert "Login Page" in dashboard
    assert 'name="loginBg"' in dashboard
    assert "saveLoginBg" in dashboard


def test_login_page_accepts_custom_background(pages):
    assert "background: #123456;" in pages.login_page(bg_css="#123456")
    assert "background: var(--l-grouped);" in pages.login_page()


def test_customize_preview_avoids_login_only_css_var(dashboard):
    # --l-grouped is defined only on the login page; referencing it in the
    # dashboard's Customize preview made the image `background` shorthand an
    # invalid (undefined-var) declaration, so the picked image never painted.
    assert "--l-grouped" not in dashboard
    assert 'id="lbg_preview"' in dashboard


def test_dashboard_has_admin_help_overlay(dashboard):
    # The "Administration" help menu structure is available on the admin page.
    assert 'id="helpOv"' in dashboard
    assert 'onclick="openHelp()"' in dashboard
    assert "const ADMIN_HELP" in dashboard
    assert "function renderHelp" in dashboard
    # Its sections mirror the admin tabs / the app's Administration help group.
    for title in [
        "Admin Interface",
        "TLS / SSL",
        "Users & Sign-in",
        "Database Connections",
        "Directory (LDAP)",
        "Logging",
        "Backup & Restore",
        "Customize",
        "License & Demo Mode",
    ]:
        assert title in dashboard
    # The nav buttons use the app's clean soft-accent active style (not the old
    # native-button "boxed" look).
    assert ".help-ov-nav button.sel" in dashboard
    assert "border: none; background: none" in dashboard
