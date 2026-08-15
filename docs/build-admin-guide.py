#!/usr/bin/env python3
"""Generate a self-contained HTML setup & operations guide for administrators.
Screenshots are embedded as base64 data URIs so the single .html file needs nothing else."""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "manual" / "screenshots"
OUT = ROOT / "docs" / "Administration-Quick-Start.html"


def data_uri(name: str) -> str:
    b = (SHOTS / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


STEPS = [
    (
        "admin-01-overview.png",
        "Sign in &amp; the dashboard",
        "Open the <b>Administration</b> interface in your browser (by default on port <b>8090</b>) and "
        "sign in with an administrator account. Only administrators can reach this site &mdash; a "
        "correct password on a non-admin account is refused with the same message as a wrong one. The "
        "dashboard opens on <b>App&nbsp;Control</b>, with every tab along the top.",
        "On first run a banner reminds you to change the default administrator password &mdash; do that "
        "on day one.",
    ),
    (
        "admin-02-app-control.png",
        "App Control &mdash; licence &amp; restart",
        "The <b>App Control</b> tab shows the licence status and, in Demo Mode, a one-time grace "
        "countdown. Upload a signed licence here. The <b>&#8635; Restart</b> button re-binds all "
        "browser surfaces at once &mdash; use it after a TLS change or after enabling/disabling a "
        "feature.",
        None,
    ),
    (
        "admin-03-tls-ssl.png",
        "TLS / SSL",
        "Choose how the site is served: <b>off</b> (HTTP), <b>optional</b> (HTTP + HTTPS) or "
        "<b>required</b> (HTTPS only). Generate a self-signed certificate or upload your own, then "
        "activate it. A single restart applies the mode and certificate to the app, admin, integration "
        "and Actions surfaces together.",
        "The admin interface follows the same TLS mode, so a bad certificate can lock you out &mdash; "
        "keep a way back in (e.g. the HTTP fallback) until you have verified the new one.",
    ),
    (
        "admin-04-users.png",
        "Users &amp; sign-in",
        "Add user accounts and grant roles: <b>Power user</b>, <b>Developer</b> and <b>Administrator</b> "
        "(an account with none is a standard user). Here you also control the global <b>require "
        "sign-in</b> switch, the <b>idle timeout</b>, the <b>failed-login lockout</b>, and per-account "
        "<b>passkeys</b> and <b>two-factor</b> (with master toggles and a force-enrolment option). A "
        "badge marks each account <b>local</b> or <b>LDAP</b>.",
        "Roles are never granted by the directory &mdash; every role is set explicitly here. Keep at "
        "least one <b>local administrator</b> as break-glass access.",
    ),
    (
        "admin-05-database-connections.png",
        "Database Connections",
        "Create the database connections your users will analyse: name, host, port, schema and "
        "credentials, plus an optional AI model server. <b>Assign</b> each connection to the users who "
        "may use it &mdash; a user only ever sees their assigned connections. <b>Test</b> checks the "
        "values before saving. You can also opt a connection into <b>pre-materialised transitions</b> "
        "for faster maps.",
        None,
    ),
    (
        "admin-06-directory-ldap.png",
        "Directory (LDAP / Active Directory)",
        "Optionally let the main app accept directory sign-ins via search&nbsp;+&nbsp;bind: set the "
        "server URI, service-account bind DN/password, base DN, user filter and attributes, then "
        "<b>test</b> a login. Directory users are created locally on first sign-in as plain accounts you "
        "then grant roles to. Two switches let you also allow directory sign-in to this admin interface, "
        "and show or hide the <b>Authentication Server</b> availability indicator on the login panels.",
        None,
    ),
    (
        "admin-07-logging.png",
        "Logging",
        "The <b>Logging</b> tab is a filterable audit trail: sign-ins, configuration changes, "
        "certificate and connection actions, backups and more, each tagged by operation so you can "
        "narrow to exactly what you need. The live log is kept in a database; older segments rotate to "
        "files.",
        None,
    ),
    (
        "admin-08-backup.png",
        "Backup &amp; restore",
        "Export an <b>encrypted backup</b> of the security store on demand, or schedule automatic "
        "backups on a cron expression with a retention count. Backups are password-protected; the same "
        "password restores them. Inspect a backup before restoring it.",
        "Enabling a schedule requires a password &mdash; it is never echoed back, so store it safely.",
    ),
    (
        "admin-09-customize.png",
        "Customize the login panels",
        "Set the look of every sign-in panel: a solid background colour or an uploaded image, shared by "
        "the app, admin, integration and Actions surfaces. The freely-editable version line (e.g. "
        "&ldquo;V0.95 &ndash; Milford Sound&rdquo;) also appears under the title.",
        None,
    ),
    (
        "admin-10-integration.png",
        "The other surfaces &amp; reporting",
        "Two more tabs turn optional surfaces on or off: <b>Integration</b> (the data-source console for "
        "developers) and <b>Actions</b> (the Action&nbsp;Designer, off by default). Both take effect "
        "after a restart. The <b>Reporting</b> tab configures the AI report per connection and project "
        "&mdash; its letterhead, logo and sections, and the analysis prompt.",
        "Enabling or disabling a surface only flips a flag; press <b>&#8635; Restart</b> on App Control "
        "to bind or release its listener.",
    ),
]

CHECKLIST = [
    "Change the default <b>administrator password</b> (banner on App Control).",
    "Choose a <b>TLS mode</b> and activate a certificate.",
    "Create at least one <b>database connection</b> and assign it to the right users.",
    "Keep one <b>local administrator</b> account as break-glass access.",
    "Set an <b>idle timeout</b> and a <b>failed-login lockout</b> that match your policy.",
    "Schedule <b>encrypted backups</b>.",
]

CSS = """
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --okbg:#eefaf1; --okbar:#2e9e5b; --okink:#1c5334;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:0 20px 72px}
header.hero{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;
  border-radius:0 0 26px 26px;padding:44px 20px 40px;margin-bottom:34px;
  box-shadow:0 12px 30px rgba(58,109,240,.25)}
.hero-inner{max-width:900px;margin:0 auto;padding:0 20px}
.chip{display:inline-block;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);
  padding:4px 12px;border-radius:999px;font-size:13px;font-weight:600;letter-spacing:.3px}
h1{font-size:30px;line-height:1.2;margin:14px 0 8px;font-weight:800}
.hero p{margin:0;max-width:660px;color:rgba(255,255,255,.92);font-size:16px}
.lead{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 22px;
  margin:0 0 30px;color:var(--soft)}
.lead b{color:var(--ink)}
.step{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 22px 8px;
  margin:0 0 22px;box-shadow:0 1px 2px rgba(20,30,50,.04)}
.step-head{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.num{flex:0 0 auto;width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  font-weight:800;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2))}
.step h2{font-size:20px;margin:0;font-weight:750}
.step p.body{margin:2px 0 16px}
.shot{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:12px;
  box-shadow:0 6px 18px rgba(20,30,50,.10);margin:0 0 16px}
.tip{background:var(--tipbg);border-left:4px solid var(--tipbar);color:var(--tipink);
  border-radius:8px;padding:10px 14px;margin:0 0 16px;font-size:14.5px}
.tip .k{font-weight:700;margin-right:6px}
.check{background:var(--okbg);border:1px solid #cdead7;border-left:4px solid var(--okbar);
  color:var(--okink);border-radius:14px;padding:20px 22px;margin:34px 0 0}
.check h2{margin:0 0 8px;font-size:19px;color:#1c5334}
.check ol{margin:8px 0 0;padding-left:22px}
.check li{margin:4px 0}
footer{color:var(--soft);font-size:13px;text-align:center;margin-top:34px}
@media (prefers-color-scheme:dark){
  :root{--bg:#14171c;--card:#1d2127;--ink:#e7eaee;--soft:#a3adba;--line:#2c333c;
    --tipbg:#182338;--tipink:#cdd9f5;--okbg:#132a1d;--okink:#bfe6cd}
}
@media print{
  body{background:#fff}
  header.hero{box-shadow:none;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .step,.lead,.check{break-inside:avoid;box-shadow:none}
  .shot{box-shadow:none}
}
"""


def render() -> str:
    steps_html = []
    for i, (img, title, body, tip) in enumerate(STEPS, start=1):
        tip_html = f'<div class="tip"><span class="k">Note</span>{tip}</div>' if tip else ""
        steps_html.append(
            f"""<section class="step">
  <div class="step-head"><div class="num">{i}</div><h2>{title}</h2></div>
  <p class="body">{body}</p>
  <img class="shot" alt="{html.escape(title)}" src="{data_uri(img)}">
  {tip_html}
</section>"""
        )
    checklist = "\n".join(f"<li>{c}</li>" for c in CHECKLIST)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Administration Quick-Start</title>
<style>{CSS}</style>
</head><body>
<header class="hero"><div class="hero-inner">
  <span class="chip">For administrators</span>
  <h1>Process Mining &mdash; Administration<br>Setup &amp; Operations Guide</h1>
  <p>A guided tour of the Administration interface, tab by tab, in roughly the order you would set up
     a new installation &mdash; users and roles, database connections, TLS, sign-in security, logging,
     backups and the optional surfaces.</p>
</div></header>
<div class="wrap">
  <div class="lead">The <b>Administration</b> site is where the whole installation is configured. It is
    a separate surface from the application, reachable only by administrators, and it controls the app,
    the Integration console and the Action&nbsp;Designer as well as itself.</div>
  {''.join(steps_html)}
  <div class="check">
    <h2>Day-one checklist</h2>
    <ol>{checklist}</ol>
  </div>
  <footer>Process Mining Demonstrator &mdash; Administration &middot; Setup &amp; operations guide</footer>
</div>
</body></html>"""


OUT.write_text(render(), encoding="utf-8")
print(f"WROTE {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
