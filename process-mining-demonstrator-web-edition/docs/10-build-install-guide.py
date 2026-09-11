#!/usr/bin/env python3
"""Generate the self-contained HTML installation guide for the whole suite, covering
both deployment variants: native (./run.sh) and Docker Compose.

Facts (ports, commands, defaults, paths) are taken from run.sh, docker-compose.yml,
backend/app/config.py and the README — update this builder when they change.
Run:  python3 docs/build-install-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "10-Installation-Guide.html"
_BUILDER = pathlib.Path(__file__).name

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon, so the
# browser tab shows the suite's icon while the page stays fully self-contained.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each chapter: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
STEPS = [
    (
        "What you are installing",
        "The suite is <b>one code base with five surfaces</b>, each on its own port. A single "
        "start command brings them all up — whichever variant you choose:",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Surface</th><th>Who</th><th>Native (run.sh)</th><th>Docker host port</th></tr>
        <tr><td>Main application</td><td>all users</td><td>8080 / 8443</td><td>18080 / 18443</td></tr>
        <tr><td>Admin interface</td><td>administrators</td><td>8090 / 8453</td><td>18090 / 18453</td></tr>
        <tr><td>Integration console</td><td>power&nbsp;/&nbsp;dev&nbsp;/&nbsp;admin</td><td>8100 / 8463</td><td>18100 / 18463</td></tr>
        <tr><td>Actions surface</td><td>dev&nbsp;/&nbsp;admin</td><td>8110 / 8473</td><td>18110 / 18473</td></tr>
        <tr><td>Compute backend</td><td>internal only</td><td>8000 (loopback, TLS)</td><td>inside the container</td></tr>
      </table>
      <p class="cap">Second port of each pair = HTTPS, active once TLS is enabled in the admin.
        The Docker column shows the <b>defaults</b> — host ports mapped at +10000 so they don't
        clash with local services; any free host port can be mapped instead (see Variant B).
        The compute backend is never exposed to the browser — the GUI server proxies to it.</p>
    </div>""",
        None,
        '<span class="k">Which variant?</span> <b>run.sh</b> for development or a machine you '
        "manage directly; <b>Docker Compose</b> for a self-contained, restartable deployment "
        "with one folder of persistent state.",
    ),
    (
        "Prerequisites",
        "The two variants need different tooling on the host:",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Requirement</th><th>Native (run.sh)</th><th>Docker</th></tr>
        <tr><td>Python</td><td>3.13 or 3.14 (3.11+ works)</td><td>— (image pins 3.13)</td></tr>
        <tr><td>Node.js</td><td>20+ (only to build the SPA)</td><td>— (built in a Node stage)</td></tr>
        <tr><td>Docker + Compose</td><td>—</td><td>Compose ≥ 2.22 for <code>watch</code></td></tr>
        <tr><td>Exasol database</td><td colspan="2">any reachable instance (the app's data source)</td></tr>
        <tr><td>LLM endpoint (optional)</td><td colspan="2">any OpenAI-compatible URL — for the AI report</td></tr>
      </table>
    </div>""",
        None,
        None,
    ),
    (
        "Variant A — native, with run.sh",
        "Three commands from a fresh checkout: create the Python environment, build the "
        "frontend once, start everything.",
        """<div class="mock">
      <pre class="calc"># 1. Python environment + backend dependencies (python3.14 works too)
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Build the frontend SPA (installs npm dependencies on first run)
./run.sh --build

# 3. Start the suite — backend, GUI, admin, integration, actions
./run.sh</pre>
      <p class="cap">run.sh starts all five services and stops them together on Ctrl-C. On the
        next start the SPA is only rebuilt if missing.</p>
    </div>""",
        [
            "App → <code>http://127.0.0.1:8080</code> · Admin → <code>http://127.0.0.1:8090</code> · "
            "Integration → <code>http://127.0.0.1:8100</code>",
            "Frontend development with hot reload: <code>./run.sh --dev</code> (backend + admin + "
            "Vite dev server on :5173).",
            "Optional test dependencies: <code>.venv/bin/pip install -r requirements-dev.txt</code>.",
        ],
        '<span class="k">Custom ports.</span> Override with environment variables before '
        "starting: <code>PMW_FRONTEND_PORT</code>, <code>PMW_ADMIN_PORT</code>, "
        "<code>PMW_BACKEND_PORT</code>, <code>PMW_INTEGRATION_PORT</code>, "
        "<code>PMW_ACTIONS_PORT</code> (and the matching <code>…_HTTPS_PORT</code> variants).",
    ),
    (
        "Variant B — Docker Compose",
        "One command builds the image (SPA in a Node stage, Python services in a slim runtime) "
        "and starts the container with all surfaces:",
        """<div class="mock">
      <pre class="calc"># optional but recommended BEFORE the first start:
#   edit docker-compose.yml and set the bootstrap admin password
#   PMW_DEFAULT_ADMIN_PASSWORD: "your-strong-password"

docker compose up -d --build</pre>
      <p class="cap">App → <code>http://localhost:18080</code> · Admin →
        <code>http://localhost:18090</code> · Integration → <code>http://localhost:18100</code> ·
        Actions → <code>http://localhost:18110</code> (host ports are the container ports
        +10000).</p>
    </div>""",
        [
            "The container runs the same <code>run.sh</code> under <code>tini</code> and restarts "
            "automatically (<code>restart: unless-stopped</code>).",
            "The bootstrap password env applies <b>only while the security database is empty</b> — "
            "set it before the very first <code>up</code>.",
            "Auto-rebuild during development: <code>docker compose watch</code> (or "
            "<code>up --watch</code>) rebuilds the image when sources change; Docker's layer "
            "cache keeps unchanged parts free.",
        ],
        '<span class="k">Pick your own ports.</span> The +10000 mapping is only the default. '
        "Map <b>any free host port</b> to the container ports by editing the <code>ports:</code> "
        "entries in <code>docker-compose.yml</code> — the left-hand side is the host port, e.g. "
        "<code>\"80:8080\"</code> serves the app on plain port 80. The container ports on the "
        "right stay as they are. One caveat: never map to host port <b>10080</b> — "
        "browsers block it as a restricted port.",
    ),
    (
        "First sign-in",
        "Open the <b>admin interface</b> first. A fresh installation bootstraps one "
        "administrator account:",
        """<div class="mock">
      <pre class="calc">username:  Administrator
password:  Administrator          (unless overridden via
                                   PMW_DEFAULT_ADMIN_USER / _PASSWORD)</pre>
      <p class="cap">Change this password immediately — admin → Users. Then create your users,
        define database connections (admin → Connections) and assign them; users sign in to the
        main app with their own accounts.</p>
    </div>""",
        [
            "A <b>Demo Mode</b> banner on the sign-in panel means no license is installed yet — "
            "the suite runs with the demo allowance until a license file is uploaded in the "
            "admin's App Control section.",
            "The Integration console and Actions surface are role-gated (and Actions stays "
            "disabled until an admin switches it on in the Actions tab).",
        ],
        None,
    ),
    (
        "Where your data lives",
        "Everything the suite must keep is written to <b>one directory</b> — the same layout in "
        "both variants:",
        """<div class="mock">
      <pre class="calc">native:  ./data                (override with PMW_DATA_DIR)
docker:  ./data  ⇄  /app/data  (bind mount in docker-compose.yml)

data/
  settings.sqlite3    per-user app settings
  security.sqlite3    users, roles, connections, norms, licenses
  logs.sqlite3        backend / admin logs
  secret.key          encryption key for stored secrets
  certs/              TLS certificates managed in the admin</pre>
      <p class="cap">Back up the <b>data</b> directory and you have backed up the installation —
        users, connections, certificates and settings. (Scheduled backups can also be configured
        in the admin.)</p>
    </div>""",
        None,
        '<span class="k">Keep secret.key with its databases.</span> Stored secrets (connection '
        "passwords, LLM keys) are encrypted with it — a database restored without its matching "
        "key cannot decrypt them.",
    ),
    (
        "Enabling HTTPS",
        "Both variants start on plain HTTP. TLS is switched on centrally in the <b>admin "
        "interface</b> (TLS tab): upload or generate a certificate, choose the TLS mode, and "
        "every surface follows the same plan — the HTTPS ports (8443/8453/8463/8473, or their "
        "+2000 Docker mappings) become active, no restart of individual services needed.",
        None,
        [
            "The internal GUI → backend hop is always TLS-encrypted with an internal "
            "self-signed certificate, independent of the public-facing mode.",
            "The admin, integration and actions surfaces follow the same TLS mode and active "
            "certificate as the main app.",
        ],
        None,
    ),
    (
        "Updating",
        "Updates are the install commands again — state in <code>data/</code> is untouched:",
        """<div class="mock">
      <pre class="calc"># native
git pull
.venv/bin/pip install -r requirements.txt   # in case dependencies changed
./run.sh --build                            # rebuild the SPA
./run.sh

# docker
git pull
docker compose up -d --build                # rebuilds only changed layers</pre>
    </div>""",
        None,
        None,
    ),
]

BEYOND = [
    "<b>The browser only ever talks to the GUI server</b> — the compute backend can even run "
    "on a separate host close to the database (<code>PMW_BACKEND_URL</code>).",
    "<b>Useful env vars</b>: <code>PMW_DATA_DIR</code>, <code>PMW_QUERY_TIMEOUT</code>, "
    "<code>PMW_DEFAULT_ADMIN_USER</code> / <code>PMW_DEFAULT_ADMIN_PASSWORD</code>, and the "
    "port overrides listed in Variant A.",
    "<b>Uninstalling</b> is deleting the checkout (and the container/image for Docker) — all "
    "state is in <code>data/</code>, nothing is installed system-wide.",
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
.hero p{margin:0;max-width:640px;color:rgba(255,255,255,.92);font-size:16px}
.lead{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 22px;
  margin:0 0 30px;color:var(--soft)}
.lead b{color:var(--ink)}
.lead code, .step ul li code, .cap code{background:var(--bg);border-radius:4px;padding:0 5px;
  font-size:13px}
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
.tip code{background:rgba(58,109,240,.10);border-radius:4px;padding:0 4px;font-size:13px}
.beyond{background:var(--warnbg);border:1px solid #f0d9b8;border-left:4px solid var(--warnbar);
  color:var(--warnink);border-radius:14px;padding:20px 22px;margin:34px 0 0}
.beyond h2{margin:0 0 8px;font-size:19px;color:#7a4d13}
.beyond ul{margin:8px 0 0;padding-left:20px}
.beyond li{margin:3px 0}
.beyond code{background:rgba(0,0,0,.06);border-radius:4px;padding:0 4px;font-size:13px}
.beyond .note{margin-top:12px;font-size:14.5px}
footer{color:var(--soft);font-size:13px;text-align:center;margin-top:34px}
/* Mock illustrations */
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.tbl{border-collapse:collapse;font-size:13px;width:100%}
.tbl th{color:var(--soft);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;
  text-align:left;padding:4px 12px 6px 0;border-bottom:2px solid var(--line)}
.tbl td{padding:5px 12px 5px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.tbl td code{background:var(--bg);border-radius:4px;padding:0 4px;font-size:12px}
.calc{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px;
  margin:0;font:12.5px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;
  overflow-x:auto;white-space:pre}
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
<title>10 - Installation Guide</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Suite · Installation</span>
  <h1>Installing the Process Mining Suite</h1>
  <p>One code base, five surfaces, two ways to run it: natively with <b>./run.sh</b> or as a
     container with <b>Docker Compose</b>. This guide takes a fresh machine to a running,
     signed-in suite — and tells you where your data lives.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    Both variants run the <b>same services</b> and keep their state in the <b>same
    data directory</b> — the choice is purely operational. Native gives you direct
    control and hot-reload development; Docker gives you an isolated, restartable
    deployment where host ports default to <b>+10000</b> (app on <code>18080</code>
    instead of <code>8080</code>) — and any free host port can be mapped instead.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Rule of thumb: if you can type <code>docker compose up -d --build</code>,
      the Docker variant is the fastest path from zero to a running suite.</p>
  </div>

  <footer>Process Mining Demonstrator · Suite — Installation Guide (run.sh &amp; Docker Compose)</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
