#!/usr/bin/env python3
"""Generate the self-contained HTML guide "15 - Installation of MCP Server".

Covers every aspect of installing and configuring the seventh surface — the read-only
MCP query server — with the **Authentik** OAuth provider (Keycloak to follow) and
**Claude Desktop** as the example client (other clients to follow).

Facts (ports, admin fields, Authentik steps, Claude connector flow, env vars) are taken
from MCP-SERVER.md, mcp/server.py, backend/app/web_surface.py and admin/pages.py — update
this builder when they change.
Run:  python3 docs/15-build-mcp-install-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "15-Installation-MCP-Server.html"
_BUILDER = pathlib.Path(__file__).name

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon, so the
# browser tab shows the suite's icon while the page stays fully self-contained.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each chapter: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
STEPS = [
    (
        "What the MCP server is",
        "The <b>MCP server</b> is a read-only <a href=\"https://modelcontextprotocol.io\">Model "
        "Context Protocol</a> endpoint that lets AI clients (Claude, ChatGPT, …) query your "
        "Process Mining data — <b>metrics, paths and metadata</b> — over HTTP(S). It is the "
        "<b>seventh surface</b>, on the admin port <b>+40</b>, and it is <b>off until an "
        "administrator enables it</b> (it returns <code>503</code> while off). Callers "
        "authenticate with an <b>OAuth access token from your Authentik server</b>; the token "
        "is verified against Authentik's signing keys and mapped to a Process Mining user, "
        "whose assigned database connections decide what they may see. <b>Nothing here can "
        "write</b> — there are no ingest, edit or sampling tools.",
        """<div class="mock">
      <pre class="calc">AI client ──OAuth──▶ Authentik (:19443)            the client gets an access token
AI client ──MCP/JSON-RPC + Bearer token──▶ MCP server (:8493/mcp)
                       └─ verifies the token against Authentik's JWKS (RS256, offline)
                       └─ maps it to a Process Mining user
                       └─ answers read-only queries on that user's connections</pre>
      <table class="tbl">
        <tr><th>&nbsp;</th><th>HTTP</th><th>HTTPS</th></tr>
        <tr><td>Container port</td><td><code>8130</code></td><td><code>8493</code></td></tr>
        <tr><td>Docker host port (+10000)</td><td><code>18130</code></td><td><code>18493</code></td></tr>
      </table>
      <p class="cap">OAuth clients require HTTPS — use the <b>HTTPS</b> endpoint. The server
        follows the same TLS mode and certificate as the app and admin console.</p>
    </div>""",
        None,
        '<span class="k">Read-only, same boundary as the app.</span> A caller never sees more '
        "than the mapped user's assigned connections — exactly what that person could open in "
        "the main app.",
    ),
    (
        "What it exposes (the tools)",
        "Every query tool takes <code>connectionId</code> + <code>projectId</code> and an "
        "optional filter (<code>sampleSet</code>, <code>fromDate</code>, <code>toDate</code>, "
        "<code>includedSteps</code>, <code>excludedSteps</code>, <code>meta1..3</code>). The "
        "drill-down chain is <code>get_statistics</code> → <code>find_journeys</code> → "
        "<code>get_journey</code>.",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Tool</th><th>Returns</th></tr>
        <tr><td><code>list_connections</code></td><td>The database connections you may query (id, name, schema).</td></tr>
        <tr><td><code>list_projects</code></td><td>Projects on a connection — or, with <code>connectionId</code> omitted, on every connection you may query.</td></tr>
        <tr><td><code>get_process_map</code></td><td>The directly-follows map: steps (nodes) + transitions (edges) with counts/timing.</td></tr>
        <tr><td><code>get_transition_metrics</code></td><td>Per step-pair: count and avg/median/min/max/stddev transition time.</td></tr>
        <tr><td><code>get_variants</code></td><td>Distinct journey paths and how often each occurs (most frequent first).</td></tr>
        <tr><td><code>get_statistics</code></td><td>Journey count, journey-duration stats, process-goodness score.</td></tr>
        <tr><td><code>get_metadata</code></td><td>Meta-attribute titles, step names, and the event date range.</td></tr>
        <tr><td><code>get_journey</code></td><td>One case's ordered events, by business case id or stored hash.</td></tr>
        <tr><td><code>find_journeys</code></td><td>The individual journeys behind an aggregate: slowest cases, cases that visited a step, longest traces.</td></tr>
      </table>
    </div>""",
        None,
        None,
    ),
    (
        "Prerequisites",
        "Before you touch the MCP tab, make sure the pieces it relies on are in place:",
        None,
        [
            "An <b>Authentik</b> server reachable from the Process Mining host (this guide "
            "assumes <code>https://authentik.example.com:19443</code>).",
            "Administrator access to <b>both</b> Authentik and the Process Mining admin console.",
            "Each MCP user must <b>already exist and be enabled</b> in Process Mining "
            "(<i>Users</i> tab) with the <b>same username</b> the token will carry.",
            "That user must be <b>assigned the connection(s)</b> they should query "
            "(<i>Database Connections</i> tab).",
            "<b>TLS enabled</b> in the admin (<i>TLS / SSL</i> tab) so the HTTPS endpoint "
            "(<code>:18493</code>) is live — OAuth clients require HTTPS.",
        ],
        '<span class="k">No PM user, no access.</span> The token only authenticates <i>who</i> '
        "the caller is; the matching Process Mining user (and its connection assignments) is "
        "what grants any data at all. A valid token for a username with no PM account gets "
        "<code>403</code>.",
    ),
    (
        "Part A — Configure Authentik",
        "Create a dedicated OAuth2/OpenID provider and an application in front of it, then note "
        "the endpoints the MCP server will trust.",
        """<div class="mock">
      <p class="cap"><b>1 · Create an OAuth2/OpenID Provider</b> &nbsp;—&nbsp;
        <i>Applications → Providers → Create → OAuth2/OpenID Provider</i></p>
      <table class="tbl">
        <tr><th>Field</th><th>Value</th></tr>
        <tr><td>Name</td><td><code>Process Mining MCP</code></td></tr>
        <tr><td>Authorization flow</td><td>your standard explicit- (or implicit-) consent flow</td></tr>
        <tr><td>Client type</td><td><code>Public</code> (PKCE, recommended for interactive clients) — or <code>Confidential</code> if the client stores a secret</td></tr>
        <tr><td>Signing key</td><td>an <b>RSA</b> key → the access token is a signed <b>RS256 JWT</b> the server verifies offline</td></tr>
        <tr><td>Scopes</td><td><code>openid</code>, <code>profile</code>, <code>email</code> (+ <code>offline_access</code> for refresh tokens)</td></tr>
        <tr><td>Redirect URIs</td><td>the callback(s) your client uses — for Claude, see Part C</td></tr>
      </table>
      <p class="cap"><b>2 · Create an Application</b> bound to that provider &nbsp;—&nbsp;
        <i>Applications → Applications → Create.</i> Name <code>Process Mining MCP</code>,
        slug e.g. <code>process-mining-mcp</code>. Under <b>Bindings</b>, restrict who may use
        it (e.g. bind a group <code>process-mining-users</code>).</p>
      <p class="cap"><b>3 · Note the endpoints</b> (all under
        <code>…/application/o/process-mining-mcp/</code>):</p>
      <pre class="calc">Issuer     https://authentik.example.com:19443/application/o/process-mining-mcp/
Discovery  &lt;issuer&gt;/.well-known/openid-configuration
JWKS       &lt;issuer&gt;/jwks/</pre>
    </div>""",
        None,
        '<span class="k">Set an Audience (recommended).</span> Authentik only sets the token\'s '
        "<code>aud</code> if you add an audience via a scope/property mapping. Do it and put the "
        "client id in the MCP <b>Audience</b> field: it ties each token to <i>this</i> "
        "application, so a token minted for another app on the same Authentik can't be replayed "
        "here. Leave it blank and the <code>aud</code> check is skipped (still gated by issuer, "
        "signature, user-mapping and group).",
    ),
    (
        "Part B — Configure the MCP server (admin console)",
        "Open the admin console → <b>MCP Server</b> tab and fill in the Authentik (OAuth) "
        "settings. <b>No secrets are stored here</b> — only these public coordinates, because "
        "tokens are validated offline against the JWKS.",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Field</th><th>What to enter</th></tr>
        <tr><td>Issuer URL</td><td><code>https://authentik.example.com:19443/application/o/process-mining-mcp/</code></td></tr>
        <tr><td>JWKS URL</td><td>blank to auto-discover from the issuer, or paste <code>…/jwks/</code></td></tr>
        <tr><td>Audience / Client ID</td><td>the client id (recommended, once you mapped <code>aud</code>); blank skips the check</td></tr>
        <tr><td>Required group</td><td>optional — only members of this Authentik group may connect (matched against the token's <code>groups</code>)</td></tr>
        <tr><td>Username claim</td><td>the JWT claim matched to a PM username — default <code>preferred_username</code>; use <code>email</code> if usernames are email addresses</td></tr>
      </table>
      <p class="cap">Then: <b>Save settings</b> → <b>Test Authentik</b> (fetches the discovery
        document and JWKS and reports the signing-key count — fix any error first) →
        tick <b>Enable the MCP server</b>. Enabling/disabling is immediate; no restart.</p>
    </div>""",
        None,
        '<span class="k">A TLS change needs a restart.</span> Turn TLS on in the <b>TLS / SSL</b> '
        "tab; the change takes effect after <b>↻ Restart app server</b> (App Control). Enabling "
        "or disabling the MCP server itself does not.",
    ),
    (
        "Behind a reverse proxy (optional)",
        "The MCP server listens on its own port. To publish it under a public domain path — "
        "e.g. <code>https://pm.example.com/mcp</code> — a proxy must <b>preserve the "
        "<code>/mcp</code> path</b> and <b>send forwarding headers</b> so the OAuth discovery "
        "document advertises the public URL, not the internal host:port.",
        """<div class="mock">
      <pre class="calc">location /mcp {
    proxy_pass https://127.0.0.1:18493;   # NO trailing slash — keep the /mcp path
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
}
location = /.well-known/oauth-protected-resource     { proxy_pass https://127.0.0.1:18493; proxy_set_header X-Forwarded-Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
location = /.well-known/oauth-protected-resource/mcp { proxy_pass https://127.0.0.1:18493; proxy_set_header X-Forwarded-Host $host; proxy_set_header X-Forwarded-Proto $scheme; }</pre>
      <p class="cap">A <b>trailing slash</b> on <code>proxy_pass</code> strips the prefix and the
        backend answers <code>404 {"detail":"Not Found"}</code>. The server also answers at the
        root as a fallback, so a stripping proxy still works — but preserving the path is
        cleaner. Route <code>/mcp</code>, the two well-known paths and <code>/health</code>.</p>
    </div>""",
        [
            "Point the client at the public URL (<code>https://pm.example.com/mcp</code>).",
            "Or skip the proxy and expose the port directly "
            "(<code>https://&lt;host&gt;:18493/mcp</code>) if your firewall allows it and TLS "
            "is on.",
        ],
        None,
    ),
    (
        "Part C — Add the server to Claude Desktop",
        "Claude is the example client here; any MCP client that supports <b>remote (HTTP) "
        "servers with OAuth</b> follows the same shape (more client walkthroughs to follow).",
        """<div class="mock">
      <table class="tbl">
        <tr><th>#</th><th>In Claude Desktop</th></tr>
        <tr><td>1</td><td><b>Settings → Connectors → Add custom connector</b>.</td></tr>
        <tr><td>2</td><td><b>Name</b> <code>Process Mining</code> · <b>URL</b> <code>https://&lt;your-host&gt;:18493/mcp</code> (or your proxy URL).</td></tr>
        <tr><td>3</td><td>Save and click <b>Connect</b>. Claude reads the server's <code>/.well-known/oauth-protected-resource</code>, opens Authentik's sign-in, and stores the token after you approve.</td></tr>
        <tr><td>4</td><td>Enable the connector in a chat and ask e.g. <i>&ldquo;list my process-mining connections&rdquo;</i>, then <i>&ldquo;show the process map for project 1 on connection c1&rdquo;</i>.</td></tr>
      </table>
      <p class="cap">Add Claude's OAuth <b>redirect URIs</b> to the Authentik provider (Part A):
        <code>https://claude.ai/api/mcp/auth_callback</code>,
        <code>https://claude.com/api/mcp/auth_callback</code>, and for the desktop app a local
        loopback such as <code>http://localhost:*</code> — use the exact value Claude shows you
        if it differs.</p>
    </div>""",
        None,
        '<span class="k">The token is the user.</span> Whoever signs in at Authentik must match '
        "an enabled Process Mining user (by the configured username claim). Claude then sees "
        "exactly that user's connections — nothing more.",
    ),
    (
        "Verifying by hand",
        "Two quick checks from a shell confirm the endpoint is live and discoverable before you "
        "involve a client (<code>-k</code> accepts the self-signed internal certificate):",
        """<div class="mock">
      <pre class="calc"># liveness (unauthenticated) → {"ok":true,"enabled":true}
curl -k https://&lt;your-host&gt;:18493/health

# OAuth discovery (unauthenticated) → the Authentik authorization server
curl -k https://&lt;your-host&gt;:18493/.well-known/oauth-protected-resource

# a real call, with a token you already obtained from Authentik
curl -k -X POST https://&lt;your-host&gt;:18493/mcp \\
  -H "Authorization: Bearer &lt;ACCESS_TOKEN&gt;" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"list_connections","arguments":{}}}'</pre>
    </div>""",
        None,
        None,
    ),
    (
        "Troubleshooting",
        "The common failures and where to fix them:",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Symptom</th><th>Cause / fix</th></tr>
        <tr><td><code>503 The MCP server is disabled</code></td><td>Enable it in the admin <b>MCP Server</b> tab.</td></tr>
        <tr><td><code>401</code> + a <code>WWW-Authenticate</code> header</td><td>No/invalid token — the client should run the OAuth flow. Check issuer/JWKS and press <b>Test Authentik</b>.</td></tr>
        <tr><td><code>403 No enabled Process Mining user matches '…'</code></td><td>The token's username claim doesn't match an enabled PM user. Create it (Users tab) with that exact name, or change the <b>Username claim</b> (e.g. to <code>email</code>).</td></tr>
        <tr><td><code>403 …not in the group required</code></td><td>The user isn't in the configured <b>Required group</b> in Authentik.</td></tr>
        <tr><td><code>Connection … is not assigned to you</code></td><td>Assign the connection to the user (Database Connections tab).</td></tr>
        <tr><td>Test can't reach Authentik</td><td>Wrong issuer URL, or the host can't reach <code>:19443</code>. The URL and network path must be right.</td></tr>
      </table>
    </div>""",
        None,
        None,
    ),
]

BEYOND = [
    "<b>Keycloak (and other OIDC providers) to follow.</b> This guide uses Authentik, but the "
    "MCP server trusts any provider that issues <b>RS256 JWTs with a JWKS endpoint</b> — so "
    "Keycloak already works today with the equivalent settings; a dedicated Keycloak "
    "walkthrough is coming.",
    "<b>More clients to follow.</b> Claude Desktop is the worked example; the same custom-"
    "connector pattern applies to any client that supports remote HTTP MCP servers with OAuth.",
    "<b>Tuning env vars</b>: <code>PMW_MCP_MAX_ROWS</code> (default 1000) caps rows returned "
    "per call; <code>PMW_MCP_JWKS_CACHE_SECS</code> (default 3600) sets how long signing keys "
    "are cached.",
    "<b>Token integrity does not depend on TLS.</b> Tokens are verified cryptographically "
    "against Authentik's JWKS (RS256); only the JWKS <i>transport</i> skips certificate "
    "verification (Authentik is a trusted internal host).",
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
.hero a{color:#fff}
.lead{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 22px;
  margin:0 0 30px;color:var(--soft)}
.lead b{color:var(--ink)}
.lead code, .step ul li code, .cap code, .step p.body code{background:var(--bg);border-radius:4px;
  padding:0 5px;font-size:13px}
.step{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 22px 8px;
  margin:0 0 22px;box-shadow:0 1px 2px rgba(20,30,50,.04)}
.step-head{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.num{flex:0 0 auto;width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  font-weight:800;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2))}
.step h2{font-size:20px;margin:0;font-weight:750}
.step p.body{margin:2px 0 16px}
.step p.body a{color:var(--accent)}
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
.tbl td{padding:5px 12px 5px 0;border-bottom:1px solid var(--line);vertical-align:top}
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
<title>15 - Installation of MCP Server</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Suite · MCP Server</span>
  <h1>Installing the MCP Server</h1>
  <p>The seventh surface: a <b>read-only</b> Model Context Protocol endpoint that lets AI
     clients query your process-mining metrics, paths and metadata — authenticated with
     <b>OAuth via Authentik</b>. This guide takes you from an Authentik provider to a
     connected <b>Claude Desktop</b>.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    The MCP server is <b>off by default</b> and adds <b>no new credentials</b>: it trusts an
    external OAuth provider, verifies each token against that provider's public signing keys,
    and maps it to an existing Process Mining user — so a caller sees exactly the connections
    that user is assigned, and never anything to write. This guide uses <b>Authentik</b>
    (Keycloak to follow) and <b>Claude Desktop</b> as the example client (other clients to
    follow).
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Rule of thumb: get <code>curl -k https://&lt;host&gt;:18493/health</code>
      returning <code>{{"ok":true,"enabled":true}}</code> first — then add the connector in
      Claude.</p>
  </div>

  <footer>Process Mining Demonstrator · Suite — Installation of the MCP Server (Authentik OAuth · Claude Desktop)</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
