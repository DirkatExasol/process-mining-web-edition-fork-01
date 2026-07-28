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

# Resolve the persisted theme before first paint (no flash of the wrong palette).
# 'system' follows the OS; the stored value is shared with the topbar control below.
_THEME_BOOT = (
    "<script>(function(){try{var t=localStorage.getItem('pmw_admin_theme')||'system';"
    "var d=t==='system'?matchMedia('(prefers-color-scheme: dark)').matches:t==='dark';"
    "document.documentElement.dataset.theme=d?'dark':'light';}catch(e){}})();</script>"
)

_STYLE = """
:root {
  /* Light is the default; the dark palette (below) mirrors the previous look and is
     applied via data-theme, matching the main app's theme mechanism. */
  --bg: #f2f2f7; --panel: #ffffff; --panel2: #eceef3; --fill: rgba(120,120,128,.12);
  --fill2: rgba(120,120,128,.2); --border: rgba(60,60,67,.29); --border-soft: rgba(60,60,67,.12);
  --text: #1c1c1e; --muted: rgba(60,60,67,.6); --tertiary: rgba(60,60,67,.3);
  --accent: #0a84ff; --green: #248a3d; --red: #d70015; --orange: #c93400; --yellow: #b25000;
  --radius: 10px; --shadow: 0 8px 30px rgba(0,0,0,.18);
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color-scheme: light;
}
:root[data-theme='dark'] {
  --bg: #0b0b0d; --panel: #16161a; --panel2: #1d1d22; --fill: rgba(120,120,128,.16);
  --fill2: rgba(120,120,128,.28); --border: rgba(120,120,128,.28); --border-soft: rgba(120,120,128,.16);
  --text: #f2f2f7; --muted: rgba(235,235,245,.6); --tertiary: rgba(235,235,245,.3);
  --green: #32d74b; --red: #ff453a; --orange: #ff9f0a; --yellow: #ffd60a;
  --shadow: 0 8px 30px rgba(0,0,0,.5);
  color-scheme: dark;
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
.codeblock { background: var(--panel2); border: 1px solid var(--border-soft); border-radius: 8px;
  padding: 12px 40px 12px 14px; font-family: var(--mono); font-size: 12px; line-height: 1.5; overflow-x: auto; }
.codeblock .tok { color: var(--accent, #0a84ff); font-weight: 600; }
.codeblock-wrap { position: relative; }
.copy-btn { position: absolute; top: 8px; right: 8px; padding: 3px 7px; border: 1px solid var(--border-soft);
  border-radius: 6px; background: var(--panel); cursor: pointer; font-size: 13px; line-height: 1; }
.copy-btn:hover { background: var(--fill2); }
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
.pill.power { background: rgba(48,209,196,.18); color: #30d1c4; font-weight: 600; letter-spacing: .3px; }
.pill.log-info { background: rgba(10,132,255,.16); color: var(--accent); }
.pill.log-usage { background: rgba(50,215,75,.16); color: var(--green); }
.pill.log-warn { background: rgba(255,159,10,.16); color: var(--orange); }
.pill.log-error { background: rgba(255,69,58,.16); color: var(--red); }
.pill.log-debug { background: var(--fill2); color: var(--muted); }
#logTable table { table-layout: fixed; width: 100%; }
#logTable td { font-size: 12px; vertical-align: top; }
#logTable th:first-child, #logTable td:first-child { white-space: nowrap; width: 104px; }
#logTable th:nth-child(2), #logTable td:nth-child(2) { white-space: nowrap; width: 76px; }
/* Every row stays exactly one line regardless of message length — long SQL is
   clipped with an ellipsis; a click opens the full entry in a popup. */
#logTable td:last-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 0; }
#logTable tbody tr { cursor: pointer; }
#logTable tbody tr:hover { background: var(--fill); }
/* Full-entry popup (mirrors the help overlay). */
.log-ov { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; background: rgba(0,0,0,.4); }
.log-ov[hidden] { display: none; }
.log-ov-box { width: min(760px, 92vw); max-height: 84vh; overflow: auto; background: var(--panel);
  border: 1px solid var(--border-soft); border-radius: 12px; padding: 18px; box-shadow: 0 20px 60px rgba(0,0,0,.4); }
/* Theme-aware grey (the old near-white tint was invisible on the light card);
   the inset outline keeps it reading as a badge without changing its size. */
.pill.neutral { background: var(--fill2); color: var(--text); box-shadow: inset 0 0 0 1px var(--border-soft); }
/* Two important roles at once (admin + power / admin + user): one badge whose
   background gently floats between the two role colours (--c1 → --c2). */
.pill.combo { color: #fff; font-weight: 600; letter-spacing: .3px;
  background: linear-gradient(90deg, var(--c1), var(--c2), var(--c1));
  background-size: 220% 100%; animation: pillFloat 4s ease-in-out infinite; }
.pill.combo .sep { opacity: .6; margin: 0 1px; font-weight: 400; }
@keyframes pillFloat { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }
@media (prefers-reduced-motion: reduce) { .pill.combo { animation: none; } }
.u-ident { display: flex; flex-direction: column; line-height: 1.2; white-space: nowrap; }
.u-real { font-size: 11px; color: var(--muted); margin-top: 1px; }
.seg { display: inline-flex; background: var(--fill); border-radius: 8px; padding: 3px; gap: 3px; }
.seg button { border: none; background: none; color: var(--text); padding: 6px 14px; border-radius: 6px; font-size: 13px; }
.seg button.sel { background: rgba(10,132,255,.22); color: var(--accent); font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(10,132,255,.35); }
.seg button.sel .subtle { color: var(--accent); }
.theme-seg { padding: 2px; }
.theme-seg button { padding: 5px 10px; font-size: 15px; line-height: 1; }
.banner { border-radius: var(--radius); padding: 12px 16px; margin: 14px 0; font-size: 13px; }
.banner.warn { background: rgba(255,159,10,.12); border: 1px solid rgba(255,159,10,.4); }
.banner.info { background: rgba(10,132,255,.1); border: 1px solid rgba(10,132,255,.3); }
.banner.ok { background: rgba(48,209,88,.12); border: 1px solid rgba(48,209,88,.4); }
.banner.err { background: rgba(255,69,58,.12); border: 1px solid rgba(255,69,58,.45); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.subtle { font-size: 12px; color: var(--tertiary); }
details summary { cursor: pointer; font-size: 13px; color: var(--accent); padding: 6px 0; }
.toast { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); padding: 10px 16px;
  border-radius: 10px; background: var(--panel2); border: 1px solid var(--border); box-shadow: var(--shadow);
  font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none; z-index: 50; }
.toast.show { opacity: 1; }
.toast.err { border-color: rgba(255,69,58,.5); }
/* Help overlay — mirrors the main app's Help panel (the master): a clean
   borderless table of contents with a soft-accent active row, a subtle title
   bar, and a titled content pane. */
.help-ov { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center;
  background: rgba(0,0,0,.4); padding: 24px; }
.help-ov[hidden] { display: none; }
.help-ov-panel { width: min(880px, 100%); height: min(640px, 90vh); display: flex; flex-direction: column;
  background: var(--panel); border: 1px solid var(--border-soft); border-radius: var(--radius);
  box-shadow: var(--shadow); overflow: hidden; }
.help-ov-bar { display: flex; align-items: center; gap: 10px; padding: 11px 14px;
  background: rgba(120,120,128,.08); font-weight: 600; }
.help-ov-bar .spacer { flex: 1; }
.help-ov-body { display: flex; flex: 1; min-height: 0; }
.help-ov-nav { width: 210px; flex-shrink: 0; overflow-y: auto; padding: 8px;
  border-right: 1px solid var(--border-soft); display: flex; flex-direction: column; gap: 2px; }
.help-ov-nav button { display: flex; align-items: center; gap: 6px; width: 100%; text-align: left;
  border: none; background: none; color: var(--text); padding: 6px 10px; border-radius: 8px; font-size: 13px; }
.help-ov-nav button:hover { background: var(--fill); }
.help-ov-nav button.sel { background: rgba(10,132,255,.14); color: var(--accent); font-weight: 600; }
.help-ov-content { flex: 1; overflow-y: auto; padding: 20px 24px; font-size: 13px; line-height: 1.55; }
.help-ov-content h2 { font-size: 20px; font-weight: 700; margin: 0 0 12px; padding-bottom: 10px;
  border-bottom: 1px solid var(--border-soft); }
.help-ov-content p { margin: 0 0 10px; color: var(--text); }
.help-ov-content .note { padding: 8px 12px; border-radius: 8px; margin: 10px 0 0;
  background: rgba(10,132,255,.1); border: 1px solid rgba(10,132,255,.28); }
.help-ov-content .warn { background: rgba(255,159,10,.12); border-color: rgba(255,159,10,.32); }
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


def login_page(error: str = "", inactivity: bool = False, bg_css: str = "") -> str:
    """The admin sign-in screen — a faithful port of the main app's login panel
    (`LoginView.tsx`, the master): identical layout, field sizing and behaviour
    (submit stays disabled until a username is entered). The ONLY difference is
    the two-line title (Process Mining Demonstrator / Administration).

    ``bg_css`` overrides the page background (admin Customize tab). It is a value
    already validated by the security store, safe to inject; blank keeps the
    theme colour."""
    # Custom background chosen in the admin Customize tab, or the theme default.
    body_bg = bg_css or "var(--l-grouped)"
    # Over a custom background image, make the panel 50% transparent so the image
    # shows through (a colour/default background keeps the panel solid).
    panel_class = " translucent" if "url(" in body_bg else ""
    err = (
        f'<div class="login-err">{html.escape(error)}</div>' if error else ""
    )
    # Same inactivity notice the app shows (LoginView.tsx); error takes precedence.
    notice = (
        '<div class="login-notice">You were signed out due to inactivity.</div>'
        if inactivity and not error
        else ""
    )
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{_FAVICON_LINK}{_THEME_BOOT}
<title>Administration — Sign in</title><style>{_STYLE}
/* App-master (LoginView.tsx) tokens, mirrored so both panels render identically
   in light and dark. Rules are scoped under .login-splash so they win over the
   base input/button styles in _STYLE. */
:root {{
  --l-material: rgba(255,255,255,.82);
  /* Layered elevation so the panel floats above any background — colour or
     photo — with a faint hairline ring keeping its edge legible over imagery. */
  --l-shadow: 0 0 0 0.5px rgba(0,0,0,.07), 0 4px 12px rgba(0,0,0,.18),
    0 30px 60px rgba(0,0,0,.34), 0 64px 120px rgba(0,0,0,.42);
  --l-primary: #000; --l-secondary: rgba(60,60,67,.6);
  --l-fill: rgba(120,120,128,.12); --l-grouped: #f2f2f7;
}}
:root[data-theme='dark'] {{
  --l-material: rgba(38,38,40,.86);
  --l-shadow: 0 0 0 0.5px rgba(255,255,255,.1), 0 4px 12px rgba(0,0,0,.6),
    0 30px 64px rgba(0,0,0,.72), 0 68px 130px rgba(0,0,0,.82);
  --l-primary: #fff; --l-secondary: rgba(235,235,245,.6);
  --l-fill: rgba(120,120,128,.24); --l-grouped: #000;
}}
body {{ display: grid; place-items: center; min-height: 100vh; background: {body_bg}; padding: 24px; }}
.login-splash {{ width: min(460px, 100%); border-radius: 20px; background: var(--l-material);
  -webkit-backdrop-filter: blur(30px); backdrop-filter: blur(30px); box-shadow: var(--l-shadow);
  padding: 32px 28px; display: flex; flex-direction: column; align-items: center; gap: 16px; text-align: center; }}
/* Over a background image the panel is 50% transparent; content stays opaque. */
.login-splash.translucent {{ background: rgba(255,255,255,.5); }}
:root[data-theme='dark'] .login-splash.translucent {{ background: rgba(38,38,40,.5); }}
.login-splash .login-logo {{ width: 64px; height: 64px; border-radius: 11px; display: grid; place-items: center;
  background: none; box-shadow: 0 2px 6px rgba(10,20,60,.28); flex-shrink: 0; }}
.login-splash .login-logo .pm-logo {{ width: 100%; height: 100%; }}
.login-splash .title-col {{ display: flex; flex-direction: column; align-items: center; gap: 2px; }}
.login-splash .t-title3 {{ font-size: 20px; font-weight: 700; color: var(--l-primary); line-height: 1.2; }}
.login-splash .t-caption {{ font-size: 11px; color: var(--l-secondary); }}
.login-splash .login-form {{ display: flex; flex-direction: column; align-items: center; gap: 16px; width: 100%; }}
.login-splash .field {{ display: flex; flex-direction: column; gap: 3px; width: 100%; text-align: left; }}
.login-splash .field-label {{ font-size: 11px; color: var(--l-secondary); }}
.login-splash .text-input {{ width: 100%; padding: 5px 8px; font-size: 12px; border-radius: 6px;
  border: 1px solid transparent; background: var(--l-fill); color: var(--l-primary); outline: none; }}
.login-splash .text-input:focus {{ border-color: transparent; }}
.login-splash .btn-prominent {{ width: 100%; padding: 10px; font-size: 15px; font-weight: 500; border-radius: 6px;
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
  background: var(--accent); color: #fff; border: none; white-space: nowrap; }}
.login-splash .btn-prominent:hover:not(:disabled) {{ filter: brightness(1.08); }}
.login-splash .btn-prominent:disabled {{ opacity: .4; cursor: default; }}
.login-splash .login-err, .login-splash .login-notice {{ width: 100%; padding: 10px 12px; border-radius: 6px;
  font-size: 12px; text-align: left; }}
.login-splash .login-err {{ background: rgba(255,59,48,.12); border: 1px solid rgba(255,59,48,.32); color: #ff3b30; }}
.login-splash .login-notice {{ background: rgba(255,159,10,.12); border: 1px solid rgba(255,159,10,.32); color: #ff9500; text-align: center; }}
.login-splash .dir-row {{ display: flex; align-items: center; gap: 6px; }}
.login-splash .t-caption2 {{ font-size: 10px; color: var(--l-secondary); }}
.login-splash .spinner {{ width: 16px; height: 16px; border-radius: 50%; border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff; animation: spin .8s linear infinite; display: inline-block; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style></head><body>
<div class="login-splash{panel_class}">
  <div class="login-logo">{_LOGO_SVG}</div>
  <div class="title-col">
    <span class="t-title3">Process Mining Demonstrator</span>
    <span class="t-title3">Administration</span>
    <span class="t-caption">Sign in to continue</span>
  </div>
  {notice}{err}
  <form class="login-form" method="post" action="/login" id="loginForm">
    <div class="field"><label class="field-label" for="u">Username</label>
      <input class="text-input" id="u" type="text" name="username" autocomplete="username"
        autocapitalize="none" autocorrect="off" autofocus></div>
    <div class="field"><label class="field-label" for="p">Password</label>
      <input class="text-input" id="p" type="password" name="password" autocomplete="current-password"></div>
    <button class="btn-prominent" type="submit" id="signin" disabled>
      <span class="spinner" id="spin" style="display:none"></span> Sign in</button>
  </form>
  <div id="dirStatus" class="dir-row" style="display:none">
    <span id="dirDot" style="width:8px; height:8px; border-radius:50%; flex:0 0 auto"></span>
    <span id="dirLabel" class="t-caption2"></span>
  </div>
</div>
<script>
// Submit stays disabled until a username is entered — mirrors the app's LoginView.
(function () {{
  var u = document.getElementById('u'), btn = document.getElementById('signin');
  var form = document.getElementById('loginForm'), spin = document.getElementById('spin');
  function sync() {{ btn.disabled = !u.value.trim(); }}
  u.addEventListener('input', sync); sync();
  form.addEventListener('submit', function () {{
    if (btn.disabled) return;
    btn.disabled = true; spin.style.display = 'inline-block';  // busy state during the POST
  }});
}})();
// Directory-server availability LED — shown only when a directory is configured.
(async function () {{
  try {{
    const s = await (await fetch('/api/directory-status')).json();
    if (!s.configured) return;
    const ok = !!s.available;
    const color = ok ? 'var(--green)' : 'var(--red)';
    const dot = document.getElementById('dirDot');
    dot.style.background = color;
    dot.style.boxShadow = '0 0 6px ' + color;
    document.getElementById('dirLabel').textContent =
      'Directory server ' + (ok ? 'available' : 'unavailable');
    document.getElementById('dirStatus').style.display = 'flex';
  }} catch (e) {{ /* never block the login screen */ }}
}})();
</script>
</body></html>"""


def dashboard_page(username: str, http_port: int, https_port: int) -> str:
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
{_FAVICON_LINK}{_THEME_BOOT}
<title>Administration</title><style>{_STYLE}</style></head><body>
<div class="topbar">
  <div class="brand"><div class="logo">{_LOGO_SVG}</div>
    <div><h1>Administration</h1><div class="sub">Process Mining Demonstrator</div></div></div>
  <div class="spacer"></div>
  <div class="seg theme-seg" id="themeSeg" title="Appearance">
    <button data-theme-choice="system" title="System" aria-label="System theme" onclick="setTheme('system')">◐</button>
    <button data-theme-choice="light" title="Light" aria-label="Light theme" onclick="setTheme('light')">☀</button>
    <button data-theme-choice="dark" title="Dark" aria-label="Dark theme" onclick="setTheme('dark')">☾</button>
  </div>
  <span class="muted">Signed in as <strong id="who">{html.escape(username)}</strong></span>
  <button class="btn small" onclick="openHelp()" title="Administration help">❔ Help</button>
  <button class="btn small" onclick="changeOwnPassword()">Change password</button>
  <form method="post" action="/logout" style="display:inline"><button class="btn small">Log out</button></form>
</div>
<div class="help-ov" id="helpOv" hidden onclick="if(event.target===this)closeHelp()">
  <div class="help-ov-panel" role="dialog" aria-label="Administration help">
    <div class="help-ov-bar"><span aria-hidden>⚙︎</span><span class="spacer">Administration</span>
      <button class="btn small" onclick="closeHelp()" aria-label="Close help">✕</button></div>
    <div class="help-ov-body">
      <nav class="help-ov-nav" id="helpNav"></nav>
      <div class="help-ov-content" id="helpContent"></div>
    </div>
  </div>
</div>
<div class="wrap">
  <div id="defaultWarn"></div>

  <div class="tabs">
    <button data-tab="appcontrol" class="sel" onclick="selectTab('appcontrol')">App Control</button>
    <button data-tab="tls" onclick="selectTab('tls')">TLS / SSL</button>
    <button data-tab="users" onclick="selectTab('users')">Users</button>
    <button data-tab="connections" onclick="selectTab('connections')">Database Connections</button>
    <button data-tab="ldap" onclick="selectTab('ldap')">Directory (LDAP)</button>
    <button data-tab="logging" onclick="selectTab('logging')">Logging</button>
    <button data-tab="backup" onclick="selectTab('backup')">Backup</button>
    <button data-tab="customize" onclick="selectTab('customize')">Customize</button>
  </div>

  <div class="tabpanel sel" id="tab-appcontrol">
  <div class="card">
    <h2>App Control</h2>
    <p class="muted" style="margin-top:0">Operational controls for the running servers.</p>
    <div class="row" style="flex-wrap:wrap; align-items:center; gap:12px">
      <button class="btn primary" onclick="restartServer()" title="Rebind the app + admin listeners with the current TLS settings">↻ Restart app server</button>
      <span class="subtle">Rebinds the main application and this admin interface in place with the current TLS mode &amp; active certificate — no terminal needed.</span>
    </div>
    <div class="banner info" style="margin-top:14px">
      TLS mode and certificate changes (in the <strong>TLS / SSL</strong> tab) take effect on restart.
      This restarts <strong>both the app and the admin interface</strong> (they share the certificate),
      so this page may briefly drop — and if you changed the mode, the admin moves between
      HTTP <code>:8090</code> and HTTPS <code>:8453</code>; reconnect there if it stops responding.
    </div>
    <div id="restartResult" class="col" style="margin-top:8px"></div>
  </div>
  <div class="card">
    <h2>License</h2>
    <p class="muted" style="margin-top:0">The compute backend requires a valid license.
      Without one it runs for a short grace period and then stops. Upload the
      <code>license.json</code> you were issued to apply it.</p>
    <div id="licenseStatus" class="banner info" style="margin-top:4px">Checking license…</div>
    <div class="row" style="flex-wrap:wrap; align-items:center; gap:12px; margin-top:12px">
      <input type="file" id="licenseFile" accept=".json,application/json">
      <button class="btn primary" onclick="uploadLicense()">Upload license</button>
      <button class="btn" onclick="deleteLicense()">Delete license</button>
      <span class="subtle">The signature is verified before the license is stored.</span>
    </div>
    <div id="licenseResult" class="col" style="margin-top:8px"></div>
  </div>
  <div class="card">
    <h2>Admin session</h2>
    <p class="muted" style="margin-top:0">Automatically sign out of <strong>this admin interface</strong>
      after a period of inactivity. This is separate from the main app's auto sign-out (set in the Users tab).</p>
    <div class="banner info" style="display:flex; align-items:center; gap:10px; flex-wrap:wrap">
      <label class="row" style="font-size:13px; gap:8px">
        Auto sign-out after
        <input type="number" id="adminIdleTimeout" min="0" max="1440" step="1" style="width:80px"> minutes of inactivity
      </label>
      <button class="btn small" onclick="saveAdminIdleTimeout()">Save</button>
      <span class="subtle" id="adminIdleTimeoutHint"></span>
    </div>
  </div>
  </div><!-- /tab-appcontrol -->

  <div class="tabpanel" id="tab-tls">
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
    </div>
    <div id="tlsPlan" class="col" style="margin-top:12px"></div>
    <p class="subtle" style="margin-top:10px">Mode &amp; certificate changes take effect after a restart — use <strong>↻ Restart app server</strong> in the <strong>App Control</strong> tab.</p>
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
    <div class="banner info" style="display:flex; align-items:center; gap:10px; flex-wrap:wrap">
      <label class="row" style="font-size:13px; gap:8px">
        Auto sign-out after
        <input type="number" id="idleTimeout" min="0" max="1440" step="1" style="width:80px"> minutes of inactivity
      </label>
      <button class="btn small" onclick="saveIdleTimeout()">Save</button>
      <span class="subtle" id="idleTimeoutHint"></span>
    </div>
    <div class="banner info" style="display:flex; align-items:center; gap:10px; flex-wrap:wrap">
      <label class="row" style="font-size:13px; gap:8px">
        Disable an account after
        <input type="number" id="maxFailedLogins" min="0" max="100" step="1" style="width:80px"> failed sign-in attempts
      </label>
      <button class="btn small" onclick="saveMaxFailedLogins()">Save</button>
      <span class="subtle" id="maxFailedLoginsHint"></span>
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
      <div class="banner info" style="margin-top:14px">
        <div class="row" style="align-items:center; gap:10px">
          <button class="btn" onclick="provisionSchema()">Create schema &amp; tables</button>
          <span id="c_provisionResult" class="muted"></span>
        </div>
        <label class="row" style="font-size:13px; margin-top:8px">
          <input type="checkbox" id="c_provisionBuildMat" style="width:auto">
          Also build pre-materialized transitions after provisioning
        </label>
        <p class="subtle" style="margin:8px 0 0">
          Creates the schema named above and the process-mining tables
          (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don't exist, using the credentials
          entered here. This requires a database account permitted to
          <strong>CREATE SCHEMA</strong> and <strong>CREATE TABLE</strong> — only your database
          administrator can grant those rights; this application cannot.
        </p>
      </div>

      <div class="banner info" style="margin-top:14px">
        <label class="row" style="font-size:13px">
          <input type="checkbox" id="c_useMaterialized" style="width:auto">
          <strong>Use pre-materialized transitions</strong>
        </label>
        <p class="subtle" style="margin:6px 0 12px">
          Reads the process map from a prebuilt <code>TRANSITIONS_RAW</code> table instead of running the
          windowed query live — much faster for interactive filtering on large logs. It falls back to the
          live query until the table is built, so rebuild it after each load of <code>JOURNEYS</code>.
        </p>
        <div class="row" style="align-items:center; gap:12px; flex-wrap:wrap">
          <button class="btn" id="c_rebuildBtn" onclick="rebuildTransitions()">Rebuild now</button>
          <span id="c_matStatus" class="subtle"></span>
          <span id="c_matResult" class="muted"></span>
        </div>

        <details id="c_apiBox" style="margin-top:14px">
          <summary style="cursor:pointer; font-size:13px; font-weight:600">Rebuild from a script (API)</summary>
          <div style="margin-top:10px">
            <p class="subtle" style="margin:0 0 10px">
              Let a scheduler (cron / ETL) rebuild <em>this connection</em> right after loading its
              <code>JOURNEYS</code>, without an admin login. The token below is scoped to this connection only,
              and calls are rate-limited.
            </p>
            <div class="row" style="align-items:center; gap:10px; flex-wrap:wrap">
              <span id="rtStatus" class="subtle"></span>
              <span class="spacer"></span>
              <button class="btn small" onclick="generateRebuildToken()">Generate / rotate token</button>
              <button class="btn small danger" id="rtRevokeBtn" onclick="revokeRebuildToken()">Revoke</button>
            </div>
            <div id="rtValue" style="margin-top:8px"></div>
            <div class="codeblock-wrap" style="margin-top:10px">
              <button class="copy-btn" onclick="copyCurl()" title="Copy to clipboard" aria-label="Copy curl command">📋</button>
              <pre id="api_curl" class="codeblock" style="white-space:pre-wrap; word-break:break-all"></pre>
            </div>
            <p class="subtle" style="margin:6px 0 0">
              The token is shown once — copy it now; only its hash is stored. The <code>Bearer</code> value appears
              in the command only while the token is visible above, then shows <code>&lt;token&gt;</code>.
              <code>-k</code> skips the self-signed TLS check.
            </p>
          </div>
        </details>
      </div>
    </div>
  </div>
  </div><!-- /tab-connections -->

  <div class="tabpanel" id="tab-ldap">
  <div class="card">
    <h2>Directory (LDAP / Active Directory)</h2>
    <p class="muted" style="margin-top:0">When enabled, the <strong>main application</strong> also accepts sign-ins from an
      LDAP directory (search&nbsp;+&nbsp;bind). Directory users are created here automatically on first login as
      plain, enabled users — grant them a role or database connections like any other user. Local accounts always keep
      working.</p>
    <div class="banner info" style="display:flex; flex-direction:column; align-items:flex-start; gap:10px">
      <label class="row" style="font-size:13px; cursor:pointer">
        <input type="checkbox" id="l_enabled" style="width:auto"> Enable directory sign-in for the main app
      </label>
      <label class="row" style="font-size:13px; cursor:pointer">
        <input type="checkbox" id="l_adminLogin" style="width:auto"> Also allow directory sign-in to <strong>this admin interface</strong>
      </label>
      <p class="subtle" style="margin:0">A directory account can only reach the admin interface once it has been promoted to
        <strong>admin</strong> in the Users tab. Local administrators always work regardless of this setting.</p>
    </div>
    <div class="grid2" style="margin-top:14px; border-bottom:1px solid var(--border); padding-bottom:18px; align-items:stretch">
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
        <div class="row" style="margin-top:auto">
          <div class="field" style="flex:1"><label>Login attribute</label><input type="text" id="l_loginAttr" placeholder="uid"></div>
          <div class="field" style="flex:1"><label>Email attribute</label><input type="text" id="l_emailAttr" placeholder="mail"></div>
          <div class="field" style="flex:1"><label>Name attribute</label><input type="text" id="l_displayAttr" placeholder="cn"></div>
        </div>
      </div>
    </div>
    <div class="banner info" style="margin-top:16px">
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

  <div class="tabpanel" id="tab-logging">
  <div class="card">
    <div class="banner info" style="display:flex; flex-wrap:wrap; align-items:center; gap:12px">
      <label class="row" style="font-size:13px; gap:6px">Max level logged
        <select id="logLevel"></select>
      </label>
      <label class="row" style="font-size:13px; gap:6px">New file after
        <input type="number" id="logMaxMb" min="1" max="1000" step="1" style="width:80px"> MB
      </label>
      <button class="btn small" onclick="saveLogConfig()">Save</button>
      <span class="subtle">Records this severity and everything above it in the ladder
        (INFO → USAGE → WARN → ERROR → DEBUG; DEBUG logs everything).</span>
    </div>

    <div class="row" style="flex-wrap:wrap; gap:8px; margin:12px 0 8px; align-items:center">
      <div class="seg" id="logSeverityFilter"></div>
      <input type="text" id="logIp" placeholder="Client IP" style="width:130px" oninput="scheduleLogReload()">
      <select id="logOp" onchange="logResetReload()"><option value="">All operations</option></select>
      <input type="text" id="logSearch" placeholder="Search message (regex / wildcards)…"
        style="flex:1; min-width:180px" oninput="scheduleLogReload()">
      <button class="btn small" onclick="loadLogs()">↻ Refresh</button>
      <button class="btn small" onclick="downloadLog()">⬇ Download</button>
      <button class="btn small danger" onclick="clearLogs()">Clear</button>
    </div>
    <div id="logTable"></div>
    <div id="logModal" class="log-ov" hidden onclick="if(event.target===this)closeLogModal()">
      <div class="log-ov-box">
        <div class="row" style="justify-content:space-between; align-items:center; margin-bottom:12px">
          <strong style="font-size:14px">Log entry</strong>
          <button class="btn small" onclick="closeLogModal()">Close</button>
        </div>
        <div id="logModalBody"></div>
      </div>
    </div>
    <div class="row" id="logPager"
      style="justify-content:space-between; align-items:center; gap:12px; margin-top:12px; font-size:13px">
      <label class="row subtle" style="gap:6px">Per page
        <select id="logPerPage" onchange="setLogPerPage()">
          <option value="10">10</option>
          <option value="25" selected>25</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
      </label>
      <span class="row" id="logPagerNav" style="gap:8px; align-items:center"></span>
    </div>
  </div>
  </div><!-- /tab-logging -->

  <div class="tabpanel" id="tab-backup">
  <div class="card">
    <h2>Export</h2>
    <p class="muted" style="font-size:13px; margin:0 0 12px">Exports connections, filter presets,
      happy paths, target norms, node layouts, LLM prompt templates and app preferences as a single
      JSON file (byte-compatible with the app's backup format).</p>
    <div class="col" style="gap:8px; max-width:520px">
      <label class="row" style="gap:8px; font-size:14px"><input type="checkbox" id="bkUsername" checked style="width:auto"> Include database usernames</label>
      <label class="row" style="gap:8px; font-size:14px"><input type="checkbox" id="bkPasswords" style="width:auto" onchange="updateBackupWarn()"> Include database passwords</label>
      <label class="row" style="gap:8px; font-size:14px"><input type="checkbox" id="bkLlmKey" style="width:auto" onchange="updateBackupWarn()"> Include LLM API keys</label>
      <div id="bkSecretWarn" class="banner warn" style="display:none">⚠ Secrets will be written in plain text unless you set an encryption password below.</div>
      <div class="field"><label>Encryption password (optional, AES-256-GCM)</label>
        <input type="password" id="bkExportPw" autocomplete="new-password" oninput="updateBackupWarn()" style="max-width:320px"></div>
      <button class="btn primary" style="align-self:flex-start" onclick="exportBackup()">⬇ Export backup</button>
    </div>
  </div>
  <div class="card">
    <h2>Restore</h2>
    <p class="muted" style="font-size:13px; margin:0 0 12px">Load a backup file, review its contents,
      then choose what to restore. This overwrites the corresponding settings.</p>
    <div class="col" style="gap:10px; max-width:520px">
      <div class="field"><label>Backup file</label>
        <input type="file" id="bkFile" accept=".json,application/json" onchange="pickBackupFile()"></div>
      <div class="field"><label>Password (if the backup is encrypted)</label>
        <div class="row" style="gap:8px">
          <input type="password" id="bkRestorePw" autocomplete="off" style="max-width:280px">
          <button class="btn small" onclick="inspectBackup()">Inspect</button>
        </div></div>
      <div id="bkError" class="banner warn" style="display:none"></div>
      <div id="bkSummary" style="display:none">
        <hr style="border:none; border-top:1px solid var(--border-soft); margin:8px 0">
        <div style="font-weight:600; margin-bottom:6px">Backup contents</div>
        <div id="bkSummaryBody" class="col" style="gap:3px; font-size:13px; color:var(--muted)"></div>
        <div style="font-weight:600; margin:14px 0 6px">Restore</div>
        <div id="bkRestoreOpts" class="col" style="gap:6px"></div>
        <button class="btn primary danger" style="align-self:flex-start; margin-top:12px" onclick="restoreBackup()">Restore</button>
      </div>
    </div>
  </div>
  </div><!-- /tab-backup -->

  <div class="tabpanel" id="tab-customize">
  <div class="card">
    <h2>Customize</h2>
    <p class="muted" style="margin-top:0">Branding and appearance for the application and this admin interface. More options to come.</p>

    <h2 style="font-size:14px; margin-top:18px">Login Page</h2>
    <p class="subtle" style="margin-top:0">Background for both sign-in pages (the main app and this admin interface). The default keeps the built-in theme colour, which follows light / dark mode.</p>

    <div class="col" style="gap:10px; max-width:520px; margin-top:12px">
      <label class="row" style="font-size:14px; cursor:pointer"><input type="radio" name="loginBg" value="default" id="lbg_default" style="width:auto" onchange="onLoginBgType()"> Default theme colour</label>
      <label class="row" style="font-size:14px; cursor:pointer"><input type="radio" name="loginBg" value="color" id="lbg_color" style="width:auto" onchange="onLoginBgType()"> Solid colour</label>
      <div class="row" id="lbg_colorRow" style="gap:10px; align-items:center; padding-left:26px; display:none">
        <input type="color" id="lbg_colorPicker" value="#f2f2f7" style="width:48px; height:32px; padding:2px" onchange="syncLoginColor('picker')">
        <div class="field" style="margin:0"><input type="text" id="lbg_colorHex" placeholder="#f2f2f7" style="width:120px" oninput="syncLoginColor('hex')"></div>
      </div>
      <label class="row" style="font-size:14px; cursor:pointer"><input type="radio" name="loginBg" value="image" id="lbg_image" style="width:auto" onchange="onLoginBgType()"> Background image</label>
      <div class="col" id="lbg_imageRow" style="gap:8px; padding-left:26px; display:none">
        <input type="file" id="lbg_imageFile" accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml" onchange="pickLoginImage()">
        <p class="subtle" style="margin:0">PNG, JPEG, GIF, WebP or SVG, up to ~3&nbsp;MB. The image is scaled to cover the page.</p>
      </div>
    </div>

    <div style="margin-top:16px">
      <div class="subtle" style="margin-bottom:6px">Preview</div>
      <div id="lbg_preview" style="width:100%; max-width:520px; height:150px; border-radius:10px; border:1px solid var(--border-soft); background:var(--bg); display:grid; place-items:center">
        <div style="padding:10px 16px; border-radius:10px; background:rgba(255,255,255,.82); color:#000; font-size:13px; box-shadow:0 6px 20px rgba(0,0,0,.18)">Sign in</div>
      </div>
    </div>

    <div class="row" style="margin-top:16px; align-items:center; gap:12px">
      <button class="btn primary" onclick="saveLoginBg()">Save</button>
      <span id="lbg_result" class="subtle"></span>
    </div>
  </div>
  </div><!-- /tab-customize -->
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

// ── Appearance (System / Light / Dark), analog to the main app ────────────────
const THEME_KEY = 'pmw_admin_theme';
function readThemePref() { try { return localStorage.getItem(THEME_KEY) || 'system'; } catch (e) { return 'system'; } }
function applyTheme(pref) {
  const dark = pref === 'system'
    ? matchMedia('(prefers-color-scheme: dark)').matches
    : pref === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}
function markThemeSel(pref) {
  const seg = $('themeSeg'); if (!seg) return;
  seg.querySelectorAll('button').forEach((b) =>
    b.classList.toggle('sel', b.getAttribute('data-theme-choice') === pref));
}
function setTheme(pref) {
  try { localStorage.setItem(THEME_KEY, pref); } catch (e) { /* private mode */ }
  applyTheme(pref); markThemeSel(pref);
}
function initTheme() {
  const pref = readThemePref();
  applyTheme(pref); markThemeSel(pref);
  try {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (readThemePref() === 'system') applyTheme('system');
    });
  } catch (e) { /* Safari < 14 */ }
}
initTheme();

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
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmtDate = (s) => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? '—' : d.toLocaleString(); };

let BUILTIN_ADMIN = '';
async function loadSession() {
  const s = await api('/api/session');
  BUILTIN_ADMIN = s.builtinAdmin || '';
  $('who').textContent = s.username;
  $('defaultWarn').innerHTML = s.defaultPasswordActive
    ? '<div class="banner warn">⚠️ The <strong>Administrator</strong> account is still using its default password. Change it now with “Change password”.</div>'
    : '';
  $('requireLogin').checked = !!s.requireLogin;
  $('requireLoginHint').textContent = s.requireLogin
    ? 'Users must sign in.' : 'The app is open — no sign-in required.';
  const idle = s.idleTimeoutMins || 0;
  $('idleTimeout').value = idle;
  $('idleTimeoutHint').textContent = idle > 0
    ? 'Idle sessions are signed out after ' + idle + ' min.' : 'Disabled — sessions never time out on inactivity.';
  const adminIdle = s.adminIdleTimeoutMins || 0;
  $('adminIdleTimeout').value = adminIdle;
  $('adminIdleTimeoutHint').textContent = adminIdle > 0
    ? 'You are signed out of this admin after ' + adminIdle + ' min idle.'
    : 'Disabled — the admin session never times out on inactivity.';
  setAdminIdle(adminIdle);
  const maxFail = s.maxFailedLogins || 0;
  $('maxFailedLogins').value = maxFail;
  $('maxFailedLoginsHint').textContent = maxFail > 0
    ? 'Accounts (incl. the Administrator) are disabled after ' + maxFail + ' failed sign-ins.'
    : 'Disabled — accounts are never locked on failed sign-ins.';
  renderLicense(s.license);
}
function renderLicense(lic) {
  const el = $('licenseStatus');
  if (!el) return;
  lic = lic || { state: 'missing', message: 'No license installed.' };
  const cls = lic.state === 'valid' ? 'banner ok'
    : lic.state === 'expired' ? 'banner warn' : 'banner err';
  let html = '<strong>' + esc(lic.message || lic.state) + '</strong>';
  if (lic.licensee) {
    html += '<div class="subtle" style="margin-top:4px">Licensed to ' + esc(lic.licensee)
      + (lic.expires ? ' · expires ' + esc(lic.expires) : '')
      + (lic.issued ? ' · issued ' + esc(lic.issued) : '') + '</div>';
  }
  el.className = cls;
  el.innerHTML = html;
}
async function uploadLicense() {
  const f = $('licenseFile').files[0];
  if (!f) { toast('Choose a license file first', true); return; }
  const out = $('licenseResult');
  try {
    const content = await _fileToBase64(f);
    const r = await api('/api/license', { method: 'POST', body: JSON.stringify({ content }) });
    renderLicense(r.license);
    if (out) out.innerHTML = '<div class="banner ok">License installed. The backend applies it within a few seconds.</div>';
    $('licenseFile').value = '';
    toast('License installed');
  } catch (e) {
    if (out) out.innerHTML = '<div class="banner err">' + esc(e.message) + '</div>';
    toast(e.message, true);
  }
}
async function deleteLicense() {
  if (!confirm('Delete the installed license?\n\nThe compute backend drops to Demo Mode and stops after the grace period unless a new license is applied.')) return;
  const out = $('licenseResult');
  try {
    const r = await api('/api/license', { method: 'DELETE' });
    renderLicense(r.license);
    if (out) out.innerHTML = r.removed
      ? '<div class="banner warn">License removed — the backend is now in Demo Mode.</div>'
      : '<div class="banner info">No license was installed.</div>';
    toast(r.removed ? 'License deleted' : 'No license installed');
  } catch (e) {
    if (out) out.innerHTML = '<div class="banner err">' + esc(e.message) + '</div>';
    toast(e.message, true);
  }
}
async function saveMaxFailedLogins() {
  const count = Math.max(0, parseInt($('maxFailedLogins').value, 10) || 0);
  try { await api('/api/access/max-failed-logins', { method: 'POST', body: JSON.stringify({ count }) });
    toast('Failed-sign-in lockout updated'); await loadSession(); }
  catch (e) { toast(e.message, true); }
}
async function saveRequireLogin() {
  const requireLogin = $('requireLogin').checked;
  try { await api('/api/access/require-login', { method: 'POST', body: JSON.stringify({ requireLogin }) });
    toast('Access updated'); await loadSession(); }
  catch (e) { toast(e.message, true); $('requireLogin').checked = !requireLogin; }
}
async function saveIdleTimeout() {
  const minutes = Math.max(0, parseInt($('idleTimeout').value, 10) || 0);
  try { await api('/api/access/idle-timeout', { method: 'POST', body: JSON.stringify({ minutes }) });
    toast('Auto sign-out updated'); await loadSession(); }
  catch (e) { toast(e.message, true); }
}
async function saveAdminIdleTimeout() {
  const minutes = Math.max(0, parseInt($('adminIdleTimeout').value, 10) || 0);
  try { await api('/api/access/admin-idle-timeout', { method: 'POST', body: JSON.stringify({ minutes }) });
    toast('Admin auto sign-out updated'); await loadSession(); }
  catch (e) { toast(e.message, true); }
}

// ── Admin idle auto-logout ────────────────────────────────────────────────
// Mirrors the app's IdleLogout: after N minutes without activity, sign out of
// the admin. Activity slides the server window (a throttled /api/session poll).
let ADMIN_IDLE_MINS = 0, _idleTimer = null, _lastPing = 0, _idleWired = false;
function _resetIdle() {
  clearTimeout(_idleTimer);
  if (!ADMIN_IDLE_MINS) return;
  _idleTimer = setTimeout(_onIdleTimeout, ADMIN_IDLE_MINS * 60000);
  const now = Date.now();
  if (now - _lastPing > 30000) { _lastPing = now; fetch('/api/session').catch(() => {}); }
}
async function _onIdleTimeout() {
  try { await fetch('/logout', { method: 'POST' }); } catch (e) { /* cookie expires anyway */ }
  location.href = '/login?inactivity=1';
}
function setAdminIdle(mins) {
  ADMIN_IDLE_MINS = mins || 0;
  if (!_idleWired) {
    _idleWired = true;
    ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'].forEach(ev =>
      document.addEventListener(ev, _resetIdle, { passive: true }));
  }
  _resetIdle();
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
    toast('TLS mode saved — restart in App Control to apply'); await loadTls(); }
  catch (e) { toast(e.message, true); }
}
document.querySelectorAll('#tlsSeg button').forEach(b => b.onclick = () => {
  document.querySelectorAll('#tlsSeg button').forEach(x => x.classList.remove('sel'));
  b.classList.add('sel');
});
async function restartServer() {
  if (!confirm('Restart now?\n\nThe app AND this admin interface rebind their HTTP/HTTPS listeners with the current TLS settings. Anyone using the app will briefly disconnect, and if you changed the TLS mode this admin page may move between :8090 (HTTP) and :8453 (HTTPS).')) return;
  const out = $('restartResult');
  if (out) out.innerHTML = '<span class="muted">Restarting…</span>';
  try { const r = await api('/api/restart', { method: 'POST' });
    toast('Restarting (app pid ' + r.pid + (r.adminPid ? ', admin pid ' + r.adminPid : '') + ')…');
    if (out) out.innerHTML = '<div class="banner info">Restart signalled. Listeners rebind with the current TLS plan; reconnect on the new address if this page stops responding.</div>';
    // Give it a moment to rebind, then refresh the endpoint view.
    setTimeout(() => loadTls().catch(() => {}), 1500);
  } catch (e) { if (out) out.innerHTML = ''; toast(e.message, true); }
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
        (active ? '' : `<button class="btn small" data-id="${esc(c.id)}" onclick="activateCert(this.dataset.id)">Activate</button> `) +
        `<a class="btn small" href="/api/certs/${encodeURIComponent(c.id)}/download">Download</a> ` +
        `<button class="btn small danger" data-id="${esc(c.id)}" data-name="${esc(c.name)}" onclick="deleteCert(this.dataset.id, this.dataset.name)">Delete</button>` +
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
    await loadTls(); }
  catch (e) { toast(e.message, true); }
}
async function uploadCert() {
  const body = { name: $('u_name').value, certPem: $('u_cert').value, keyPem: $('u_key').value, activate: $('u_activate').checked };
  try { await api('/api/certs/upload', { method: 'POST', body: JSON.stringify(body) });
    toast('Certificate uploaded'); $('u_name').value = $('u_cert').value = $('u_key').value = '';
    await loadTls(); }
  catch (e) { toast(e.message, true); }
}
async function activateCert(id) {
  try { await api('/api/certs/' + id + '/activate', { method: 'POST' });
    toast('Certificate activated'); await loadTls(); }
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
// The role cell. An administrator always carries a second base role (power, or
// plain user) — those two important roles share one badge whose colour floats
// between them. A non-admin shows a single pill (power supersedes user).
function roleBadge(u) {
  const BLUE = 'var(--accent)', TEAL = '#30d1c4', GREY = '#8e8e93';
  const POWER_TITLE = 'May create and manage their own database connections from the app';
  if (u.isAdmin) {
    const second = u.isPower ? 'power' : 'user';
    const c2 = u.isPower ? TEAL : GREY;
    const title = u.isPower ? 'Administrator, and a power user' : 'Administrator';
    return `<span class="pill combo" style="--c1:${BLUE}; --c2:${c2}" title="${title}">` +
      `admin<span class="sep">·</span>${second}</span>`;
  }
  if (u.isPower) return `<span class="pill power" title="${POWER_TITLE}">power</span>`;
  return '<span class="pill neutral">user</span>';
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
    // The built-in Administrator cannot be disabled or demoted (enforced server-side too).
    const isBuiltin = !!BUILTIN_ADMIN && u.username.toLowerCase() === BUILTIN_ADMIN.toLowerCase();
    const nameCell = `<div class="u-ident"><strong>${esc(u.username)}</strong>` +
      (u.displayName ? `<span class="u-real">${esc(u.displayName)}</span>` : '') + `</div>`;
    h += `<tr><td>${nameCell}</td>` +
      `<td>${isLdap ? '<span class="pill ldap">LDAP</span>' : '<span class="pill neutral">local</span>'}</td>` +
      `<td>${roleBadge(u)}</td>` +
      `<td>${u.isEnabled
        ? '<span class="pill on">enabled</span>'
        : (u.loginLocked
            ? '<span class="pill off" title="Disabled after too many failed sign-ins — Unlock to restore.">locked</span>'
            : '<span class="pill off">disabled</span>')}</td>` +
      `<td class="muted">${fmtDate(u.lastLogin)}</td>` +
      `<td style="text-align:right; white-space:nowrap">` +
        (isBuiltin
          ? (u.loginLocked
              ? `<button class="btn small" data-user="${esc(u.username)}" onclick="toggleEnabled(this.dataset.user,true)">Unlock</button> `
              : '')
          : `<button class="btn small" data-user="${esc(u.username)}" onclick="toggleEnabled(this.dataset.user,${!u.isEnabled})">${u.isEnabled ? 'Disable' : (u.loginLocked ? 'Unlock' : 'Enable')}</button> `) +
        (isBuiltin ? '' : `<button class="btn small" data-user="${esc(u.username)}" onclick="toggleAdmin(this.dataset.user,${!u.isAdmin})">${u.isAdmin ? 'Remove admin' : 'Make admin'}</button> `) +
        (isBuiltin ? '' : `<button class="btn small" data-user="${esc(u.username)}" onclick="togglePower(this.dataset.user,${!u.isPower})">${u.isPower ? 'Remove power' : 'Make power'}</button> `) +
        (isLdap ? '' : `<button class="btn small" data-user="${esc(u.username)}" onclick="resetPw(this.dataset.user)">Reset password</button> `) +
        (isBuiltin ? '<span class="subtle" title="The built-in administrator cannot be disabled, demoted or deleted.">built-in admin</span>' : `<button class="btn small danger" data-user="${esc(u.username)}" onclick="delUser(this.dataset.user)">Delete</button>`) +
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
async function togglePower(u, isPower) {
  try { await api('/api/users/' + encodeURIComponent(u) + '/power', { method: 'POST', body: JSON.stringify({ isPower }) });
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
  if (name === 'logging') loadLogs().catch(e => toast(e.message, true));
  if (name === 'customize') loadCustomize().catch(e => toast(e.message, true));
}

// ── Customize (login page background) ───────────────────────────────────────
let _loginImage = ''; // data: URI of the current / newly-picked background image

async function loadCustomize() {
  const a = await api('/api/customize/login');
  _loginImage = a.image || '';
  const type = ['default', 'color', 'image'].includes(a.type) ? a.type : 'default';
  $('lbg_' + type).checked = true;
  const hex = /^#[0-9a-fA-F]{6}$/.test(a.color) ? a.color : '#f2f2f7';
  $('lbg_colorHex').value = hex;
  $('lbg_colorPicker').value = hex;
  onLoginBgType();
}

function onLoginBgType() {
  const type = (document.querySelector('input[name="loginBg"]:checked') || {}).value || 'default';
  $('lbg_colorRow').style.display = type === 'color' ? 'flex' : 'none';
  $('lbg_imageRow').style.display = type === 'image' ? 'flex' : 'none';
  updateLoginPreview();
}

function syncLoginColor(from) {
  if (from === 'picker') $('lbg_colorHex').value = $('lbg_colorPicker').value;
  else if (/^#[0-9a-fA-F]{6}$/.test($('lbg_colorHex').value)) $('lbg_colorPicker').value = $('lbg_colorHex').value;
  updateLoginPreview();
}

function pickLoginImage() {
  const f = $('lbg_imageFile').files[0];
  if (!f) return;
  if (f.size > 3 * 1024 * 1024) { toast('Image is too large (max ~3 MB)', true); $('lbg_imageFile').value = ''; return; }
  const r = new FileReader();
  r.onload = () => { _loginImage = r.result; updateLoginPreview(); };
  r.onerror = () => toast('Could not read the image', true);
  r.readAsDataURL(f);
}

function updateLoginPreview() {
  const type = (document.querySelector('input[name="loginBg"]:checked') || {}).value || 'default';
  const el = $('lbg_preview');
  if (type === 'color') el.style.background = $('lbg_colorHex').value || 'var(--bg)';
  else if (type === 'image' && _loginImage) el.style.background = 'var(--bg) url("' + _loginImage + '") center / cover no-repeat';
  else el.style.background = 'var(--bg)';
}

async function saveLoginBg() {
  const type = (document.querySelector('input[name="loginBg"]:checked') || {}).value || 'default';
  const body = { type: type, color: $('lbg_colorHex').value };
  if (type === 'image') {
    if (!_loginImage) { toast('Choose a background image first', true); return; }
    body.image = _loginImage;
  }
  $('lbg_result').textContent = '';
  try {
    const a = await api('/api/customize/login', { method: 'POST', body: JSON.stringify(body) });
    _loginImage = a.image || _loginImage;
    $('lbg_result').textContent = 'Saved — new sign-ins use it immediately.';
    toast('Login background saved');
  } catch (e) { $('lbg_result').textContent = ''; toast(e.message, true); }
}

// ── Logging ───────────────────────────────────────────────────────────────
// Default display filter: show INFO + USAGE, hide WARN / ERROR / DEBUG.
let LOG_LEVELS = [], LOG_SEVS = new Set(['INFO', 'USAGE']), _logInited = false, _logReloadTimer = null;
let _logPage = 1, _logPerPage = 25, _logTotal = 0, _logPages = 1, _logEntries = [];

function _logParams() {
  const p = new URLSearchParams();
  if (LOG_SEVS.size) p.set('severities', [...LOG_SEVS].join(','));
  const ip = $('logIp').value.trim(); if (ip) p.set('clientIp', ip);
  const op = $('logOp').value; if (op) p.set('operation', op);
  const q = $('logSearch').value.trim(); if (q) p.set('search', q);
  return p;
}
async function loadLogs() {
  const params = _logParams();
  params.set('page', String(_logPage));
  params.set('perPage', String(_logPerPage));
  const r = await api('/api/logs?' + params.toString());
  LOG_LEVELS = r.severities || [];
  if (!_logInited) {
    _logInited = true;
    $('logLevel').innerHTML = LOG_LEVELS.map(lv => `<option value="${lv}">${lv}</option>`).join('');
    $('logLevel').value = r.config.level;
    $('logMaxMb').value = Math.max(1, Math.round(r.config.maxBytes / 1000000));
  }
  renderSeverityChips();
  const curOp = $('logOp').value;
  $('logOp').innerHTML = '<option value="">All operations</option>' +
    (r.operations || []).map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
  $('logOp').value = curOp;
  _logPage = r.page; _logPerPage = r.perPage; _logTotal = r.total; _logPages = r.pages;
  _logEntries = r.entries || [];
  renderLogRows(_logEntries);
  renderLogPager();
}
// Filters/search span the entire log, so any filter change returns to page 1.
function logResetReload() { _logPage = 1; loadLogs().catch(e => toast(e.message, true)); }
function logGoto(p) { _logPage = Math.max(1, Math.min(p, _logPages)); loadLogs().catch(e => toast(e.message, true)); }
function setLogPerPage() {
  _logPerPage = parseInt($('logPerPage').value, 10) || 25;
  _logPage = 1;
  loadLogs().catch(e => toast(e.message, true));
}
function renderLogPager() {
  const nav = $('logPagerNav');
  if (!_logTotal) { nav.innerHTML = '<span class="subtle">No entries</span>'; return; }
  const start = (_logPage - 1) * _logPerPage + 1;
  const end = Math.min(_logTotal, _logPage * _logPerPage);
  nav.innerHTML =
    `<span class="subtle">${start}–${end} of ${_logTotal}</span>` +
    `<button class="btn small" ${_logPage <= 1 ? 'disabled' : ''} onclick="logGoto(1)">« First</button>` +
    `<button class="btn small" ${_logPage <= 1 ? 'disabled' : ''} onclick="logGoto(${_logPage - 1})">‹ Prev</button>` +
    `<span class="subtle">Page ${_logPage} / ${_logPages}</span>` +
    `<button class="btn small" ${_logPage >= _logPages ? 'disabled' : ''} onclick="logGoto(${_logPage + 1})">Next ›</button>` +
    `<button class="btn small" ${_logPage >= _logPages ? 'disabled' : ''} onclick="logGoto(${_logPages})">Last »</button>`;
}
function renderSeverityChips() {
  $('logSeverityFilter').innerHTML = LOG_LEVELS.map(lv =>
    `<button class="${LOG_SEVS.size === 0 || LOG_SEVS.has(lv) ? 'sel' : ''}" onclick="toggleLogSeverity('${lv}')">${lv}</button>`
  ).join('');
}
function toggleLogSeverity(lv) {
  if (LOG_SEVS.size === 0) LOG_LEVELS.forEach(l => LOG_SEVS.add(l));  // 'all' → explicit
  if (LOG_SEVS.has(lv)) LOG_SEVS.delete(lv); else LOG_SEVS.add(lv);
  if (LOG_SEVS.size === LOG_LEVELS.length) LOG_SEVS.clear();          // all selected → 'all'
  logResetReload();
}
function renderLogRows(entries) {
  if (!entries.length) { $('logTable').innerHTML = '<p class="subtle">No matching log entries.</p>'; return; }
  let h = '<table><thead><tr><th>Date</th><th>Time</th><th>Severity</th><th>Client IP</th><th>User</th><th>Message</th></tr></thead><tbody>';
  entries.forEach((e, i) => {
    h += `<tr onclick="showLogEntry(${i})" title="Click to view the full entry">` +
      `<td class="mono">${e.date}</td><td class="mono">${e.time}</td>` +
      `<td><span class="pill log-${e.severity.toLowerCase()}">${e.severity}</span></td>` +
      `<td class="mono">${esc(e.clientIp || '—')}</td><td>${esc(e.user || '—')}</td>` +
      `<td>${esc(e.message)}</td></tr>`;
  });
  $('logTable').innerHTML = h + '</tbody></table>';
}
// Minimal, dependency-free SQL pretty-printer: breaks before major clauses and
// indents subqueries by parenthesis depth. String literals are tokenised first
// so their contents (e.g. 'GROUP …') are never treated as keywords.
function tokenizeSql(s) {
  const toks = []; let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "'") {                       // 'string' with '' escapes
      let j = i + 1;
      while (j < s.length) { if (s[j] === "'") { if (s[j+1] === "'") { j += 2; continue; } j++; break; } j++; }
      toks.push({ t: 'str', v: s.slice(i, j) }); i = j;
    } else if (c === '(' || c === ')' || c === ',') { toks.push({ t: c, v: c }); i++; }
    else if (/\s/.test(c)) { i++; }
    else { let j = i; while (j < s.length && !/[\s(),']/.test(s[j])) j++; toks.push({ t: 'word', v: s.slice(i, j) }); i = j; }
  }
  return toks;
}
function formatSql(raw) {
  // Drop the "SQL:" / "SQL (12.3 ms):" trace prefix before formatting.
  const s = String(raw).replace(/^\s*SQL\s*(\([^)]*\))?\s*:\s*/i, '').trim();
  const toks = tokenizeSql(s);
  const CLAUSE = new Set(['SELECT','FROM','WHERE','GROUP','ORDER','HAVING','LIMIT','UNION','ON','VALUES','SET']);
  const JOINQ = new Set(['LEFT','RIGHT','INNER','FULL','CROSS','OUTER']);
  // Keywords that keep a space before '(' (so it reads "IN (…)"); anything else
  // before '(' is treated as a function call and attaches ("COUNT(*)").
  const PAREN_SPACE = new Set(['IN','AND','OR','NOT','ON','EXISTS','ANY','ALL','SELECT','VALUES','BETWEEN','WHEN','THEN','ELSE','UNION','WHERE','HAVING']);
  const lines = []; let line = '', indent = 0, lineIndent = 0, betweenPending = false;
  const stack = [];
  const add = (t) => {
    if (line === '') { lineIndent = indent; line = t; }
    else if (line.endsWith('(')) line += t;
    else line += ' ' + t;
  };
  const flush = () => { if (line !== '') { lines.push('  '.repeat(Math.max(0, lineIndent)) + line); line = ''; } };
  for (let k = 0; k < toks.length; k++) {
    const tk = toks[k];
    const up = tk.t === 'word' ? tk.v.toUpperCase() : '';
    const prevUp = k > 0 && toks[k-1].t === 'word' ? toks[k-1].v.toUpperCase() : '';
    const nextUp = k + 1 < toks.length && toks[k+1].t === 'word' ? toks[k+1].v.toUpperCase() : '';
    if (tk.t === '(') {
      const sub = nextUp === 'SELECT';
      if (line !== '' && /\w$/.test(line) && !PAREN_SPACE.has(prevUp)) line += '(';  // function call
      else add('(');
      stack.push(sub); indent++; if (sub) flush(); continue;
    }
    if (tk.t === ')') { const sub = stack.pop(); indent = Math.max(0, indent - 1); if (sub) { flush(); add(')'); } else line += ')'; continue; }
    if (tk.t === ',') { line += ','; continue; }
    if (tk.t === 'str') { add(tk.v); continue; }
    if (up === 'BETWEEN') { betweenPending = true; add(tk.v); continue; }
    if ((up === 'AND' || up === 'OR') && prevUp !== 'CREATE') {
      if (up === 'AND' && betweenPending) { betweenPending = false; add(tk.v); continue; }  // "BETWEEN x AND y"
      flush(); add(tk.v); continue;
    }
    if (up === 'JOIN' && JOINQ.has(prevUp)) { add(tk.v); continue; }
    if (JOINQ.has(up) || up === 'JOIN') { flush(); add(tk.v); continue; }
    if (CLAUSE.has(up)) { if (!(up === 'SELECT' && line === '')) flush(); add(tk.v); continue; }
    add(tk.v);
  }
  flush();
  return lines.join('\n');
}
function showLogEntry(i) {
  const e = _logEntries[i];
  if (!e) return;
  const field = (k, v) =>
    `<div style="display:flex; gap:12px; margin-bottom:5px">` +
    `<span class="subtle" style="min-width:92px">${k}</span>` +
    `<span class="mono">${esc(v || '—')}</span></div>`;
  // The verbose SQL trace (operation 'sql') is pretty-printed and its execution
  // time surfaced as a field; anything else is shown verbatim.
  const isSql = e.operation === 'sql';
  const durMatch = isSql && e.message.match(/^\s*SQL\s*\(([^)]+)\)\s*:/i);
  const body = isSql ? formatSql(e.message) : e.message;
  $('logModalBody').innerHTML =
    field('Date', e.date) + field('Time', e.time) + field('Severity', e.severity) +
    field('Client IP', e.clientIp) + field('User', e.user) + field('Operation', e.operation) +
    (durMatch ? field('Execution time', durMatch[1]) : '') +
    `<div class="subtle" style="margin:12px 0 4px">${isSql ? 'SQL' : 'Message'}</div>` +
    `<pre class="codeblock" style="white-space:pre-wrap; word-break:break-word; max-height:52vh; overflow:auto">${esc(body)}</pre>`;
  $('logModal').hidden = false;
}
function closeLogModal() { $('logModal').hidden = true; }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('logModal').hidden) closeLogModal(); });
function scheduleLogReload() {
  clearTimeout(_logReloadTimer);
  _logReloadTimer = setTimeout(logResetReload, 300);
}
async function saveLogConfig() {
  const level = $('logLevel').value;
  const maxBytes = Math.max(1, parseInt($('logMaxMb').value, 10) || 1) * 1000000;
  try { await api('/api/logs/config', { method: 'POST', body: JSON.stringify({ level, maxBytes }) });
    toast('Logging config saved'); await loadLogs(); }
  catch (e) { toast(e.message, true); }
}
async function clearLogs() {
  if (!confirm('Clear the live log?\n\nThis empties the current log (rotated archive files are kept).')) return;
  try { await api('/api/logs/clear', { method: 'POST' }); toast('Log cleared'); _logPage = 1; await loadLogs(); }
  catch (e) { toast(e.message, true); }
}
function downloadLog() {
  window.location = '/api/logs/download?' + _logParams().toString();
}

// ── Backup / restore ──────────────────────────────────────────────────────
let _bkContent = '';
const BACKUP_RESTORE_OPTS = [
  ['appSettings', 'App settings & preferences'],
  ['connections', 'Connections & servers'],
  ['username', 'Usernames'],
  ['llmApiKey', 'LLM API keys'],
  ['passwords', 'Database passwords'],
  ['layouts', 'Saved node layouts'],
  ['norms', 'Target norms'],
  ['happyPaths', 'Happy paths'],
  ['filterPresets', 'Filter presets'],
];

function updateBackupWarn() {
  const wantSecrets = $('bkPasswords').checked || $('bkLlmKey').checked;
  $('bkSecretWarn').style.display = wantSecrets && !$('bkExportPw').value ? 'block' : 'none';
}

async function exportBackup() {
  try {
    const resp = await fetch('/api/backup/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        includeUsername: $('bkUsername').checked,
        includePasswords: $('bkPasswords').checked,
        includeLlmApiKey: $('bkLlmKey').checked,
        password: $('bkExportPw').value,
      }),
    });
    if (resp.status === 401) { location.href = '/login'; return; }
    if (!resp.ok) { toast('Export failed', true); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ProcessMining-Backup-' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
    URL.revokeObjectURL(url);
    toast('Backup exported');
  } catch (e) { toast(e.message, true); }
}

function _fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const bytes = new Uint8Array(r.result);
      let s = '';
      for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
      resolve(btoa(s));
    };
    r.onerror = reject;
    r.readAsArrayBuffer(file);
  });
}

async function pickBackupFile() {
  const f = $('bkFile').files[0];
  if (!f) return;
  _bkContent = await _fileToBase64(f);
  $('bkSummary').style.display = 'none';
  $('bkError').style.display = 'none';
  inspectBackup();
}

async function inspectBackup() {
  if (!_bkContent) { toast('Choose a backup file first', true); return; }
  $('bkError').style.display = 'none';
  try {
    const s = await api('/api/backup/inspect', {
      method: 'POST',
      body: JSON.stringify({ content: _bkContent, password: $('bkRestorePw').value }),
    });
    renderBackupSummary(s);
  } catch (e) {
    $('bkSummary').style.display = 'none';
    $('bkError').textContent = e.message;
    $('bkError').style.display = 'block';
  }
}

function renderBackupSummary(s) {
  const inc = [
    s.includesUsername ? 'usernames' : '—',
    s.includesPasswords ? 'passwords' : 'no passwords',
    s.includesLlmApiKey ? 'API keys' : 'no API keys',
  ];
  const rows = [
    'Created: ' + (s.createdAt || '—'),
    'Connections: ' + (s.connectionCount || 0),
    'Projects with settings: ' + (s.projectCount || 0),
    'Includes: ' + inc.join(', '),
  ];
  if (s.connectionNames && s.connectionNames.length) {
    rows.push('Overwrites: ' + s.connectionNames.join(', '));
  }
  $('bkSummaryBody').innerHTML = rows.map((r) => '<span>' + esc(r) + '</span>').join('');
  $('bkRestoreOpts').innerHTML = BACKUP_RESTORE_OPTS.map(
    (o) =>
      '<label class="row" style="gap:8px; font-size:14px"><input type="checkbox" class="bk-opt" data-key="' +
      o[0] + '" checked style="width:auto"> ' + esc(o[1]) + '</label>'
  ).join('');
  $('bkSummary').style.display = 'block';
}

async function restoreBackup() {
  const opts = {};
  document.querySelectorAll('.bk-opt').forEach((c) => { opts[c.dataset.key] = c.checked; });
  if (!confirm('Restore the selected items from this backup?\n\nThis overwrites the current settings.')) return;
  try {
    await api('/api/backup/restore', {
      method: 'POST',
      body: JSON.stringify({ content: _bkContent, password: $('bkRestorePw').value, options: opts }),
    });
    toast('Backup restored');
  } catch (e) { toast(e.message, true); }
}

// ── Directory (LDAP) ──────────────────────────────────────────────────────
async function loadLdap() {
  const c = await api('/api/ldap');
  $('l_enabled').checked = !!c.enabled;
  $('l_adminLogin').checked = !!c.adminLoginEnabled;
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
    adminLoginEnabled: $('l_adminLogin').checked,
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
        `<button class="btn small" data-id="${esc(c.id)}" onclick="editConnection(this.dataset.id)">Edit</button></td></tr>`;
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
  $('c_useMaterialized').checked = !!c.useMaterializedTransitions;
  renderMatStatus(c);
  $('c_matResult').textContent = '';
  $('c_rebuildBtn').disabled = !c.id;  // needs a saved connection to rebuild against
  $('c_rebuildBtn').title = c.id ? '' : 'Save the connection first';
  $('c_provisionBuildMat').checked = false;
  // Per-connection rebuild API: reset the shown-once token, collapse the box,
  // reflect whether this connection already has a token, and prime the example.
  LAST_TOKEN = '';
  $('rtValue').textContent = '';
  $('c_apiBox').open = false;
  renderTokenStatus(!!c.rebuildTokenSet);
  renderCurl();
  $('c_testResult').innerHTML = '';
  $('c_provisionResult').textContent = '';
  $('c_deleteBtn').style.display = c.id ? 'inline-flex' : 'none';
  $('connEditor').style.display = 'block';
  $('connEditor').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function renderMatStatus(c) {
  const m = c && c.materialization;
  if (!m) { $('c_matStatus').textContent = 'Not built yet — the live query is used until you rebuild.'; return; }
  if (m.ok) {
    $('c_matStatus').innerHTML = `Last built: ${esc(m.built_at || '—')} · ${Number(m.rows || 0).toLocaleString()} pairs.`;
  } else {
    $('c_matStatus').innerHTML = `<span style="color:var(--red)">Last rebuild failed: ${esc(m.error || 'unknown error')}</span>`;
  }
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
    useMaterializedTransitions: $('c_useMaterialized').checked,
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
async function provisionSchema() {
  const body = editorBody();
  if (!body.schema) { toast('Enter a schema name first.', true); return; }
  const req = {
    host: body.host, port: body.port, username: body.username,
    password: $('c_password').value, schema: body.schema, useTLS: body.useTLS,
    certModeRaw: body.certModeRaw, fingerprint: body.fingerprint,
    minRSAKeySizeBits: body.minRSAKeySizeBits,
    buildTransitions: $('c_provisionBuildMat').checked,
  };
  const out = $('c_provisionResult');
  out.textContent = 'Creating…'; out.style.color = '';
  try {
    const r = await api('/api/connections/provision-schema', { method: 'POST', body: JSON.stringify(req) });
    if (r.ok) {
      out.style.color = 'var(--green)';
      out.textContent = 'Created: ' + (r.created || []).join(', ') +
        (r.materialization ? (r.materialization.ok
          ? ` · transitions built (${Number(r.materialization.rows || 0).toLocaleString()} pairs)`
          : ` · transitions build failed: ${r.materialization.error || 'error'}`) : '');
    } else {
      out.style.color = 'var(--red)';
      out.textContent = r.error || 'Could not create the schema.';
    }
  } catch (e) {
    out.style.color = 'var(--red)';
    out.textContent = e.message;
  }
}

async function rebuildTransitions() {
  const id = $('c_id').value;
  if (!id) { toast('Save the connection first.', true); return; }
  const out = $('c_matResult');
  out.textContent = 'Rebuilding… (this runs the pairing once and may take a while)';
  out.style.color = '';
  try {
    const r = await api('/api/connections/' + encodeURIComponent(id) + '/rebuild-transitions', { method: 'POST' });
    if (r.ok) {
      out.style.color = 'var(--green)';
      out.textContent = `Built ${Number(r.rows || 0).toLocaleString()} pairs.`;
    } else {
      out.style.color = 'var(--red)';
      out.textContent = r.error || 'Rebuild failed.';
    }
    await loadConnections();
    const fresh = CONNS.find(x => x.id === id);
    if (fresh) renderMatStatus(fresh);
  } catch (e) { out.style.color = 'var(--red)'; out.textContent = e.message; }
}

// The plaintext token for the connection currently open in the editor, kept only
// while it is visible after generation; the curl example uses it verbatim until
// then, then reverts to a <token> placeholder.
let LAST_TOKEN = '';

function renderTokenStatus(isSet) {
  const saved = !!$('c_id').value;
  $('rtStatus').textContent = !saved ? 'save the connection first'
    : isSet ? 'a token is set for this connection' : 'no token set';
  $('rtRevokeBtn').style.display = (saved && isSet) ? 'inline-flex' : 'none';
}

function renderCurl() {
  const connId = $('c_id').value || '<connection-id>';
  const token = LAST_TOKEN ? `<span class="tok">${esc(LAST_TOKEN)}</span>` : '&lt;token&gt;';
  // -k skips the TLS certificate check (handy with the self-signed admin cert).
  $('api_curl').innerHTML =
    'curl -k -X POST \\\n' +
    `  -H "Authorization: Bearer ${token}" \\\n` +
    `  "${esc(window.location.origin)}/api/connections/${esc(connId)}/rebuild-transitions"`;
}

function copyCurl() {
  const text = $('api_curl').textContent;  // plaintext incl. the real token if shown
  navigator.clipboard.writeText(text).then(
    () => toast('curl command copied'),
    () => toast('Copy failed', true),
  );
}

async function generateRebuildToken() {
  const id = $('c_id').value;
  if (!id) { toast('Save the connection first.', true); return; }
  if (!confirm('Generate a new token for this connection? Any existing token stops working.')) return;
  try {
    const r = await api('/api/connections/' + encodeURIComponent(id) + '/rebuild-token', { method: 'POST' });
    LAST_TOKEN = r.token;
    $('rtValue').innerHTML = 'New token (copy it now — it is not shown again):<br>' +
      `<code style="user-select:all; word-break:break-all">${esc(r.token)}</code>`;
    renderTokenStatus(true);
    renderCurl();
    toast('Rebuild token generated');
  } catch (e) { toast(e.message, true); }
}
async function revokeRebuildToken() {
  const id = $('c_id').value;
  if (!id) return;
  if (!confirm("Revoke this connection's token? A scheduler using it will stop working.")) return;
  try {
    await api('/api/connections/' + encodeURIComponent(id) + '/rebuild-token', { method: 'DELETE' });
    LAST_TOKEN = '';
    $('rtValue').textContent = '';
    renderTokenStatus(false);
    renderCurl();
    toast('Rebuild token revoked');
  } catch (e) { toast(e.message, true); }
}

loadSession().then(loadTls).then(loadUsers).catch(() => {});

// ── Administration help overlay ─────────────────────────────────────────────
// Mirrors the "Administration" group in the main app's Help, so the same guidance
// is available here on the admin interface.
const ADMIN_HELP = [
  { id: 'interface', icon: '⚙︎', title: 'Admin Interface', html: `
    <h2>Admin Interface</h2>
    <p>This administration interface runs on its own port (8090 by default) and is where all security and access is configured. It has its own sign-in and admits administrators only.</p>
    <p>On first run it seeds a local administrator (Administrator / Administrator) and prompts you to change the password. Local admin accounts always work as a break-glass route.</p>
    <div class="note">Tabs: App Control, TLS / SSL, Users, Database Connections, Directory (LDAP), Logging, Backup and Customize.</div>` },
  { id: 'tls', icon: '🔒', title: 'TLS / SSL', html: `
    <h2>TLS / SSL</h2>
    <p>Choose how connections are accepted: Off (HTTP only), Optional (HTTP and HTTPS) or Required (HTTPS only). Generate a self-signed certificate or upload your own PEM cert and key, then mark one active.</p>
    <p>The app and this admin interface follow the same mode and share the active certificate. Changes take effect on restart (App Control &rarr; Restart app server); if a mode needs a certificate but none is active, each server falls back to HTTP so nothing is left unreachable.</p>
    <div class="note warn">Keep the active certificate valid &mdash; an expired certificate makes HTTPS clients refuse to connect.</div>` },
  { id: 'users', icon: '👤', title: 'Users & Sign-in', html: `
    <h2>Users &amp; Sign-in</h2>
    <p>Create local users, enable/disable access, grant or revoke the admin role, and reset passwords. Only enabled users can sign in. The <strong>Require sign-in</strong> toggle turns the login gate on or off (on by default) &mdash; with it off there is no user identity, so per-user settings and filter presets share one profile.</p>
    <p><strong>Failed sign-in lockout</strong> disables an account after N wrong passwords (0 = off); unlock it in the Users tab, or restart with PMW_RESET_LOCKOUTS=1. <strong>Power</strong> users manage their own connections and get the advanced-analysis views (Conformance Check, Happy Path, Simulation).</p>` },
  { id: 'connections', icon: '🗄️', title: 'Database Connections', html: `
    <h2>Database Connections</h2>
    <p>Define each connection (Exasol host, port, user, password, schema, TLS, and an optional OpenAI-compatible LLM server) and assign it to users; each user sees only the connections assigned to them. Use Test connection to verify the database and LLM before saving; a blank password/key keeps the stored value.</p>
    <p>&ldquo;Create schema &amp; tables&rdquo; provisions the process-mining schema and tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if missing.</p>
    <div class="note warn">Provisioning needs a DB account with CREATE SCHEMA / CREATE TABLE rights &mdash; only the database administrator can grant those.</div>` },
  { id: 'api', icon: '🔌', title: 'Rebuild from a script (API)', html: `
    <h2>Rebuild from a script (API)</h2>
    <p>Each connection can issue its own bearer token so an external caller (a cron job or ETL step) can trigger that connection&rsquo;s pre-materialized transitions rebuild without an admin login. Open the connection in <strong>Database Connections</strong>, expand &ldquo;Rebuild from a script (API)&rdquo;, and Generate / rotate or revoke the token there &mdash; it is shown <strong>once</strong> (copy it then); only its hash is stored, and the token is scoped to that connection only.</p>
    <p>Call <code>POST /api/connections/&lt;id&gt;/rebuild-transitions</code> with header <code>Authorization: Bearer &lt;token&gt;</code>. That section shows a copy-able <code>curl</code> example &mdash; pre-filled with your real token while it is still visible, and using <code>-k</code> to skip the TLS certificate check. Token-triggered rebuilds are rate-limited per connection and never overlap. Run it right after each load of <code>JOURNEYS</code>.</p>` },
  { id: 'directory', icon: '📇', title: 'Directory (LDAP)', html: `
    <h2>Directory (LDAP)</h2>
    <p>When enabled, the main-app login also accepts directory accounts via search + bind. Set the server URI, service-account bind DN/password, base DN, user filter and attributes. Test server connection checks the server alone; Test a user login also resolves and signs in an account.</p>
    <p>Directory users are created locally on first sign-in as plain, enabled accounts. The admin interface stays local-only unless you tick &ldquo;Also allow directory sign-in to this admin interface&rdquo; &mdash; and even then only after a directory account is promoted to admin.</p>
    <div class="note">Admin is never granted from the directory; a local admin must promote the user.</div>` },
  { id: 'logging', icon: '🧾', title: 'Logging', html: `
    <h2>Logging</h2>
    <p>A shared, structured log written by all three servers. Each entry records a timestamp, severity, client IP, user, operation and message. Severity is a cumulative ladder &mdash; INFO, USAGE, WARN, ERROR, DEBUG; pick the maximum level to record. Filter by severity, client IP or operation, search by regular expression, page through, and Download or Clear.</p>
    <p>Audited actions carry an operation tag: sign-in/out (login/logout), LDAP tests and config (ldap), certificate actions (tls), connection actions and connection/LLM tests (connection/llm-test), backup export/inspect/restore (backup) and login-page customization (customize). Deletions are logged as warnings.</p>
    <div class="note">A new log file starts once the live log passes the configured size; rotated files are saved under data/logs/.</div>` },
  { id: 'backup', icon: '💾', title: 'Backup & Restore', html: `
    <h2>Backup &amp; Restore</h2>
    <p>Export everything except the event data itself &mdash; connections, filter presets, node layouts, norms, happy paths, LLM prompts and app preferences &mdash; as one JSON file, and restore it again. Tick the boxes to include usernames, connection passwords and LLM API keys, and optionally protect the file with an AES-256-GCM password. Restore inspects the file and shows a summary before you pick which categories to apply.</p>
    <div class="note warn">Including secrets without an encryption password writes them in plain text &mdash; always set a password when the backup contains secrets.</div>` },
  { id: 'customize', icon: '🎨', title: 'Customize', html: `
    <h2>Customize</h2>
    <p>Set the login-page background for both sign-in pages (the app and this admin interface): keep the default theme colour, choose a solid colour, or upload a background image (PNG, JPEG, GIF, WebP or SVG, up to ~3 MB). A live preview shows the result before you save, and the choice applies to new sign-ins immediately.</p>
    <p>Over a background image the login panel turns semi-transparent so the image shows through while the text and fields stay legible.</p>` },
  { id: 'license', icon: '🔑', title: 'License & Demo Mode', html: `
    <h2>License &amp; Demo Mode</h2>
    <p>The application requires a valid license &mdash; upload it in App Control &rarr; License. Without one, the app runs in Demo Mode for a one-time grace period, then the compute backend stops until a license is applied. Uploading a valid license during the grace period cancels the shutdown.</p>
    <div class="note">The admin interface keeps working even when the backend has stopped, so you can always apply a license here.</div>` },
];
let _helpTopic = ADMIN_HELP[0].id;

function renderHelp() {
  const nav = $('helpNav'), content = $('helpContent');
  if (!nav || !content) return;
  nav.innerHTML = '';
  for (const t of ADMIN_HELP) {
    const b = document.createElement('button');
    b.className = t.id === _helpTopic ? 'sel' : '';
    b.innerHTML = '<span aria-hidden style="width:18px;display:inline-block">' + t.icon + '</span>' + esc(t.title);
    b.onclick = () => { _helpTopic = t.id; renderHelp(); };
    nav.appendChild(b);
  }
  const topic = ADMIN_HELP.find(t => t.id === _helpTopic) || ADMIN_HELP[0];
  content.innerHTML = topic.html;
  content.scrollTop = 0;
}
function openHelp() { renderHelp(); $('helpOv').hidden = false; }
function closeHelp() { $('helpOv').hidden = true; }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('helpOv').hidden) closeHelp(); });
"""
