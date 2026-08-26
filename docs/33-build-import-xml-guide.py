#!/usr/bin/env python3
"""Generate the self-contained HTML how-to for importing XML logs in the Integration
Console: the repeating record element, element/attribute path mapping and the
whole-document delta.

Self-contained (CSS-drawn mocks, no screenshots). Facts mirror the in-app Help.
Run:  python3 docs/33-build-import-xml-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "33-Import-XML-Logs.html"
_BUILDER = pathlib.Path(__file__).name

_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

TITLE = "33 - Importing XML Logs"
CHIP = "Integration · Guide"
HERO_H1 = "Importing XML Logs"
HERO_P = ("An XML export repeats one element per event — you name that record element, then locate "
          "each field by an element or attribute path such as @id or payload/user@id. The console "
          "shows live what every path extracts.")
LEAD = ("An <b>XML</b> source type treats each <b>repeating element</b> as one record. Every field "
        "is located by an <b>element / attribute path</b>; the five roles are the same as every "
        "other format. This guide covers the record element, path mapping and the whole-document "
        "delta. See guide 30 for the console overview.")
NOTE = ("XML mapping mirrors JSON — click a path onto a role and read the live value — with "
        "attributes addressed by a leading @.")
FOOTER = "Process Mining Demonstrator · Integration — Importing XML logs"

STEPS = [
    (
        "The repeating record element",
        "Open <b>Source types → ＋</b> and <b>📄 Choose a file…</b>. The console auto-detects "
        "<span class='fmt xml'>XML</span> and the <b>record element</b> — the element that repeats "
        "once per event (here <code>&lt;event&gt;</code>) — shown at the top of the mapping step.",
        """<div class="mock"><span class="fmt xml">XML</span>
      <span class="cap" style="margin:0 0 0 8px">record element: <code>event</code></span>
      <div class="rec">&lt;log&gt;
  <span class="t">&lt;event</span> id="20253471"<span class="t">&gt;</span>
    <span class="t">&lt;ts&gt;</span>2015-01-09T19:12:06Z<span class="t">&lt;/ts&gt;</span>
    <span class="t">&lt;payload&gt;&lt;action&gt;</span>login<span class="t">&lt;/action&gt;&lt;/payload&gt;</span>
  <span class="t">&lt;/event&gt;</span>
  <span class="t">&lt;event</span> id="…"<span class="t">&gt;</span> … <span class="t">&lt;/event&gt;</span>
&lt;/log&gt;</div></div>""",
        None,
        None,
    ),
    (
        "Map fields by element / attribute path",
        "The record's fields are listed as <b>clickable paths</b>. Pick a role tab and click a path "
        "— or type one. An <b>attribute</b> is addressed with a leading <code>@</code>; nested "
        "elements use <code>/</code>.",
        """<div class="mock"><div class="mapwrap"><table class="maptab">
      <tr><th>Role</th><th>Path</th><th>Extracted</th></tr>
      <tr><td class="role">EVENT_ID</td><td class="sel">@id</td><td class="val">20253471</td></tr>
      <tr><td class="role">EVENT_TIME</td><td class="sel">ts</td><td class="val">2015-01-09T19:12:06Z</td></tr>
      <tr><td class="role">STEP</td><td class="sel">payload/action</td><td class="val">login</td></tr>
      <tr><td class="role">Meta 1</td><td class="sel">payload/user@id</td><td class="val">u-77</td></tr>
    </table></div><p class="cap">Each path resolves to a single value, shown live — so a wrong path
      is obvious immediately.</p></div>""",
        None,
        '<span class="k">Same five roles.</span> EVENT_TIME is normalised to '
        "<code>YYYY-MM-DD HH:MM:SS</code>; EVENT_ID is stored <b>MD5-hashed</b>; up to three Metas "
        "carry business names; a Helper feeds compound rules only.",
    ),
    (
        "Compound steps work with paths too",
        "Split one activity into several by another field — the conditions match on <b>path</b> "
        "values. Map the deciding field (e.g. a status attribute) as a Helper, then write rules in "
        "the <b>STEP</b> tab.",
        """<div class="mock"><div class="rules">
      <div class="rulechip"><b>Rule 1 → login successful</b> <span class="cond">when payload/action is “login” · @status is “200”</span></div>
      <div class="rulechip"><b>Rule 2 → login failed</b> <span class="cond">when payload/action is “login” · @status is “500”</span></div>
    </div><p class="cap">First matching rule wins; unmatched records keep the plain STEP value.</p></div>""",
        None,
        None,
    ),
    (
        "Import & re-import",
        "Add a <b>File</b> source, link this source type, and press <b>▷</b>. An XML file is a "
        "<b>whole document</b>, so it is <b>import-once by content signature</b>: re-running an "
        "unchanged file imports nothing; a changed file re-imports the whole document.",
        """<div class="mock"><div class="lab">Importing…</div><div class="progress"><i></i></div>
      <p class="cap">The panel shows the records imported and when it last ran. Because events are
        never de-duplicated, re-importing a changed file adds its events again — to truly reload a
        project, delete it first (Connections → Projects) and import anew.</p></div>""",
        None,
        None,
    ),
]

BEYOND = [
    "<b>Attributes vs elements.</b> A leading <code>@</code> selects an attribute (<code>@id</code>, "
    "<code>payload/user@id</code>); a bare path selects element text.",
    "<b>Live JOURNEYS preview.</b> An example output row (id shown “stored as MD5”) confirms the "
    "whole spec before you save.",
    "<b>Compound rules are additive</b> and case-insensitive except for “matches regex” — same as "
    "every format.",
    "<b>Sandboxed reads</b> and import logging apply here too — see the overview (guide 30).",
]

CSS = r"""
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415;
  --txt:#3a9bff; --json:#e0a417; --xml:#12a150; --good:#1e9e5a;
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
kbd{background:var(--card);border:1px solid var(--line);border-bottom-width:2px;border-radius:6px;
  padding:1px 7px;font:600 13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}
code{background:var(--bg);border-radius:4px;padding:1px 5px;font-size:12.5px}
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.big-arrow{color:var(--soft);font-size:20px;font-weight:700}
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);font-weight:600;font-size:13px}
.node.good{border-color:rgba(30,158,90,.5);background:rgba(30,158,90,.1);color:var(--good)}
.node.hub{border-color:var(--accent);background:rgba(58,109,240,.08);color:var(--accent);font-weight:750}
.arrow{color:var(--soft);font-weight:700}
.lab{color:var(--soft);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px}
/* format badge */
.fmt{display:inline-block;font-size:11px;font-weight:800;letter-spacing:.05em;border-radius:6px;
  padding:2px 8px;color:#fff}
.fmt.text{background:var(--txt)} .fmt.json{background:var(--json)} .fmt.xml{background:var(--xml)}
/* example record box */
.rec{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin-top:8px;
  font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;overflow-x:auto;color:var(--ink)}
.rec .hl{background:rgba(58,109,240,.22);border-radius:3px;padding:0 2px;box-shadow:0 0 0 1px rgba(58,109,240,.4)}
.rec .k{color:var(--json)} .rec .t{color:var(--xml)}
/* mapping table */
.maptab{border-collapse:collapse;width:100%;font-size:13px;min-width:460px}
.maptab th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--soft);
  padding:5px 10px;border-bottom:2px solid var(--line)}
.maptab td{padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.maptab .role{font-weight:750;color:var(--accent);white-space:nowrap}
.maptab .sel{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink)}
.maptab .val{color:var(--good);font-weight:650}
.mapwrap{overflow-x:auto}
/* two concept cards */
.cards{display:flex;gap:12px;flex-wrap:wrap}
.cardk{flex:1;min-width:220px;border:1px solid var(--line);border-radius:11px;padding:13px 15px;background:var(--card)}
.cardk .ct{font-weight:800;font-size:15px;margin-bottom:3px}
.cardk .cd{color:var(--soft);font-size:13px}
/* rule badges */
.rules{display:flex;flex-direction:column;gap:6px}
.rulechip{border:1px solid var(--line);border-radius:9px;padding:8px 12px;background:var(--card);font-size:13px}
.rulechip b{color:var(--accent)}
.rulechip .cond{color:var(--soft)}
/* progress / checkpoint */
.progress{height:8px;border-radius:5px;background:var(--line);overflow:hidden;max-width:320px;margin-top:6px}
.progress i{display:block;height:100%;width:64%;background:linear-gradient(90deg,var(--accent),var(--accent2))}
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
    return f'''<!doctype html>
<!-- Generated documentation page - open this file in a WEB BROWSER.
     It is NOT a script; to rebuild it run:  python3 docs/{_BUILDER} -->
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">{CHIP}</span>
  <h1>{HERO_H1}</h1>
  <p>{HERO_P}</p>
</div></header>

<div class="wrap">

  <div class="lead">{LEAD}</div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">{NOTE}</p>
  </div>

  <footer>{FOOTER}</footer>
</div>
</body></html>
'''


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
