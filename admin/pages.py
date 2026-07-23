"""Server-rendered HTML for the administrative interface.

Self-contained: inline CSS and JS, no build step, dark theme matching the main
app. The dashboard fetches its data from the /api/* endpoints after load.
"""

from __future__ import annotations

import base64
import html

# Animated brand mark (a discovered process graph with a flowing event dot),
# shared by the sign-in page and the dashboard. Matches frontend/components/Logo.tsx.
_LOGO_SVG = """<svg class="pm-logo" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="pmBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3a9bff"/><stop offset="1" stop-color="#6b5cf0"/>
    </linearGradient>
    <linearGradient id="pmShine" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#fff" stop-opacity="0"/>
      <stop offset="0.5" stop-color="#fff" stop-opacity="0.5"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="pmClip"><rect x="2" y="2" width="44" height="44" rx="12"/></clipPath>
    <filter id="pmGlow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="1.2" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <g clip-path="url(#pmClip)">
    <rect x="2" y="2" width="44" height="44" rx="12" fill="url(#pmBg)"/>
    <rect x="-28" y="2" width="20" height="44" fill="url(#pmShine)" transform="skewX(-16)">
      <animate attributeName="x" values="-28;56" dur="4.2s" begin="0.5s" repeatCount="indefinite"/>
    </rect>
    <path d="M15 16 L33 16 L24 34 Z" fill="none" stroke="#fff" stroke-width="2.4"
          stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>
    <circle cx="15" cy="16" r="4.4" fill="none" stroke="#fff" stroke-width="1.5">
      <animate attributeName="r" values="4.4;9" dur="2.8s" repeatCount="indefinite"/>
      <animate attributeName="opacity" values="0.55;0" dur="2.8s" repeatCount="indefinite"/>
    </circle>
    <g fill="#fff">
      <circle cx="15" cy="16" r="4.4"/><circle cx="33" cy="16" r="4.4"/><circle cx="24" cy="34" r="4.4"/>
    </g>
    <circle r="2.2" fill="#eaf3ff" filter="url(#pmGlow)">
      <animateMotion dur="2.8s" repeatCount="indefinite" calcMode="linear" path="M15 16 L33 16 L24 34 Z"/>
    </circle>
  </g>
</svg>"""

# Static one-frame version for the browser-tab favicon (favicons don't animate).
_FAVICON_SVG = (
    '<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="b" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#3a9bff"/><stop offset="1" stop-color="#6b5cf0"/>'
    '</linearGradient></defs>'
    '<rect x="2" y="2" width="44" height="44" rx="12" fill="url(#b)"/>'
    '<path d="M15 16 L33 16 L24 34 Z" fill="none" stroke="#fff" stroke-width="2.6" '
    'stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>'
    '<g fill="#fff"><circle cx="15" cy="16" r="4.6"/><circle cx="33" cy="16" r="4.6"/>'
    '<circle cx="24" cy="34" r="4.6"/></g>'
    '<circle cx="24" cy="16" r="2.4" fill="#eaf3ff"/></svg>'
)
_FAVICON_LINK = (
    '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,'
    + base64.b64encode(_FAVICON_SVG.encode("utf-8")).decode("ascii")
    + '">'
)

_STYLE = """
:root {
  --bg: #0b0b0d; --panel: #16161a; --panel2: #1d1d22; --fill: rgba(120,120,128,.16);
  --fill2: rgba(120,120,128,.28); --border: rgba(120,120,128,.28); --border-soft: rgba(120,120,128,.16);
  --text: #f2f2f7; --muted: rgba(235,235,245,.6); --tertiary: rgba(235,235,245,.3);
  --accent: #0a84ff; --green: #32d74b; --red: #ff453a; --orange: #ff9f0a; --yellow: #ffd60a;
  --radius: 10px; --shadow: 0 8px 30px rgba(0,0,0,.5);
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: var(--font); font-size: 14px; }
a { color: var(--accent); }
button { font: inherit; cursor: pointer; }
h1 { font-size: 20px; margin: 0; }
h2 { font-size: 15px; margin: 0 0 12px; }
.wrap { max-width: 980px; margin: 0 auto; padding: 24px 20px 60px; }
.topbar { display: flex; align-items: center; gap: 12px; padding: 14px 20px; background: var(--panel);
  border-bottom: 1px solid var(--border-soft); position: sticky; top: 0; z-index: 10; }
.brand { display: flex; align-items: center; gap: 12px; }
.logo { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
  background: none; box-shadow: 0 2px 6px rgba(10,20,60,.35); }
.pm-logo { width: 100%; height: 100%; display: block; }
.brand .sub { font-size: 11px; color: var(--muted); }
.spacer { flex: 1; }
.card { background: var(--panel); border: 1px solid var(--border-soft); border-radius: var(--radius);
  padding: 18px; margin: 16px 0; }
.row { display: flex; align-items: center; gap: 10px; }
.col { display: flex; flex-direction: column; gap: 10px; }
.muted { color: var(--muted); }
.mono { font-family: var(--mono); font-size: 12px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 11px; color: var(--muted); }
input[type=text], input[type=password], input[type=number], select, textarea {
  font: inherit; color: var(--text); background: var(--fill); border: 1px solid transparent;
  border-radius: 7px; padding: 7px 9px; outline: none; width: 100%; }
input:focus, select:focus, textarea:focus { border-color: var(--accent); }
textarea { min-height: 90px; font-family: var(--mono); font-size: 12px; resize: vertical; }
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border: none; border-radius: 7px;
  background: var(--fill); color: var(--text); white-space: nowrap; }
.btn:hover { background: var(--fill2); }
.btn.primary { background: var(--accent); color: #fff; }
.btn.danger { color: var(--red); }
.btn.small { padding: 4px 9px; font-size: 12px; }
.btn:disabled { opacity: .45; cursor: default; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-size: 11px; color: var(--muted); font-weight: 600; padding: 8px 10px;
  border-bottom: 1px solid var(--border-soft); }
td { padding: 9px 10px; border-bottom: 1px solid var(--border-soft); vertical-align: middle; }
tr:last-child td { border-bottom: 0; }
.pill { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
.pill.on { background: rgba(50,215,75,.16); color: var(--green); }
.pill.off { background: rgba(255,69,58,.16); color: var(--red); }
.pill.admin { background: rgba(10,132,255,.18); color: var(--accent); }
.pill.active { background: rgba(50,215,75,.18); color: var(--green); }
.pill.ldap { background: rgba(191,90,242,.18); color: #bf5af2; font-weight: 600; letter-spacing: .3px; }
.pill.neutral { background: rgba(235,235,245,.1); color: var(--muted); }
.u-ident { display: flex; flex-direction: column; line-height: 1.2; white-space: nowrap; }
.u-real { font-size: 11px; color: var(--muted); margin-top: 1px; }
.seg { display: inline-flex; background: var(--fill); border-radius: 8px; padding: 3px; gap: 3px; }
.seg button { border: none; background: none; color: var(--text); padding: 6px 14px; border-radius: 6px; font-size: 13px; }
.seg button.sel { background: rgba(10,132,255,.22); color: var(--accent); font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(10,132,255,.35); }
.seg button.sel .subtle { color: var(--accent); }
.banner { border-radius: var(--radius); padding: 12px 16px; margin: 14px 0; font-size: 13px; }
.banner.warn { background: rgba(255,159,10,.12); border: 1px solid rgba(255,159,10,.4); }
.banner.info { background: rgba(10,132,255,.1); border: 1px solid rgba(10,132,255,.3); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.subtle { font-size: 12px; color: var(--tertiary); }
details summary { cursor: pointer; font-size: 13px; color: var(--accent); padding: 6px 0; }
.toast { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); padding: 10px 16px;
  border-radius: 10px; background: var(--panel2); border: 1px solid var(--border); box-shadow: var(--shadow);
  font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 50; }
.toast.show { opacity: 1; }
.toast.err { border-color: rgba(255,69,58,.5); }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border-soft); margin: 8px 0 4px; }
.tabs button { background: none; border: none; color: var(--muted); padding: 10px 16px; font-size: 14px;
  border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tabs button.sel { color: var(--text); border-bottom-color: var(--accent); font-weight: 600; }
.tabpanel { display: none; }
.tabpanel.sel { display: block; }
.assign-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; }
.assign-grid label { display: flex; align-items: center; gap: 6px; font-size: 13px; padding: 5px 8px;
  border-radius: 6px; background: var(--fill); }
.editor { border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-top: 14px;
  background: var(--panel2); }
@media (max-width: 720px){ .grid2 { grid-template-columns: 1fr; } }
"""


def login_page(error: str = "") -> str:
    err = (
        f'<div class="banner warn">{html.escape(error)}</div>' if error else ""
    )
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{_FAVICON_LINK}
<title>Administration — Sign in</title><style>{_STYLE}
body {{ display: grid; place-items: center; min-height: 100vh; }}
.login {{ width: min(380px, 92vw); }}
</style></head><body>
<div class="login">
  <div class="brand" style="justify-content:center; margin-bottom:18px;">
    <div class="logo">{_LOGO_SVG}</div>
    <div><h1>Administration</h1><div class="sub">Process Mining Demonstrator</div></div>
  </div>
  <form class="card col" method="post" action="/login">
    {err}
    <div class="field"><label>Username</label>
      <input type="text" name="username" autocomplete="username" autofocus value="Administrator"></div>
    <div class="field"><label>Password</label>
      <input type="password" name="password" autocomplete="current-password"></div>
    <button class="btn primary" type="submit">Sign in</button>
  </form>
  <p class="subtle" style="text-align:center">Admin access only.</p>
</div></body></html>"""


def dashboard_page(username: str, http_port: int, https_port: int) -> str:
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{_FAVICON_LINK}
<title>Administration</title><style>{_STYLE}</style></head><body>
<div class="topbar">
  <div class="brand"><div class="logo">{_LOGO_SVG}</div>
    <div><h1>Administration</h1><div class="sub">Process Mining Demonstrator</div></div></div>
  <div class="spacer"></div>
  <span class="muted">Signed in as <strong id="who">{html.escape(username)}</strong></span>
  <button class="btn small" onclick="changeOwnPassword()">Change password</button>
  <form method="post" action="/logout" style="display:inline"><button class="btn small">Log out</button></form>
</div>
<div class="wrap">
  <div id="defaultWarn"></div>

  <div class="tabs">
    <button data-tab="tls" class="sel" onclick="selectTab('tls')">TLS / SSL</button>
    <button data-tab="users" onclick="selectTab('users')">Users</button>
    <button data-tab="connections" onclick="selectTab('connections')">Database Connections</button>
    <button data-tab="ldap" onclick="selectTab('ldap')">Directory (LDAP)</button>
  </div>

  <div class="tabpanel sel" id="tab-tls">
  <div class="card">
    <h2>TLS / SSL</h2>
    <p class="muted" style="margin-top:0">Choose how the main application (the GUI server) accepts connections.</p>
    <div class="row" style="flex-wrap:wrap">
      <div class="seg" id="tlsSeg">
        <button data-mode="off">Off (HTTP only)</button>
        <button data-mode="optional">Optional (HTTP + HTTPS)</button>
        <button data-mode="required">Required (HTTPS only)</button>
      </div>
      <button class="btn primary" onclick="saveTlsMode()">Save mode</button>
      <span class="spacer"></span>
      <button class="btn" onclick="restartServer()" title="Rebind the app server's listeners with the current TLS settings">↻ Restart app server</button>
    </div>
    <div id="tlsPlan" class="col" style="margin-top:12px"></div>
    <div class="banner info" id="restartNote" style="display:none">
      TLS mode and certificate changes apply when the app server restarts.
      <button class="btn small" onclick="restartServer()" style="margin-left:8px">↻ Restart now</button>
    </div>
  </div>

  <div class="card">
    <h2>Certificates</h2>
    <div id="certTable"></div>
    <div class="grid2" style="margin-top:16px">
      <div class="col">
        <h2 style="font-size:13px">Generate self-signed</h2>
        <div class="field"><label>Name</label><input type="text" id="g_name" placeholder="e.g. Internal 2026"></div>
        <div class="field"><label>Common name / host</label><input type="text" id="g_cn" placeholder="processmining.example.com"></div>
        <div class="field"><label>Additional SANs (comma-separated DNS / IPs)</label>
          <input type="text" id="g_sans" placeholder="localhost, 127.0.0.1"></div>
        <div class="row">
          <div class="field" style="flex:1"><label>Valid for (days)</label><input type="number" id="g_days" value="825" min="1" max="3650"></div>
          <div class="field" style="flex:1"><label>Key size</label>
            <select id="g_keysize"><option>2048</option><option>3072</option><option>4096</option></select></div>
        </div>
        <div class="col" style="margin-top:auto">
          <label class="row" style="font-size:13px"><input type="checkbox" id="g_activate" style="width:auto"> Activate after generating</label>
          <button class="btn primary" onclick="generateCert()">Generate</button>
        </div>
      </div>
      <div class="col">
        <h2 style="font-size:13px">Upload certificate</h2>
        <div class="field"><label>Name</label><input type="text" id="u_name" placeholder="e.g. Corporate CA"></div>
        <div class="field"><label>Certificate (PEM)</label><textarea id="u_cert" placeholder="-----BEGIN CERTIFICATE-----"></textarea></div>
        <div class="field"><label>Private key (PEM, unencrypted)</label><textarea id="u_key" placeholder="-----BEGIN PRIVATE KEY-----"></textarea></div>
        <div class="col" style="margin-top:auto">
          <label class="row" style="font-size:13px"><input type="checkbox" id="u_activate" style="width:auto"> Activate after uploading</label>
          <button class="btn primary" onclick="uploadCert()">Upload</button>
        </div>
      </div>
    </div>
  </div>
  </div><!-- /tab-tls -->

  <div class="tabpanel" id="tab-users">
  <div class="card">
    <h2>Users</h2>
    <p class="muted" style="margin-top:0">Only enabled users will be allowed to sign in to the main application.</p>
    <div class="banner info" style="display:flex; align-items:center; gap:12px">
      <label class="row" style="font-size:13px; cursor:pointer">
        <input type="checkbox" id="requireLogin" style="width:auto" onchange="saveRequireLogin()"> Require sign-in for the main application
      </label>
      <span class="subtle" id="requireLoginHint"></span>
    </div>
    <div class="row" style="margin:12px 0 6px"><div class="seg" id="userFilter"></div></div>
    <div id="userTable"></div>
    <details style="margin-top:12px"><summary>Add a user</summary>
      <div class="row" style="flex-wrap:wrap; margin-top:10px; align-items:flex-end">
        <div class="field" style="flex:1; min-width:160px"><label>Username</label><input type="text" id="nu_name"></div>
        <div class="field" style="flex:1; min-width:160px"><label>Password</label><input type="password" id="nu_pw"></div>
        <label class="row" style="font-size:13px"><input type="checkbox" id="nu_admin" style="width:auto"> Administrator</label>
        <button class="btn primary" onclick="createUser()">Create user</button>
      </div>
    </details>
  </div>
  </div><!-- /tab-users -->

  <div class="tabpanel" id="tab-connections">
  <div class="card">
    <h2>Database Connections</h2>
    <p class="muted" style="margin-top:0">Define a database (and optional LLM) server, then assign it to the users who may
      use it. Each user sees only the connections assigned to them in the main application.</p>
    <div id="connTable"></div>
    <div class="row" style="margin-top:12px">
      <button class="btn primary" onclick="newConnection()">+ New connection</button>
    </div>

    <div class="editor" id="connEditor" style="display:none">
      <input type="hidden" id="c_id">
      <div class="grid2">
        <div class="col">
          <h2 style="font-size:13px">Database</h2>
          <div class="field"><label>Name</label><input type="text" id="c_name" placeholder="e.g. Production Exasol"></div>
          <div class="field"><label>Comment</label><input type="text" id="c_comment" placeholder="optional"></div>
          <div class="row">
            <div class="field" style="flex:2"><label>Host</label><input type="text" id="c_host" placeholder="db.example.com"></div>
            <div class="field" style="flex:1"><label>Port</label><input type="number" id="c_port" value="8563"></div>
          </div>
          <div class="row">
            <div class="field" style="flex:1"><label>Username</label><input type="text" id="c_username"></div>
            <div class="field" style="flex:1"><label>Schema</label><input type="text" id="c_schema" placeholder="optional"></div>
          </div>
          <div class="field"><label>Password <span class="subtle" id="c_pwHint"></span></label>
            <input type="password" id="c_password" placeholder="••••••••" autocomplete="new-password"></div>
          <label class="row" style="font-size:13px"><input type="checkbox" id="c_useTls" style="width:auto" onchange="toggleTlsFields()"> Use TLS</label>
          <div id="c_tlsFields" style="display:none">
            <div class="field"><label>Certificate mode</label>
              <select id="c_certMode">
                <option value="verify">Verify (system trust store)</option>
                <option value="fingerprint">Pin fingerprint</option>
                <option value="insecure">Accept any (insecure)</option>
              </select></div>
            <div class="field"><label>Fingerprint (SHA-256)</label><input type="text" id="c_fingerprint" placeholder="optional"></div>
            <div class="field"><label>Minimum RSA key size</label><input type="number" id="c_minRsa" value="2048"></div>
          </div>
        </div>
        <div class="col">
          <h2 style="font-size:13px">LLM (optional)</h2>
          <div class="field"><label>Server URL</label><input type="text" id="c_llmUrl" placeholder="https://api.openai.com/v1"></div>
          <div class="field"><label>Model</label><input type="text" id="c_llmModel" placeholder="gpt-4o"></div>
          <div class="field"><label>API key <span class="subtle" id="c_llmKeyHint"></span></label>
            <input type="password" id="c_llmKey" placeholder="••••••••" autocomplete="new-password"></div>

          <h2 style="font-size:13px; margin-top:18px">Assign to users</h2>
          <div class="assign-grid" id="c_assign"></div>
        </div>
      </div>
      <div class="row" style="margin-top:16px; align-items:center">
        <button class="btn primary" onclick="saveConnection()">Save</button>
        <button class="btn" onclick="testConnection()">Test connection</button>
        <button class="btn" onclick="cancelConnection()">Cancel</button>
        <span class="spacer"></span>
        <button class="btn danger" id="c_deleteBtn" onclick="deleteConnection()" style="display:none">Delete</button>
      </div>
      <div id="c_testResult" class="col" style="margin-top:10px"></div>
    </div>
  </div>
  </div><!-- /tab-connections -->

  <div class="tabpanel" id="tab-ldap">
  <div class="card">
    <h2>Directory (LDAP / Active Directory)</h2>
    <p class="muted" style="margin-top:0">When enabled, the <strong>main application</strong> also accepts sign-ins from an
      LDAP directory (search&nbsp;+&nbsp;bind). Directory users are created here automatically on first login as
      plain, enabled users — grant them a role or database connections like any other user. Local accounts always keep
      working, and the admin panel itself stays local-only.</p>
    <div class="banner info" style="display:flex; align-items:center; gap:12px">
      <label class="row" style="font-size:13px; cursor:pointer">
        <input type="checkbox" id="l_enabled" style="width:auto"> Enable directory sign-in for the main app
      </label>
    </div>
    <div class="grid2" style="margin-top:14px">
      <div class="col">
        <h2 style="font-size:13px">Server</h2>
        <div class="field"><label>Server URI</label><input type="text" id="l_uri" placeholder="ldap://dir.example.com:389 or ldaps://dir.example.com:636"></div>
        <label class="row" style="font-size:13px"><input type="checkbox" id="l_startTls" style="width:auto"> Use StartTLS (upgrade a plain ldap:// connection)</label>
        <label class="row" style="font-size:13px"><input type="checkbox" id="l_verify" style="width:auto" checked> Verify server certificate</label>
        <div class="field"><label>CA certificate (PEM, optional)</label><textarea id="l_caCert" placeholder="-----BEGIN CERTIFICATE-----"></textarea></div>
        <p class="subtle">For a lab you can use a plain <code>ldap://</code> URI with StartTLS off — the password is then sent in the clear.</p>
        <div class="row" style="margin-top:auto"><button class="btn" onclick="testLdapServer()">Test server connection</button></div>
        <div id="l_serverTestResult" class="col"></div>
      </div>
      <div class="col">
        <h2 style="font-size:13px">Service account &amp; search</h2>
        <div class="field"><label>Bind DN <span class="subtle">(read-only service account; blank = anonymous)</span></label>
          <input type="text" id="l_bindDN" placeholder="cn=readonly,dc=example,dc=com"></div>
        <div class="field"><label>Bind password <span class="subtle" id="l_bindPwHint"></span></label>
          <input type="password" id="l_bindPw" placeholder="••••••••" autocomplete="new-password"></div>
        <div class="field"><label>Base DN</label><input type="text" id="l_baseDN" placeholder="ou=people,dc=example,dc=com"></div>
        <div class="field"><label>User filter <span class="subtle">(<code>{{username}}</code> is substituted)</span></label>
          <input type="text" id="l_filter" placeholder="(uid={{username}})"></div>
        <div class="row">
          <div class="field" style="flex:1"><label>Login attribute</label><input type="text" id="l_loginAttr" placeholder="uid"></div>
          <div class="field" style="flex:1"><label>Email attribute</label><input type="text" id="l_emailAttr" placeholder="mail"></div>
          <div class="field" style="flex:1"><label>Name attribute</label><input type="text" id="l_displayAttr" placeholder="cn"></div>
        </div>
      </div>
    </div>
    <div class="banner info" style="margin-top:8px">
      <strong>Test a user login</strong> — resolve a directory account and verify its password
      (search&nbsp;+&nbsp;bind). Use <em>Test server connection</em> above to check the server alone.
      <div class="row" style="flex-wrap:wrap; margin-top:8px; align-items:flex-end">
        <div class="field" style="flex:1; min-width:150px"><label>Test username</label><input type="text" id="l_testUser"></div>
        <div class="field" style="flex:1; min-width:150px"><label>Test password</label><input type="password" id="l_testPw" autocomplete="new-password"></div>
        <button class="btn" onclick="testLdap()">Test</button>
      </div>
      <div id="l_testResult" class="col" style="margin-top:8px"></div>
    </div>
    <div class="row" style="margin-top:16px">
      <button class="btn primary" onclick="saveLdap()">Save</button>
    </div>
  </div>
  </div><!-- /tab-ldap -->
</div>
<div class="toast" id="toast"></div>
<script>
const HTTP_PORT = {http_port}, HTTPS_PORT = {https_port};
{_DASHBOARD_JS}
</script>
</body></html>"""


# JS is kept as a separate constant purely for readability of the template above.
_DASHBOARD_JS = r"""
const $ = (id) => document.getElementById(id);
let TLS = null;

function toast(msg, isErr) {
  const t = $('toast'); t.textContent = msg; t.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(t._h); t._h = setTimeout(() => (t.className = 'toast'), 2600);
}
async function api(path, opts) {
  const r = await fetch(path, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
  if (r.status === 401) { location.href = '/login'; throw new Error('unauthorized'); }
  const body = r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error((body && body.detail) || ('HTTP ' + r.status));
  return body;
}
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtDate = (s) => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? '—' : d.toLocaleString(); };

async function loadSession() {
  const s = await api('/api/session');
  $('who').textContent = s.username;
  $('defaultWarn').innerHTML = s.defaultPasswordActive
    ? '<div class="banner warn">⚠️ The <strong>Administrator</strong> account is still using its default password. Change it now with “Change password”.</div>'
    : '';
  $('requireLogin').checked = !!s.requireLogin;
  $('requireLoginHint').textContent = s.requireLogin
    ? 'Users must sign in.' : 'The app is open — no sign-in required.';
}
async function saveRequireLogin() {
  const requireLogin = $('requireLogin').checked;
  try { await api('/api/access/require-login', { method: 'POST', body: JSON.stringify({ requireLogin }) });
    toast('Access updated'); await loadSession(); }
  catch (e) { toast(e.message, true); $('requireLogin').checked = !requireLogin; }
}

// ── TLS ─────────────────────────────────────────────────────────────────────
async function loadTls() {
  TLS = await api('/api/tls');
  document.querySelectorAll('#tlsSeg button').forEach(b =>
    b.classList.toggle('sel', b.dataset.mode === TLS.mode));
  const host = location.hostname;
  const plan = TLS.plan;
  let rows = '';
  rows += `<div class="row"><span class="muted" style="width:150px">HTTP endpoint</span>` +
    (plan.http ? `<a class="mono" href="http://${host}:${HTTP_PORT}/">http://${host}:${HTTP_PORT}/</a>` : `<span class="subtle">disabled</span>`) + `</div>`;
  rows += `<div class="row"><span class="muted" style="width:150px">HTTPS endpoint</span>` +
    (plan.https ? `<a class="mono" href="https://${host}:${HTTPS_PORT}/">https://${host}:${HTTPS_PORT}/</a>` : `<span class="subtle">disabled</span>`) + `</div>`;
  if ((TLS.mode !== 'off') && !plan.hasActiveCert)
    rows += `<div class="banner warn" style="margin:8px 0 0">No active certificate — HTTPS cannot start. Generate or upload one and activate it below.</div>`;
  $('tlsPlan').innerHTML = rows;
  renderCerts();
}
async function saveTlsMode() {
  const sel = document.querySelector('#tlsSeg button.sel');
  if (!sel) return;
  try { await api('/api/tls/mode', { method: 'POST', body: JSON.stringify({ mode: sel.dataset.mode }) });
    toast('TLS mode saved'); $('restartNote').style.display = 'block'; await loadTls(); }
  catch (e) { toast(e.message, true); }
}
document.querySelectorAll('#tlsSeg button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tlsSeg button').forEach(x => x.classList.remove('sel'));
  b.classList.add('sel');
});
async function restartServer() {
  if (!confirm('Restart the app server now?\n\nIts HTTP/HTTPS listeners rebind with the current TLS settings; anyone using the main app will briefly disconnect.')) return;
  try { const r = await api('/api/restart', { method: 'POST' });
    toast('App server restarting (pid ' + r.pid + ')…');
    $('restartNote').style.display = 'none';
    // Give it a moment to rebind, then refresh the endpoint view.
    setTimeout(() => loadTls().catch(() => {}), 1500);
  } catch (e) { toast(e.message, true); }
}

// ── Certificates ────────────────────────────────────────────────────────────
function renderCerts() {
  const certs = TLS.certs || [];
  if (!certs.length) { $('certTable').innerHTML = '<p class="subtle">No certificates yet. Generate or upload one below.</p>'; return; }
  let h = '<table><thead><tr><th>Name</th><th>Subject</th><th>Type</th><th>Expires</th><th></th></tr></thead><tbody>';
  for (const c of certs) {
    const active = c.id === TLS.activeCertId;
    h += `<tr><td><strong>${esc(c.name)}</strong> ${active ? '<span class="pill active">active</span>' : ''}</td>` +
      `<td class="mono">${esc(c.subject)}</td>` +
      `<td>${c.isSelfSigned ? 'Self-signed' : 'CA-signed'}</td>` +
      `<td>${fmtDate(c.notAfter)}</td>` +
      `<td style="text-align:right; white-space:nowrap">` +
        (active ? '' : `<button class="btn small" onclick="activateCert('${c.id}')">Activate</button> `) +
        `<a class="btn small" href="/api/certs/${c.id}/download">Download</a> ` +
        `<button class="btn small danger" onclick="deleteCert('${c.id}','${esc(c.name)}')">Delete</button>` +
      `</td></tr>`;
  }
  $('certTable').innerHTML = h + '</tbody></table>';
}
async function generateCert() {
  const body = { name: $('g_name').value, commonName: $('g_cn').value,
    sans: $('g_sans').value.split(',').map(s => s.trim()).filter(Boolean),
    days: Number($('g_days').value), keySize: Number($('g_keysize').value), activate: $('g_activate').checked };
  try { await api('/api/certs/generate', { method: 'POST', body: JSON.stringify(body) });
    toast('Certificate generated'); $('g_name').value = $('g_cn').value = $('g_sans').value = '';
    $('restartNote').style.display = 'block'; await loadTls(); }
  catch (e) { toast(e.message, true); }
}
async function uploadCert() {
  const body = { name: $('u_name').value, certPem: $('u_cert').value, keyPem: $('u_key').value, activate: $('u_activate').checked };
  try { await api('/api/certs/upload', { method: 'POST', body: JSON.stringify(body) });
    toast('Certificate uploaded'); $('u_name').value = $('u_cert').value = $('u_key').value = '';
    $('restartNote').style.display = 'block'; await loadTls(); }
  catch (e) { toast(e.message, true); }
}
async function activateCert(id) {
  try { await api('/api/certs/' + id + '/activate', { method: 'POST' });
    toast('Certificate activated'); $('restartNote').style.display = 'block'; await loadTls(); }
  catch (e) { toast(e.message, true); }
}
async function deleteCert(id, name) {
  if (!confirm('Delete certificate "' + name + '"?')) return;
  try { await api('/api/certs/' + id, { method: 'DELETE' }); toast('Certificate deleted'); await loadTls(); }
  catch (e) { toast(e.message, true); }
}

// ── Users ───────────────────────────────────────────────────────────────────
let USERS = [];
let USER_FILTER = 'all';  // 'all' | 'local' | 'ldap'

async function loadUsers() {
  USERS = await api('/api/users');
  renderUsers();
}
function setUserFilter(f) { USER_FILTER = f; renderUsers(); }
function renderUsers() {
  const counts = { all: USERS.length, local: 0, ldap: 0 };
  for (const u of USERS) counts[u.authSource === 'ldap' ? 'ldap' : 'local']++;
  const chips = [
    { key: 'all', label: 'All' },
    { key: 'local', label: 'Local' },
    { key: 'ldap', label: 'LDAP' },
  ];
  $('userFilter').innerHTML = chips.map(c =>
    `<button class="${USER_FILTER === c.key ? 'sel' : ''}" onclick="setUserFilter('${c.key}')">` +
    `${c.label} <span class="subtle" style="font-size:11px">${counts[c.key]}</span></button>`
  ).join('');

  const rows = USERS.filter(u =>
    USER_FILTER === 'all' || (u.authSource === 'ldap' ? 'ldap' : 'local') === USER_FILTER);
  let h = '<table><thead><tr><th>Username</th><th>Source</th><th>Role</th><th>Access</th><th>Last sign-in</th><th></th></tr></thead><tbody>';
  if (rows.length === 0) {
    h += '<tr><td colspan="6" class="muted">No matching users.</td></tr>';
  }
  for (const u of rows) {
    const isLdap = u.authSource === 'ldap';
    const nameCell = `<div class="u-ident"><strong>${esc(u.username)}</strong>` +
      (u.displayName ? `<span class="u-real">${esc(u.displayName)}</span>` : '') + `</div>`;
    h += `<tr><td>${nameCell}</td>` +
      `<td>${isLdap ? '<span class="pill ldap">LDAP</span>' : '<span class="pill neutral">local</span>'}</td>` +
      `<td>${u.isAdmin ? '<span class="pill admin">admin</span>' : '<span class="pill neutral">user</span>'}</td>` +
      `<td>${u.isEnabled ? '<span class="pill on">enabled</span>' : '<span class="pill off">disabled</span>'}</td>` +
      `<td class="muted">${fmtDate(u.lastLogin)}</td>` +
      `<td style="text-align:right; white-space:nowrap">` +
        `<button class="btn small" onclick="toggleEnabled('${esc(u.username)}',${!u.isEnabled})">${u.isEnabled ? 'Disable' : 'Enable'}</button> ` +
        `<button class="btn small" onclick="toggleAdmin('${esc(u.username)}',${!u.isAdmin})">${u.isAdmin ? 'Remove admin' : 'Make admin'}</button> ` +
        (isLdap ? '' : `<button class="btn small" onclick="resetPw('${esc(u.username)}')">Reset password</button> `) +
        `<button class="btn small danger" onclick="delUser('${esc(u.username)}')">Delete</button>` +
      `</td></tr>`;
  }
  $('userTable').innerHTML = h + '</tbody></table>';
}
async function createUser() {
  const body = { username: $('nu_name').value.trim(), password: $('nu_pw').value, isAdmin: $('nu_admin').checked };
  try { await api('/api/users', { method: 'POST', body: JSON.stringify(body) });
    toast('User created'); $('nu_name').value = $('nu_pw').value = ''; $('nu_admin').checked = false; await loadUsers(); }
  catch (e) { toast(e.message, true); }
}
async function toggleEnabled(u, enabled) {
  try { await api('/api/users/' + encodeURIComponent(u) + '/enabled', { method: 'POST', body: JSON.stringify({ enabled }) });
    toast('Updated'); await loadUsers(); } catch (e) { toast(e.message, true); }
}
async function toggleAdmin(u, isAdmin) {
  try { await api('/api/users/' + encodeURIComponent(u) + '/admin', { method: 'POST', body: JSON.stringify({ isAdmin }) });
    toast('Updated'); await loadUsers(); } catch (e) { toast(e.message, true); }
}
async function resetPw(u) {
  const pw = prompt('New password for ' + u + ':'); if (!pw) return;
  try { await api('/api/users/' + encodeURIComponent(u) + '/password', { method: 'POST', body: JSON.stringify({ password: pw }) });
    toast('Password reset'); await loadSession(); } catch (e) { toast(e.message, true); }
}
async function delUser(u) {
  if (!confirm('Delete user "' + u + '"?')) return;
  try { await api('/api/users/' + encodeURIComponent(u), { method: 'DELETE' }); toast('User deleted'); await loadUsers(); }
  catch (e) { toast(e.message, true); }
}
async function changeOwnPassword() {
  const pw = prompt('Enter a new password for your account:'); if (!pw) return;
  try { await api('/api/self/password', { method: 'POST', body: JSON.stringify({ password: pw }) });
    toast('Password changed'); await loadSession(); } catch (e) { toast(e.message, true); }
}

// ── Tabs ──────────────────────────────────────────────────────────────────
function selectTab(name) {
  for (const b of document.querySelectorAll('.tabs button'))
    b.classList.toggle('sel', b.dataset.tab === name);
  for (const p of document.querySelectorAll('.tabpanel'))
    p.classList.toggle('sel', p.id === 'tab-' + name);
  if (name === 'connections') loadConnections().catch(e => toast(e.message, true));
  if (name === 'ldap') loadLdap().catch(e => toast(e.message, true));
}

// ── Directory (LDAP) ──────────────────────────────────────────────────────
async function loadLdap() {
  const c = await api('/api/ldap');
  $('l_enabled').checked = !!c.enabled;
  $('l_uri').value = c.serverURI || '';
  $('l_startTls').checked = !!c.startTLS;
  $('l_verify').checked = c.verifyCert !== false;
  $('l_caCert').value = c.caCert || '';
  $('l_bindDN').value = c.bindDN || '';
  $('l_bindPw').value = '';
  $('l_bindPwHint').textContent = c.hasBindPassword ? '(set — leave blank to keep)' : '';
  $('l_baseDN').value = c.baseDN || '';
  $('l_filter').value = c.userFilter || '(uid={username})';
  $('l_loginAttr').value = c.loginAttr || 'uid';
  $('l_emailAttr').value = c.emailAttr || 'mail';
  $('l_displayAttr').value = c.displayAttr || 'cn';
  $('l_testResult').innerHTML = '';
}
function ldapBody() {
  const body = {
    enabled: $('l_enabled').checked,
    serverURI: $('l_uri').value.trim(),
    startTLS: $('l_startTls').checked,
    verifyCert: $('l_verify').checked,
    caCert: $('l_caCert').value,
    bindDN: $('l_bindDN').value.trim(),
    baseDN: $('l_baseDN').value.trim(),
    userFilter: $('l_filter').value.trim() || '(uid={username})',
    loginAttr: $('l_loginAttr').value.trim() || 'uid',
    emailAttr: $('l_emailAttr').value.trim() || 'mail',
    displayAttr: $('l_displayAttr').value.trim() || 'cn',
  };
  if ($('l_bindPw').value) body.bindPassword = $('l_bindPw').value;
  return body;
}
async function saveLdap() {
  try { await api('/api/ldap', { method: 'POST', body: JSON.stringify(ldapBody()) });
    toast('Directory settings saved'); await loadLdap(); }
  catch (e) { toast(e.message, true); }
}
async function testLdapServer() {
  // Server + service-bind only — no user is resolved (test username left blank).
  const body = ldapBody();
  body.testUsername = '';
  body.testPassword = '';
  $('l_serverTestResult').innerHTML = '<span class="muted">Testing…</span>';
  try {
    const r = await api('/api/ldap/test', { method: 'POST', body: JSON.stringify(body) });
    $('l_serverTestResult').innerHTML = r.ok
      ? '<div class="banner info">Server reachable — service bind OK</div>'
      : `<div class="banner warn">${esc(r.error)}</div>`;
  } catch (e) { $('l_serverTestResult').innerHTML = `<div class="banner warn">${esc(e.message)}</div>`; }
}
async function testLdap() {
  const body = ldapBody();
  body.testUsername = $('l_testUser').value.trim();
  body.testPassword = $('l_testPw').value;
  $('l_testResult').innerHTML = '<span class="muted">Testing…</span>';
  try {
    const r = await api('/api/ldap/test', { method: 'POST', body: JSON.stringify(body) });
    let h = r.ok
      ? '<div class="banner info">Service bind: OK</div>'
      : `<div class="banner warn">Service bind failed: ${esc(r.error)}</div>`;
    if (r.matched != null) {
      const cls = r.matched === 1 ? 'info' : 'warn';
      h += `<div class="banner ${cls}">Search matched ${r.matched} entr${r.matched === 1 ? 'y' : 'ies'}` +
        `${r.foundDN ? ' <span class="subtle">(' + esc(r.foundDN) + ')</span>' : ''}</div>`;
    }
    if (r.userOk === true) {
      const u = r.user || {};
      h += `<div class="banner info">User login: OK — ${esc(u.username || '')}${u.dn ? ' <span class="subtle">(' + esc(u.dn) + ')</span>' : ''}</div>`;
    } else if (r.userOk === false) {
      h += `<div class="banner warn">${esc(r.error || 'User login failed')}</div>`;
    }
    $('l_testResult').innerHTML = h;
  } catch (e) { $('l_testResult').innerHTML = `<div class="banner warn">${esc(e.message)}</div>`; }
}

// ── Database Connections ──────────────────────────────────────────────────
let CONNS = [];
let USERNAMES = [];

async function loadConnections() {
  const [conns, users] = await Promise.all([api('/api/connections'), api('/api/users')]);
  CONNS = conns;
  USERNAMES = users.map(u => u.username);
  let h = '<table><thead><tr><th>Name</th><th>Host</th><th>LLM</th><th>Assigned to</th><th></th></tr></thead><tbody>';
  if (!conns.length) h += '<tr><td colspan="5" class="muted">No connections defined yet.</td></tr>';
  for (const c of conns) {
    const who = c.assignments.length ? c.assignments.map(esc).join(', ') : '<span class="muted">nobody</span>';
    h += `<tr><td><strong>${esc(c.name)}</strong>${c.comment ? '<br><span class="subtle">' + esc(c.comment) + '</span>' : ''}</td>` +
      `<td class="muted">${esc(c.host)}:${c.port}</td>` +
      `<td>${c.hasLLMKey || c.llmURL ? '<span class="pill on">yes</span>' : '<span class="muted">—</span>'}</td>` +
      `<td class="muted">${who}</td>` +
      `<td style="text-align:right; white-space:nowrap">` +
        `<button class="btn small" onclick="editConnection('${esc(c.id)}')">Edit</button></td></tr>`;
  }
  $('connTable').innerHTML = h + '</tbody></table>';
}

function renderAssign(selected) {
  const set = new Set(selected || []);
  $('c_assign').innerHTML = USERNAMES.length
    ? USERNAMES.map(u => `<label><input type="checkbox" value="${esc(u)}"${set.has(u) ? ' checked' : ''} style="width:auto"> ${esc(u)}</label>`).join('')
    : '<span class="muted">No users to assign.</span>';
}
function selectedAssignments() {
  return [...$('c_assign').querySelectorAll('input:checked')].map(i => i.value);
}
function toggleTlsFields() { $('c_tlsFields').style.display = $('c_useTls').checked ? 'block' : 'none'; }

function fillEditor(c) {
  $('c_id').value = c.id || '';
  $('c_name').value = c.name || '';
  $('c_comment').value = c.comment || '';
  $('c_host').value = c.host || '';
  $('c_port').value = c.port || 8563;
  $('c_username').value = c.username || '';
  $('c_schema').value = c.schema || '';
  $('c_password').value = '';
  $('c_pwHint').textContent = c.hasPassword ? '(set — leave blank to keep)' : '';
  $('c_useTls').checked = !!c.useTLS; toggleTlsFields();
  $('c_certMode').value = c.certModeRaw || 'verify';
  $('c_fingerprint').value = c.fingerprint || '';
  $('c_minRsa').value = c.minRSAKeySizeBits || 2048;
  $('c_llmUrl').value = c.llmURL || '';
  $('c_llmModel').value = c.llmModel || '';
  $('c_llmKey').value = '';
  $('c_llmKeyHint').textContent = c.hasLLMKey ? '(set — leave blank to keep)' : '';
  renderAssign(c.assignments);
  $('c_testResult').innerHTML = '';
  $('c_deleteBtn').style.display = c.id ? 'inline-flex' : 'none';
  $('connEditor').style.display = 'block';
  $('connEditor').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function newConnection() {
  renderAssign([]);
  fillEditor({ port: 8563, minRSAKeySizeBits: 2048, certModeRaw: 'verify' });
}
function editConnection(id) {
  const c = CONNS.find(x => x.id === id);
  if (c) fillEditor(c);
}
function cancelConnection() { $('connEditor').style.display = 'none'; }

function editorBody() {
  const body = {
    id: $('c_id').value || null,
    name: $('c_name').value.trim(),
    comment: $('c_comment').value.trim(),
    host: $('c_host').value.trim(),
    port: parseInt($('c_port').value, 10) || 8563,
    username: $('c_username').value.trim(),
    schema: $('c_schema').value.trim(),
    useTLS: $('c_useTls').checked,
    certModeRaw: $('c_certMode').value,
    fingerprint: $('c_fingerprint').value.trim(),
    minRSAKeySizeBits: parseInt($('c_minRsa').value, 10) || 2048,
    llmURL: $('c_llmUrl').value.trim(),
    llmModel: $('c_llmModel').value.trim(),
    assignments: selectedAssignments(),
  };
  // Only send secrets when the user typed something (blank ⇒ keep existing).
  if ($('c_password').value) body.password = $('c_password').value;
  if ($('c_llmKey').value) body.llmKey = $('c_llmKey').value;
  return body;
}
async function saveConnection() {
  const body = editorBody();
  if (!body.name) { toast('Name is required.', true); return; }
  try {
    const saved = await api('/api/connections', { method: 'POST', body: JSON.stringify(body) });
    toast('Connection saved');
    await loadConnections();
    const fresh = CONNS.find(x => x.id === saved.id);
    if (fresh) fillEditor(fresh);
  } catch (e) { toast(e.message, true); }
}
async function deleteConnection() {
  const id = $('c_id').value;
  if (!id) return;
  if (!confirm('Delete connection "' + $('c_name').value + '"?')) return;
  try {
    await api('/api/connections/' + encodeURIComponent(id), { method: 'DELETE' });
    toast('Connection deleted'); cancelConnection(); await loadConnections();
  } catch (e) { toast(e.message, true); }
}
async function testConnection() {
  const body = editorBody();
  const test = {
    host: body.host, port: body.port, username: body.username,
    password: $('c_password').value, schema: body.schema, useTLS: body.useTLS,
    certModeRaw: body.certModeRaw, fingerprint: body.fingerprint,
    minRSAKeySizeBits: body.minRSAKeySizeBits, llmURL: body.llmURL, llmKey: $('c_llmKey').value,
  };
  $('c_testResult').innerHTML = '<span class="muted">Testing…</span>';
  try {
    const r = await api('/api/connections/test', { method: 'POST', body: JSON.stringify(test) });
    let h = '';
    h += r.dbError
      ? `<div class="banner warn">Database: ${esc(r.dbError)}</div>`
      : '<div class="banner info">Database: connection OK</div>';
    if (body.llmURL) {
      h += r.llmError
        ? `<div class="banner warn">LLM: ${esc(r.llmError)}</div>`
        : `<div class="banner info">LLM: reachable${r.llmModels && r.llmModels.length ? ' — ' + r.llmModels.length + ' models' : ''}</div>`;
    }
    $('c_testResult').innerHTML = h;
  } catch (e) { $('c_testResult').innerHTML = `<div class="banner warn">${esc(e.message)}</div>`; }
}

loadSession().then(loadTls).then(loadUsers).catch(() => {});
"""
