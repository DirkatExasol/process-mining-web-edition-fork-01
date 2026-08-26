#!/usr/bin/env python3
"""Generate the self-contained HTML how-to for the Conformance Check view: overlay
target norms on the map, read green/red edges, flip the minimum toggle, and open the
gap-analysis table. (The calculation itself is covered by guide 81.)

Self-contained (CSS-drawn mocks, no screenshots). Facts mirror the in-app Help.
Run:  python3 docs/59-build-conformance-usage-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "59-Conformance-Check.html"
_BUILDER = pathlib.Path(__file__).name

_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

STEPS = [
    (
        "What it does",
        "Conformance Check lays your <b>target values (“norms”)</b> over the process map and shows, "
        "edge by edge, whether the real process meets them — <b>green</b> where it does, <b>red</b> "
        "where it breaks the target. Switch the metric with the chips at the top; norms are stored "
        "<b>per project and per metric</b>.",
        """<div class="mock">
      <div class="pills"><span class="pill on"># Count</span><span class="pill">% Journey %</span>
        <span class="pill">⏱ Avg Time</span><span class="pill">⌄ Min</span><span class="pill">⌃ Max</span></div>
      <div class="flow" style="margin-top:12px">
        <span class="node">Payment Processing</span><span class="edge ok">→ 82% ≤ 90% ✓</span>
        <span class="node good">Confirmed</span></div>
      <div class="flow" style="margin-top:6px">
        <span class="node">Payment Processing</span><span class="edge miss">→ 18% &gt; 10% ✗</span>
        <span class="node bad">Failed</span></div>
    </div>""",
        None,
        '<span class="k">Open it</span> from the ☰ menu → <b>Conformance Check</b> (an advanced view '
        "for Power users and admins).",
    ),
    (
        "Set the norms",
        "Toggle <b>Edit norms</b>, click an edge, and type its target. For the <b>Count</b> metric a "
        "norm is a <b>percentage of the traffic leaving that source step</b>, and the editor shows a "
        "live <b>remaining %</b> — how much is already assigned to the step’s other out-edges and how "
        "much is left before it exceeds 100 %. Time metrics take an absolute value in seconds.",
        """<div class="mock"><div class="editrow">
      <span class="node">Browse Catalog</span><span class="arrow">→</span><span class="node">Add to Basket</span>
      <span class="in">35 %</span>
      <span class="remaining">remaining for this step: 5 %</span>
    </div><p class="cap">Two other edges from Browse Catalog already take 95 % — type more than 5 % and
      the editor warns you in red that the step’s norms would exceed 100 %.</p></div>""",
        None,
        None,
    ),
    (
        "Ceiling or floor",
        "By default a norm is a <b>maximum</b> — the actual value must stay at or below it (red when "
        "it exceeds). Flip <b>Norm is a minimum</b> and the whole view reverses: the actual must be "
        "<b>at least</b> the norm (red when it falls short). Same numbers, opposite meaning — pick "
        "the reading that matches how your targets are phrased.",
        """<div class="mock"><div class="row" style="gap:14px">
      <span class="toggle">Norm is a minimum <span class="sw off">◯</span></span>
      <span class="cap" style="margin:0">Shipped → Delivered: 93 % · norm 95 %</span>
    </div><p class="cap"><b>As a maximum</b>: 93 ≤ 95 → ✓ · <b>as a minimum</b>: 93 &lt; 95 → ✗
      (2 % of shipments never arrive).</p></div>""",
        None,
        None,
    ),
    (
        "Read the gap analysis",
        "Click <b>Show gaps</b> for the full table — every edge with <b>from, to, actual, norm, "
        "delta and status</b>, sorted with the worst <b>violations first</b> and a one-line summary "
        "at the top.",
        """<div class="mock"><div class="gapsum">2 violations · 2 compliant · 1 without norm</div>
      <div class="mapwrap"><table class="gaptab">
        <tr><th>Edge</th><th>Actual</th><th>Norm</th><th>Delta</th><th>Status</th></tr>
        <tr><td>Warehouse Packing → Shipped</td><td>2.1 d</td><td>1.0 d</td><td class="d-bad">+1.1 d</td><td class="s-bad">❌ Violation</td></tr>
        <tr><td>Payment Proc. → Failed</td><td>18 %</td><td>10 %</td><td class="d-bad">+8 %</td><td class="s-bad">❌ Violation</td></tr>
        <tr><td>Payment Proc. → Confirmed</td><td>82 %</td><td>90 %</td><td class="d-ok">−8 %</td><td class="s-ok">✅ Compliant</td></tr>
        <tr><td>Login → Browse</td><td>100 %</td><td>—</td><td>—</td><td class="s-mut">— No norm</td></tr>
      </table></div><p class="cap">Reading order = priority order: start fixing at the top.</p></div>""",
        None,
        None,
    ),
    (
        "Where it goes",
        "Conformance is more than a one-off view — it feeds the rest of the suite and travels with "
        "your setup:",
        None,
        [
            "The gap analysis is <b>appended to the AI supported Documentation report</b> (one table "
            "per metric that has norms), following the same ceiling/floor reading you chose.",
            "Norms <b>round-trip through Backup &amp; Restore</b>, so a target model built once can be "
            "shared or moved between installations.",
            "Only edges that <b>have a norm</b> are judged — the rest are neutral (never counted as "
            "compliant or as a violation).",
        ],
        '<span class="k">How are actual, delta and colour computed?</span> The exact per-metric '
        "rules (branching share for Count, absolute seconds for time, the 100 % budget) are in "
        "guide <b>81 — Conformance Explained</b>.",
    ),
]

BEYOND = [
    "<b>Count norms are a 100 % budget.</b> Because they’re shares of one step’s outgoing traffic, "
    "the norms leaving a step should sum to at most 100 % — the editor enforces this as you type.",
    "<b>Per project, per metric.</b> Each metric carries its own independent target set; switching "
    "the metric chip switches the whole conformance picture.",
    "<b>Advanced view.</b> Conformance Check is available to Power users and administrators (see "
    "the Users &amp; Permissions guide).",
    "<b>It measures, it doesn’t change.</b> Norms are targets laid over the real data — defining "
    "them never alters your process.",
]

CSS = r"""
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
code{background:var(--bg);border-radius:4px;padding:1px 5px;font-size:12.5px}
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.flow,.editrow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px}
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);font-weight:600}
.node.good{border-color:rgba(30,158,90,.5);background:rgba(30,158,90,.1);color:var(--good)}
.node.bad{border-color:rgba(212,69,59,.5);background:rgba(212,69,59,.1);color:var(--bad)}
.arrow{color:var(--soft);font-weight:700}
.edge{font-weight:700;font-size:12px;padding:2px 8px;border-radius:6px;font-variant-numeric:tabular-nums}
.edge.ok{color:var(--good);background:rgba(30,158,90,.1)}
.edge.miss{color:var(--bad);background:rgba(212,69,59,.1)}
.pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12.5px;background:var(--card)}
.pill.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.in{border:1px solid var(--accent);border-radius:7px;padding:4px 10px;font-weight:700;color:var(--accent);
  background:rgba(58,109,240,.08)}
.remaining{color:var(--soft);font-size:12.5px}
.toggle{display:inline-flex;align-items:center;gap:8px;font-weight:650;font-size:14px;
  border:1px solid var(--line);border-radius:999px;padding:5px 12px;background:var(--card)}
.toggle .sw{color:var(--soft)}
.gapsum{font-weight:700;color:var(--ink);margin-bottom:10px}
.mapwrap{overflow-x:auto}
.gaptab{border-collapse:collapse;width:100%;font-size:13px;min-width:480px}
.gaptab th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--soft);
  padding:5px 10px;border-bottom:2px solid var(--line)}
.gaptab td{padding:6px 10px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.gaptab .d-bad{color:var(--bad);font-weight:700}
.gaptab .d-ok{color:var(--good);font-weight:700}
.gaptab .s-bad{color:var(--bad);font-weight:650;white-space:nowrap}
.gaptab .s-ok{color:var(--good);font-weight:650;white-space:nowrap}
.gaptab .s-mut{color:var(--soft);white-space:nowrap}
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
<title>59 - Conformance Check</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Guide</span>
  <h1>Conformance Check</h1>
  <p>Lay target values over the process map and see, edge by edge, whether reality meets them —
     green where it does, red where it doesn't — then open the gap-analysis table to fix the
     worst first.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    <b>Conformance Check</b> overlays your <b>norms</b> (targets) on any transition metric and
    colours each edge by whether the actual value meets its target. You set the norms in Edit mode,
    choose whether each is a <b>ceiling or a floor</b>, and read the <b>gap analysis</b> — violations
    first. For the exact maths behind “actual” and “delta”, see guide <b>81 — Conformance
    Explained</b>.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Conformance turns a target operating model into something the map checks
      continuously — every reload re-judges the live process against the same yardstick.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — Conformance Check</footer>
</div>
</body></html>
'''


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
