#!/usr/bin/env python3
"""Generate the self-contained HTML guide for AI supported Documentation: how the
app turns the process on screen into a styled report — the LLM writes the analysis,
the app builds the document — and how to review, save and re-run it.

Every illustration is a small CSS-drawn mock — no screenshots — so the single .html
file is fully self-contained.
Run:  python3 docs/57-build-ai-doc-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "57-AI-Documentation.html"
_BUILDER = pathlib.Path(__file__).name

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each step: (title, body_html, mock_html | None, bullets | None, tip_html | None).
STEPS = [
    (
        "One click, a polished report",
        "AI supported Documentation turns the process you have on screen into a <b>styled, "
        "self-contained report</b> — a branded cover, an executive summary, a table of contents "
        "and chapters — ready to read or <b>Save as PDF</b>. A language model writes the "
        "<b>analysis</b>; the app builds the <b>document</b> around it.",
        """<div class="mock"><div class="row" style="gap:16px">
      <span class="chipbox">⛃ Your filtered process</span>
      <span class="big-arrow">⇒</span>
      <div class="report-mini"><div class="rm-bar"></div><div class="rm-t"></div>
        <div class="rm-l"></div><div class="rm-l short"></div></div>
    </div><p class="cap">The report reflects the <b>A-Chart</b> data and filters you currently
      have loaded.</p></div>""",
        None,
        '<span class="k">Open it</span> from the ☰ menu → <b>AI supported Documentation</b>.',
    ),
    (
        "What goes into it",
        "Before generating, the view shows exactly what will be included. The <b>A-Chart "
        "filters</b> define the dataset; your <b>Happy Paths</b> and <b>Conformance norms</b> "
        "enrich it — each is optional, and a card warns you when it’s empty.",
        """<div class="mock"><div class="notices">
      <div class="notice"><b>⛃ A-Chart filters in use</b><span>the reference dataset</span></div>
      <div class="notice"><b>🪧 Happy Path Conformance</b><span>2 paths will be evaluated</span></div>
      <div class="notice warn"><b>🛡️ Conformance Check</b><span>no norms — gap analysis skipped</span></div>
    </div></div>""",
        None,
        '<span class="k">Want those chapters?</span> Define Happy Paths and Conformance norms '
        "first — otherwise they are simply left out of the report.",
    ),
    (
        "The division of labour",
        "The model is handed <b>only</b> the transition table plus an analysis instruction, and "
        "returns <b>structured findings</b> (title, executive summary, sections). The app does all "
        "the <b>styling, layout and assembly</b>, and adds the chapters it computes itself. The "
        "LLM never sees raw personal data — just step names and counts.",
        """<div class="mock"><div class="flow3">
      <div class="box"><div class="lab">sent to the LLM</div>
        <table class="tbl"><tr><th>From</th><th>To</th><th>Count</th></tr>
          <tr><td>Login</td><td>Browse</td><td>12,480</td></tr>
          <tr><td>Browse</td><td>Cart</td><td>7,911</td></tr></table></div>
      <span class="big-arrow">→</span>
      <div class="box"><div class="lab">LLM returns</div>
        <code>{ "title", "summary",<br>&nbsp;&nbsp;"sections": [ … ] }</code></div>
      <span class="big-arrow">→</span>
      <div class="box"><div class="lab">app assembles</div>
        <div class="report-mini sm"><div class="rm-bar"></div><div class="rm-l"></div>
          <div class="rm-l short"></div></div></div>
    </div></div>""",
        None,
        None,
    ),
    (
        "What’s in the report",
        "The document opens with a branded cover — title, executive summary and your "
        "organisation’s <b>logo / accent colour</b> (set per project by an admin) — then a "
        "clickable table of contents and the chapters:",
        """<div class="mock"><div class="toc">
      <div class="toc-t">Contents</div>
      <ol>
        <li>Analysis <small>— the LLM’s findings &amp; tables</small></li>
        <li>Process flow <small>— the Sankey diagram</small></li>
        <li>Conformance – Gap Analysis <small>— if norms are defined</small></li>
        <li>Happy Path Conformance <small>— if paths are defined</small></li>
        <li>Journey Paths</li>
        <li>Notes</li>
      </ol>
    </div></div>""",
        [
            "The <b>Analysis</b> chapter is the LLM’s narrative plus any tables it produced.",
            "<b>Process flow, Conformance, Happy Path, Journey Paths, Notes</b> are computed by the "
            "app from your data — the LLM never touches those numbers.",
            "The <b>look, logo and which chapters appear</b> are configured per (connection, "
            "project) in the admin <b>Reporting</b> tab.",
        ],
        None,
    ),
    (
        "Review, save, re-run",
        "The report renders in an isolated frame. Use <b>Show prompt</b> to see exactly what was "
        "sent to the model, <b>⎙ Save as PDF</b> to print it through the browser, or "
        "<b>↻ Re-run</b> to regenerate after changing a filter.",
        """<div class="mock"><div class="toolbar">
      <span class="tb">Show prompt</span>
      <span class="tb prom">⎙ Save as PDF</span>
      <span class="tb">↻ Re-run</span>
    </div><p class="cap">The report footer names the exact model used —
      e.g. “analysis by <code>gpt-4o</code> · connection ‘Sales’”.</p></div>""",
        None,
        '<span class="k">Which LLM?</span> The active connection’s own LLM is used if it has one, '
        "otherwise the global default from the admin Reporting tab — read live, so an edited model "
        "applies to your very next report.",
    ),
]

BEYOND = [
    "<b>You need an LLM configured</b> — the connection’s own, or the global default. If none is "
    "reachable, the view tells you before you generate.",
    "<b>Privacy.</b> Only the aggregated transition table (step names + counts) and your "
    "instruction go to the model; individual journeys and identifiers never leave the app.",
    "<b>Self-contained output.</b> The report is a single HTML document (inline CSS, embedded "
    "diagram) rendered in a sandboxed frame — Save as PDF turns it into a shareable file.",
    "<b>Tailor it.</b> An admin can set a per-project analysis prompt, accent colour, logo and "
    "which chapters to include — see the Administration guide.",
]

CSS = """
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415;
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
code{background:var(--bg);border-radius:4px;padding:1px 5px;font-size:12.5px}
/* Mock illustrations */
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.big-arrow{color:var(--soft);font-size:20px;font-weight:700}
.chipbox{border:1px solid var(--line);border-radius:10px;padding:10px 14px;background:var(--card);
  font-weight:650;font-size:14px}
/* a tiny report cover */
.report-mini{width:120px;border:1px solid var(--line);border-radius:8px;padding:10px;
  background:var(--card);box-shadow:0 6px 16px rgba(20,30,50,.12)}
.report-mini.sm{width:96px;padding:8px}
.rm-bar{height:5px;border-radius:3px;background:linear-gradient(90deg,var(--accent),var(--accent2));
  margin-bottom:8px}
.rm-t{height:9px;width:70%;border-radius:3px;background:var(--ink);opacity:.8;margin-bottom:8px}
.rm-l{height:5px;border-radius:3px;background:var(--line);margin:5px 0}
.rm-l.short{width:60%}
/* notice cards */
.notices{display:flex;flex-direction:column;gap:8px;max-width:420px}
.notice{border:1px solid var(--line);border-radius:10px;padding:10px 13px;background:var(--card);
  display:flex;flex-direction:column;gap:2px;font-size:13.5px}
.notice span{color:var(--soft);font-size:12.5px}
.notice.warn{border-color:rgba(217,131,36,.5);background:var(--warnbg)}
/* division-of-labour flow */
.flow3{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.flow3 .box{border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--card);
  min-width:120px}
.flow3 .lab{font-size:11px;font-weight:700;color:var(--soft);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:6px}
.flow3 code{display:inline-block;line-height:1.5}
.tbl{border-collapse:collapse;font-size:12px}
.tbl th{color:var(--soft);text-transform:uppercase;font-size:10px;letter-spacing:.03em;
  text-align:left;padding:2px 8px 3px 0;border-bottom:1px solid var(--line)}
.tbl td{padding:2px 8px 2px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
/* table of contents */
.toc{border:1px solid var(--line);border-radius:10px;padding:12px 16px;background:#fcfcfe}
.toc-t{font-weight:750;color:var(--accent);font-size:12px;text-transform:uppercase;
  letter-spacing:.05em;margin-bottom:6px}
.toc ol{margin:0;padding-left:22px}
.toc li{margin:5px 0}
.toc small{color:var(--soft)}
/* the report toolbar */
.toolbar{display:flex;gap:8px;flex-wrap:wrap}
.tb{border:1px solid var(--line);border-radius:8px;padding:6px 12px;font-size:13px;font-weight:650;
  background:var(--card)}
.tb.prom{background:var(--accent);border-color:var(--accent);color:#fff}
@media (prefers-color-scheme:dark){
  :root{--bg:#14171c;--card:#1d2127;--ink:#e7eaee;--soft:#a3adba;--line:#2c333c;
    --tipbg:#182338;--tipink:#cdd9f5;--warnbg:#2a2213;--warnink:#e9d3ac}
  .toc{background:#191d24}
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
<title>57 - AI supported Documentation</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Guide</span>
  <h1>AI supported Documentation</h1>
  <p>Turn the process you have on screen into a polished, shareable report in one click:
     a language model writes the analysis, the app assembles a branded, self-contained
     document around it — cover, chapters, diagrams and all.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    <b>AI supported Documentation</b> analyses your <b>A-Chart</b> data with a language model and
    lays the findings out as a styled report. The model sees <b>only the transition table</b> and
    an instruction; the app supplies the <b>styling</b> and the fact-based chapters (process flow,
    conformance, happy path, journeys, notes). You review it, then <b>Save as PDF</b>.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">The split is the point: the LLM contributes <b>narrative</b>, the app guarantees
      the <b>numbers and the layout</b> — so the report is both readable and trustworthy.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — AI supported Documentation</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
