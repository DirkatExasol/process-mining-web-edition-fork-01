#!/usr/bin/env python3
"""Generate the self-contained HTML overview of users & permissions: the three
cumulative roles (Regular / Power / Admin), the full capability matrix, and the
separate Developer grant.

Every illustration is a small CSS-drawn mock — no screenshots — so the single .html
file is fully self-contained. Facts mirror the in-app Help "Users & Permissions".
Run:  python3 docs/21-build-users-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "21-Users-and-Permissions.html"
_BUILDER = pathlib.Path(__file__).name

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# ── the capability matrix (mirrors the in-app Help table) ─────────────────────
# Each row: (capability, regular, power, admin) where a cell is "y" / "n" / free text.
MATRIX = [
    ("View process maps, charts & KPIs", "y", "y", "y"),
    ("Filters, saved presets & date window", "y", "y", "y"),
    ("Read & write notes and comments", "y", "y", "y"),
    ("Personal settings, layout & preference backup", "y", "y", "y"),
    ("Advanced views: Conformance, Happy Path, Simulation", "n", "y", "y"),
    ("Journey sampling (create / delete samples)", "n", "y", "y"),
    ("Create, manage & assign own DB connections", "n", "y", "y"),
    ("Provision schema & generate demo data", "n", "y", "y"),
    ("Integration console (data-source configuration)", "dev", "y", "y"),
    ("Actions / Action Builder (author node actions)", "dev", "n", "y"),
    ("Admin interface: users, TLS, LDAP, licensing, logging", "n", "n", "y"),
]


def _cell(v: str) -> str:
    if v == "y":
        return '<td class="y">✓</td>'
    if v == "n":
        return '<td class="n">—</td>'
    if v == "dev":
        return '<td class="d">Dev only</td>'
    return f"<td>{html.escape(v)}</td>"


def matrix_html() -> str:
    rows = "".join(
        f"<tr><td class='cap-c'>{html.escape(cap)}</td>{_cell(r)}{_cell(p)}{_cell(a)}</tr>"
        for cap, r, p, a in MATRIX
    )
    return (
        '<div class="mock"><div class="matrix-wrap"><table class="matrix">'
        "<tr><th>Capability</th><th>Regular</th><th>Power</th><th>Admin</th></tr>"
        f"{rows}</table></div>"
        '<p class="cap">“Dev only” = a Regular user needs the separate <b>Developer</b> grant '
        "(step 3). Power and Admin have those surfaces anyway.</p></div>"
    )


# Each step: (title, body_html, mock_html | None, bullets | None, tip_html | None).
STEPS = [
    (
        "Three roles that build on each other",
        "Every signed-in account carries one of three permission levels. They are "
        "<b>cumulative</b>: a Power user can do everything a Regular user can, plus more; an "
        "Administrator can do everything a Power user can, plus run the whole installation. A new "
        "account is a <b>Regular</b> user by default.",
        """<div class="mock"><div class="roles">
      <div class="role r1"><span class="rt">Regular</span><span class="rd">Explore: maps, charts,
        filters, presets, notes &amp; personal settings — on the connections assigned to them.</span></div>
      <div class="role r2"><span class="rt">Power <small>= Regular +</small></span><span class="rd">Own DB
        connections, schema provisioning, demo data, journey sampling and the advanced views.</span></div>
      <div class="role r3"><span class="rt">Admin <small>= Power +</small></span><span class="rd">The admin
        interface: all users &amp; roles, TLS, LDAP, licensing, logging, backups.</span></div>
    </div><p class="cap">Each level contains the one below it.</p></div>""",
        None,
        '<span class="k">Assigned connections.</span> A Regular user only sees the database '
        "connections an administrator (or a Power user) has assigned to them.",
    ),
    (
        "Who can do what — the capability matrix",
        "The full picture at a glance. Everything a Regular user can do, everyone can do; the "
        "Power column adds self-service data work and the advanced-analysis views; the Admin "
        "column adds the separate administration interface.",
        matrix_html(),
        None,
        '<span class="k">Why sampling is Power+.</span> Journey sampling rewrites the shared sample '
        "sets for <i>everyone</i> on the connection, so it is a Power/Admin action, not a personal one.",
    ),
    (
        "The Developer grant — a separate add-on",
        "<b>Developer</b> is an <b>independent checkbox</b> in the admin Users tab, not a level. It "
        "admits the account to the authoring surfaces regardless of whether it is Regular, Power or "
        "Admin: the <b>Integration console</b> (data sources), the <b>Action Builder</b>, and "
        "<b>creating Σ aggregates</b> for drill-down.",
        """<div class="mock">
      <div class="check"><span class="box">☑</span> Developer <span class="cap" style="margin:0 0 0 6px">
        — grants the authoring surfaces</span></div>
      <div class="row" style="gap:10px;margin-top:12px">
        <span class="surf">⚙ Integration console <small>:8100</small></span>
        <span class="surf">🔨 Action Builder <small>:8110</small></span>
        <span class="surf">Σ Create aggregates</span>
      </div>
      <p class="cap">A Regular user with only the Developer grant may enter these surfaces, but gains
        no other elevated power in the main app.</p></div>""",
        [
            "<b>Integration console</b> — configure the application’s data sources (developers, "
            "power users and admins).",
            "<b>Action Builder</b> — author the business-readable node actions (developers and "
            "admins only; an admin must first enable Actions).",
            "<b>Aggregates</b> — collapse connected steps into Σ super-steps for drill-down "
            "(see the Aggregates &amp; Drill-Down guide).",
        ],
        None,
    ),
    (
        "Where roles are granted",
        "All of this lives in the <b>admin interface → Users</b> tab: create local users, enable or "
        "disable access, and grant or revoke <b>Power</b>, <b>Admin</b> and <b>Developer</b> per "
        "account. Only <b>enabled</b> users can sign in.",
        """<div class="mock"><div class="utable">
      <div class="ur head"><span class="un">User</span><span class="uf">Enabled</span>
        <span class="uf">Power</span><span class="uf">Admin</span><span class="uf">Developer</span></div>
      <div class="ur"><span class="un">alice</span><span class="uf">☑</span><span class="uf">☑</span>
        <span class="uf">☐</span><span class="uf">☐</span></div>
      <div class="ur"><span class="un">bob</span><span class="uf">☑</span><span class="uf">☐</span>
        <span class="uf">☐</span><span class="uf">☑</span></div>
      <div class="ur"><span class="un">admin</span><span class="uf">☑</span><span class="uf">☑</span>
        <span class="uf">☑</span><span class="uf">☐</span></div>
    </div><p class="cap">alice is a Power user; bob is a Regular user with the Developer add-on;
      admin runs the installation.</p></div>""",
        None,
        '<span class="k">Roles need a signed-in identity.</span> If an admin turns off <b>“Require '
        "sign-in for the main application”</b>, the app runs with no user — so every Power/Admin "
        "feature is hidden and its API returns 403. Keep sign-in on to use them.",
    ),
]

BEYOND = [
    "<b>Default is Regular.</b> A brand-new account can explore, but nothing that changes shared "
    "data or the installation until it is granted Power, Admin or Developer.",
    "<b>Break-glass admin.</b> The built-in <b>Administrator</b> account always works as a recovery "
    "route (and is exempt from auto-lockout), even if the LDAP directory is later misconfigured.",
    "<b>Directory (LDAP) users too.</b> Both local and directory accounts can hold any role; the "
    "grants are applied in the same Users tab.",
    "<b>Power manages only its own connections.</b> A Power user administers the connections it "
    "created; an Administrator sees and manages every connection.",
]

CSS = """
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415;
  --good:#1e9e5a; --bad:#d4453b;
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
.step ul{margin:0 0 12px;padding-left:20px;color:var(--soft)}
.step ul li{margin:3px 0}
.tip{background:var(--tipbg);border-left:4px solid var(--tipbar);color:var(--tipink);
  border-radius:8px;padding:10px 14px;margin:0 0 16px;font-size:14.5px}
.tip b{color:var(--tipink)}
.tip .k{font-weight:700;margin-right:6px}
.beyond{background:var(--warnbg);border:1px solid #f0d9b8;border-left:4px solid var(--warnbar);
  color:var(--warnink);border-radius:14px;padding:20px 22px;margin:34px 0 0}
.beyond h2{margin:0 0 8px;font-size:19px;color:#7a4d13}
.beyond ul{margin:8px 0 0;padding-left:20px}
.beyond li{margin:3px 0}
.beyond .note{margin-top:12px;font-size:14.5px}
footer{color:var(--soft);font-size:13px;text-align:center;margin-top:34px}
/* Mock illustrations */
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
/* cumulative role cards */
.roles{display:flex;flex-direction:column;gap:8px}
.role{border:1px solid var(--line);border-radius:11px;padding:11px 14px;background:var(--card)}
.role .rt{display:block;font-weight:800;font-size:15px}
.role .rt small{font-weight:600;color:var(--soft);font-size:12px}
.role .rd{display:block;color:var(--soft);font-size:13px;margin-top:2px}
.role.r1{border-left:5px solid #8aa0c8}
.role.r2{border-left:5px solid var(--accent);margin-left:16px}
.role.r3{border-left:5px solid var(--accent2);margin-left:32px}
/* capability matrix */
.matrix-wrap{overflow-x:auto}
.matrix{border-collapse:collapse;width:100%;font-size:13.5px;min-width:520px}
.matrix th{text-align:center;font-size:12px;text-transform:uppercase;letter-spacing:.03em;
  color:var(--soft);padding:6px 10px;border-bottom:2px solid var(--line)}
.matrix th:first-child{text-align:left}
.matrix td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:center}
.matrix td.cap-c{text-align:left;color:var(--ink)}
.matrix td.y{color:var(--good);font-weight:800}
.matrix td.n{color:var(--soft)}
.matrix td.d{color:var(--accent);font-weight:700;font-size:12px}
.matrix tr:hover td{background:rgba(58,109,240,.04)}
/* developer grant */
.check{display:flex;align-items:center;font-weight:700}
.check .box{color:var(--accent);font-size:20px;margin-right:8px}
.surf{border:1px solid var(--line);border-radius:9px;padding:7px 12px;background:var(--card);
  font-weight:650;font-size:13.5px}
.surf small{color:var(--soft);font-weight:600;margin-left:5px}
/* users table */
.utable{border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13.5px}
.ur{display:flex;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line)}
.ur:last-child{border-bottom:0}
.ur.head{background:rgba(0,0,0,.02);font-weight:700;color:var(--soft);font-size:12px;
  text-transform:uppercase;letter-spacing:.03em}
.ur .un{flex:1;font-weight:650;color:var(--ink)}
.ur.head .un{font-weight:700}
.ur .uf{flex:0 0 74px;text-align:center;color:var(--accent);font-size:15px}
.ur.head .uf{color:var(--soft);font-size:12px}
@media (prefers-color-scheme:dark){
  :root{--bg:#14171c;--card:#1d2127;--ink:#e7eaee;--soft:#a3adba;--line:#2c333c;
    --tipbg:#182338;--tipink:#cdd9f5;--warnbg:#2a2213;--warnink:#e9d3ac}
}
@media print{
  body{background:#fff}
  header.hero{box-shadow:none;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .step,.lead,.beyond,.mock{break-inside:avoid;box-shadow:none}
}
"""


def render() -> str:
    steps_html = []
    for i, (title, body, mock, bullets, tip) in enumerate(STEPS, start=1):
        parts = [
            '<section class="step">',
            f'  <div class="step-head"><div class="num">{i}</div>'
            f"<h2>{html.escape(title)}</h2></div>",
            f'  <p class="body">{body}</p>',
        ]
        if mock:
            parts.append(f"  {mock}")
        if bullets:
            items = "".join(f"<li>{b}</li>" for b in bullets)
            parts.append(f"  <ul>{items}</ul>")
        if tip:
            parts.append(f'  <div class="tip">{tip}</div>')
        parts.append("</section>")
        steps_html.append("\n".join(parts))

    beyond_items = "\n".join(f"      <li>{b}</li>" for b in BEYOND)
    return f"""<!doctype html>
<!-- Generated documentation page — open this file in a WEB BROWSER.
     It is NOT a script; to rebuild it run:  python3 docs/{_BUILDER} -->
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>21 - Users & Permissions</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Administration · Guide</span>
  <h1>Users &amp; Permissions — who can do what</h1>
  <p>Three cumulative roles — Regular, Power and Admin — plus a separate Developer grant decide
     what each account may do, from exploring maps to running the whole installation. Here is the
     complete picture, with the capability matrix.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    Permissions come in two parts: a <b>level</b> (Regular ⊂ Power ⊂ Admin) that each account holds
    exactly one of, and an optional <b>Developer</b> grant that opens the authoring surfaces on top
    of any level. Everything is set in the admin <b>Users</b> tab, and every capability requires a
    signed-in identity.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Rule of thumb: <b>Regular</b> explores, <b>Power</b> prepares and analyses,
      <b>Admin</b> governs — and <b>Developer</b> builds the data sources, actions and aggregates.</p>
  </div>

  <footer>Process Mining Demonstrator · Administration — Users &amp; Permissions</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
