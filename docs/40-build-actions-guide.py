#!/usr/bin/env python3
"""Generate the self-contained HTML guide for the Action Builder: the business-readable
action DSL, why it abstracts away raw SQL, and a big-SQL vs tiny-script example
("last log of a node").

Self-contained (CSS-drawn mocks, no screenshots). The example SQL mirrors what the
backend's _log_entries_sql actually produces.
Run:  python3 docs/40-build-actions-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "40-Action-Builder.html"
_BUILDER = pathlib.Path(__file__).name

_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

STEPS = [
    (
        "What the Action Builder is",
        "An <b>action</b> is a small, reusable command that a user runs straight from a node’s "
        "menu on the process map — “show me the last log entry for this step”, “open this "
        "sub-process’s transition table”. You author them in the <b>Action Builder</b> (a developer "
        "surface an admin switches on); they then appear in the right-click menu of the nodes you "
        "chose.",
        """<div class="mock"><div class="menu">
      <div class="mt">Payment Processing</div>
      <div class="mi act">⚡ Last log entry</div>
      <div class="mi act">⚡ Transition table (Count, Journey %)</div>
      <div class="mi">✎ Show Notes</div>
    </div><p class="cap">Actions (⚡) sit alongside the built-in node options — one click runs them
      against the process you have open.</p></div>""",
        None,
        '<span class="k">Experimental.</span> Actions are a developer/admin feature and still '
        "evolving; an administrator enables them under Admin → Actions.",
    ),
    (
        "Why a script, not raw SQL",
        "Every action ultimately becomes an Exasol query — but you don’t write SQL. You write a few "
        "lines of a <b>business-readable script</b>, and the app compiles it into <b>correct, safe, "
        "filter-aware SQL</b> for you. The script says <i>what</i> you want; the app handles the "
        "<i>how</i>.",
        None,
        [
            "<b>Node-relative.</b> <code>THIS</code>, <code>PREVIOUS</code>, <code>FOLLOWING</code> "
            "resolve to the node the action was run from — one script works from every node’s menu.",
            "<b>Filter-guided.</b> The query automatically inherits the chart’s current <b>date "
            "window</b> and filters — you never re-type a WHERE clause.",
            "<b>Safe by construction.</b> Values are escaped, the case id is MD5-hashed, results are "
            "capped — no SQL injection, no runaway queries.",
            "<b>Readable &amp; reusable.</b> An analyst can read, edit and share an action without "
            "knowing the table layout; the same script ports across projects and schemas.",
        ],
        None,
    ),
    (
        "Example — “last log of a node”",
        "This is the whole point. The action <b>“show the most recent event for the step I clicked”</b> "
        "is two lines of script — and expands into a fully-filtered SQL query you’d otherwise write by "
        "hand every time:",
        """<div class="mock"><div class="cmp">
      <div class="col"><div class="clab">The script you write</div>
        <pre class="code script"><span class="k1">SHOW</span> LAST LOG ENTRIES
<span class="k1">FROM</span> <span class="k2">NODE</span>(<span class="k3">THIS</span>)</pre></div>
      <div class="col"><div class="clab">The SQL it becomes</div>
        <pre class="code sql"><span class="s1">SELECT</span> EVENT_ID, STEP, EVENT_TIME,
       META_1, META_2, META_3
<span class="s1">FROM</span> JOURNEYS
<span class="s1">WHERE</span> PROJECT_ID = <span class="s2">'BOOKSTORE'</span>
  <span class="s1">AND</span> EVENT_TIME &gt;= <span class="s2">'2026-01-01 00:00:00'</span>
  <span class="s1">AND</span> EVENT_TIME &lt;  <span class="s2">'2026-02-01 00:00:00'</span>
  <span class="s1">AND</span> STEP <span class="s1">IN</span> (<span class="s2">'Payment Processing'</span>)
<span class="s1">ORDER BY</span> EVENT_TIME <span class="s1">DESC</span>, STEP_ID <span class="s1">DESC</span>
<span class="s1">LIMIT</span> 1</pre></div>
    </div><p class="cap">The app filled in everything: <b>'Payment Processing'</b> is whatever node you
      ran it from (<code>THIS</code>); the <b>date range</b> came from the chart’s current filter; the
      ordering, the LIMIT and the escaping are handled for you.</p></div>""",
        None,
        '<span class="k">That is the abstraction.</span> Change the date slider and the same two-line '
        "action returns the last entry for the new window — no SQL edit. Run it from a different node "
        "and <code>THIS</code> follows.",
    ),
    (
        "The building blocks",
        "A script is a handful of clauses (keywords are case-insensitive). Most actions use just "
        "<b>SHOW</b> and <b>FROM</b>:",
        """<div class="mock"><div class="mapwrap"><table class="tbl">
      <tr><th>Clause</th><th>What it does</th></tr>
      <tr><td class="cl">AVAILABILITY</td><td><code>ALL NODES</code> or a list of steps — where the
        action appears in the menu.</td></tr>
      <tr><td class="cl">SHOW</td><td><code>LAST [N] LOG ENTRIES</code>, or <code>TRANSITION TABLE
        WITH "COUNT","%JOURNEY%" [FOR LAST N LOG ENTRIES]</code>, or a cross-project
        <code>FLOWCHART</code>.</td></tr>
      <tr><td class="cl">FROM</td><td><code>NODE(THIS | PREVIOUS | FOLLOWING | ALL FOLLOWING |
        ALL PREVIOUS)</code> — the node set, relative to where it’s run.</td></tr>
      <tr><td class="cl">SORT</td><td><code>ASCENDING</code> / <code>DESCENDING</code> (optional).</td></tr>
      <tr><td class="cl">WHERE</td><td><code>EVENT_ID :: [id, …]</code> — restrict to specific cases
        (optional).</td></tr>
    </table></div></div>""",
        None,
        '<span class="k">More than log rows.</span> <code>SHOW TRANSITION TABLE WITH …</code> returns a '
        "metric table for the selected nodes, and <code>SHOW FLOWCHART FROM conn::project</code> opens "
        "another project’s map in a panel — all from the same tiny grammar.",
    ),
    (
        "Run it, save it, share it",
        "Set <b>AVAILABILITY</b> to the steps that should carry the action and save. It’s stored "
        "<b>per (connection, project)</b>, so everyone using that project sees it in the node menu. "
        "Running it inherits the chart’s live filters and shows the result as a table (or a flowchart "
        "panel).",
        """<div class="mock"><div class="row">
      <span class="node">Author in Action Builder</span><span class="arrow">→</span>
      <span class="node hub">Saved on the project</span><span class="arrow">→</span>
      <span class="node good">⚡ Runs from the node menu</span>
    </div><p class="cap">Write once, in business language; run anywhere the node appears, always scoped
      to what’s on screen.</p></div>""",
        None,
        None,
    ),
]

BEYOND = [
    "<b>Who.</b> Authoring actions is a developer/admin task (the Action Builder is on the admin "
    "port + 20 — :8110). Running a saved action is available to the users of the project.",
    "<b>Filter-guided, always.</b> An action never captures a fixed date range — it re-reads the "
    "chart’s current window each run, so it stays in step with what you’re looking at.",
    "<b>Safe by design.</b> The DSL compiles to escaped SQL with the case id MD5-hashed and the row "
    "count clamped; a script can’t inject SQL or dump an unbounded result.",
    "<b>Preview the SQL.</b> The builder can show the exact SQL a script compiles to, so you can "
    "confirm what will run before saving it.",
]

CSS = r"""
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415; --good:#1e9e5a;
  --codebg:#0f1524; --codefg:#cdd6f4;
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
.step ul li{margin:4px 0}
.step ul li code, .tbl code, .cap code{background:var(--bg);border-radius:4px;padding:0 5px;font-size:12.5px}
.tip{background:var(--tipbg);border-left:4px solid var(--tipbar);color:var(--tipink);
  border-radius:8px;padding:10px 14px;margin:0 0 16px;font-size:14.5px}
.tip b{color:var(--tipink)} .tip code{background:rgba(58,109,240,.1);border-radius:4px;padding:0 4px}
.tip .k{font-weight:700;margin-right:6px}
.beyond{background:var(--warnbg);border:1px solid #f0d9b8;border-left:4px solid var(--warnbar);
  color:var(--warnink);border-radius:14px;padding:20px 22px;margin:34px 0 0}
.beyond h2{margin:0 0 8px;font-size:19px;color:#7a4d13}
.beyond ul{margin:8px 0 0;padding-left:20px}
.beyond li{margin:4px 0}
.beyond code{background:rgba(0,0,0,.06);border-radius:4px;padding:0 4px}
.beyond .note{margin-top:12px;font-size:14.5px}
footer{color:var(--soft);font-size:13px;text-align:center;margin-top:34px}
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);font-weight:600;font-size:13px}
.node.hub{border-color:var(--accent);background:rgba(58,109,240,.08);color:var(--accent);font-weight:750}
.node.good{border-color:rgba(30,158,90,.5);background:rgba(30,158,90,.1);color:var(--good)}
.arrow{color:var(--soft);font-weight:700}
/* node menu */
.menu{width:300px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--card);
  box-shadow:0 10px 26px rgba(20,30,50,.16);font-size:14px}
.menu .mt{padding:8px 12px;font-weight:700;border-bottom:1px solid var(--line);background:rgba(0,0,0,.02)}
.menu .mi{padding:9px 12px;border-bottom:1px solid var(--line)}
.menu .mi:last-child{border-bottom:0}
.menu .mi.act{color:var(--accent);font-weight:600}
/* side-by-side script vs sql */
.cmp{display:flex;gap:14px;flex-wrap:wrap}
.cmp .col{flex:1;min-width:250px}
.clab{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;color:var(--soft);margin-bottom:6px}
.code{background:var(--codebg);color:var(--codefg);border-radius:10px;padding:12px 14px;margin:0;
  font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre;overflow-x:auto}
.code.script{border:1px solid rgba(58,109,240,.5);box-shadow:0 0 0 3px rgba(58,109,240,.12)}
.code .k1{color:#89b4fa;font-weight:700} .code .k2{color:#f5c2e7} .code .k3{color:#a6e3a1;font-weight:700}
.code .s1{color:#89b4fa} .code .s2{color:#a6e3a1}
/* clause table */
.mapwrap{overflow-x:auto}
.tbl{border-collapse:collapse;width:100%;font-size:13.5px;min-width:440px}
.tbl th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--soft);
  padding:5px 10px;border-bottom:2px solid var(--line)}
.tbl td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.tbl .cl{font-weight:750;color:var(--accent);white-space:nowrap;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
@media (prefers-color-scheme:dark){
  :root{--bg:#14171c;--card:#1d2127;--ink:#e7eaee;--soft:#a3adba;--line:#2c333c;
    --tipbg:#182338;--tipink:#cdd9f5;--warnbg:#2a2213;--warnink:#e9d3ac}
}
@media print{
  body{background:#fff}
  header.hero{box-shadow:none;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .step,.lead,.beyond,.mock{break-inside:avoid;box-shadow:none}
  .code{background:#0f1524 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
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
    return f'''<!doctype html>
<!-- Generated documentation page - open this file in a WEB BROWSER.
     It is NOT a script; to rebuild it run:  python3 docs/{_BUILDER} -->
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>40 - Action Builder</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Integration · Guide</span>
  <h1>Action Builder</h1>
  <p>Give users one-click actions in the node menu — "last log of this step", "this sub-process's
     transition table" — written in a few lines of a business-readable script that the app compiles
     into safe, filter-aware SQL. Write intent, not queries.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    An <b>action</b> runs from a node's right-click menu and returns a table or a flowchart. You
    author it in a tiny <b>script language</b> that abstracts away raw SQL: it is <b>node-relative</b>
    (<code>THIS</code>, <code>FOLLOWING</code>…), <b>filter-guided</b> (it inherits the chart's date
    window and filters), and <b>safe</b> (escaped, id-hashed, row-capped). The example below shows a
    two-line script becoming a full SQL query.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">The script language exists so the person who knows the <i>process question</i>
      can answer it themselves — without writing, or maintaining, the SQL underneath.</p>
  </div>

  <footer>Process Mining Demonstrator · Integration — Action Builder</footer>
</div>
</body></html>
'''


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
