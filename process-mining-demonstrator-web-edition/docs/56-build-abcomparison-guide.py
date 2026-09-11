#!/usr/bin/env python3
"""Generate the self-contained HTML guide for A/B Comparison: two filtered process
views side by side, the synchronising valve, copy-layout, per-side data sources and
the live Similarity badge.

Every illustration is a small CSS-drawn mock of the UI — no screenshots — so the
single .html file is fully self-contained.
Run:  python3 docs/56-build-abcomparison-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "56-AB-Comparison.html"
_BUILDER = pathlib.Path(__file__).name

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon, so the
# browser tab shows the suite's icon while the page stays fully self-contained.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each step: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
STEPS = [
    (
        "Two processes, side by side",
        "A/B Comparison splits the canvas: <b>A-Chart</b> on the left, <b>B-Chart</b> on the "
        "right, both visible at once. Give each side its own filters, metric and date window and "
        "compare them directly — two segments, two periods, or real against simulated.",
        """<div class="mock"><div class="split">
      <div class="pane"><div class="ph">A-Chart <span class="edit">✎ editing</span></div>
        <div class="flow sm"><span class="node">Login</span><span class="arrow">→</span>
          <span class="node">Cart</span><span class="arrow">→</span><span class="node">Pay</span></div></div>
      <div class="divider">⇄</div>
      <div class="pane"><div class="ph">B-Chart</div>
        <div class="flow sm"><span class="node">Login</span><span class="arrow">→</span>
          <span class="node">Cart</span><span class="arrow">→</span><span class="node">Pay</span></div></div>
    </div><p class="cap">Both maps stay on screen; the divider between them carries the valve and
      the similarity badge.</p></div>""",
        None,
        '<span class="k">Open it</span> from the ☰ menu → <b>A/B Comparison</b>.',
    ),
    (
        "Pick the active side, then filter it",
        "The sidebar filters, metric, date slider and presets act on the <b>active</b> side. "
        "Switch it by <b>tapping a panel header</b> or the <b>A | B segmented control</b> at the "
        "top of the Filters section — the active panel shows a pencil and an “editing” label.",
        """<div class="mock"><div class="row" style="gap:14px">
      <span class="seg big"><span class="on">A</span><span>B</span></span>
      <span class="cap" style="margin:0">← the active side gets every sidebar setting</span>
    </div></div>""",
        [
            "Each panel keeps its <b>own metric pill</b>, <b>date window</b> and <b>Presets</b> "
            "picker — so A and B can use entirely different settings at once.",
            "<b>Apply</b> reloads only the active side.",
        ],
        None,
    ),
    (
        "Choose each side’s data source",
        "In the <b>Sampling</b> section the A and B slots each choose what to load: the "
        "<b>Original</b> data, one of your <b>sample sets</b>, or a stored <b>Simulation</b> result "
        "(<b>Sim-A</b> / <b>Sim-B</b>). This is how you feed a what-if into the comparison.",
        """<div class="mock"><div class="row" style="gap:26px">
      <div><div class="lab">A source</div>
        <span class="seg"><span class="on">Original</span><span>Sample 1</span><span>Sim-A</span></span></div>
      <div><div class="lab">B source</div>
        <span class="seg"><span>Original</span><span>Sample 1</span><span class="on">Sim-B</span></span></div>
    </div><p class="cap">Here A shows the real process and B a simulation — a classic what-if
      comparison. Or compare two samples, or two date ranges of the same data.</p></div>""",
        None,
        '<span class="k">Simulations first.</span> Run a Simulation and store it as Sim-A / Sim-B, '
        "then select it here — see the <b>Simulation</b> guide.",
    ),
    (
        "The valve — sync or free the viewports",
        "The <b>⇄ valve</b> on the divider ties the two viewports together. <b>Open</b>: pan, "
        "zoom, reset and node drags <b>mirror</b> across both panels instantly. <b>Closed</b>: each "
        "panel moves independently (closing snapshots A’s view into B so they start aligned). "
        "<b>A is always the master.</b>",
        """<div class="mock"><div class="row" style="gap:14px">
      <span class="valve open">⇄ Valve open — viewports synced</span>
      <span class="valve">⇄ Valve closed — independent</span>
    </div><p class="cap">Open it to inspect the same region at the same zoom on both sides; close it
      to explore each map on its own.</p></div>""",
        None,
        None,
    ),
    (
        "Copy A’s layout to B",
        "The <b>⧉ Copy layout</b> button in A’s header transfers A’s <b>complete viewport</b> — "
        "zoom, pan and every node position — to B in one tap. Handy after you’ve hand-arranged A "
        "and want B laid out identically for a fair, node-for-node visual comparison.",
        """<div class="mock">
      <div class="pane" style="max-width:320px">
        <div class="ph">A-Chart <span class="copy">⧉ Copy layout</span></div>
        <div class="flow sm"><span class="node">Login</span><span class="arrow">→</span>
          <span class="node">Cart</span><span class="arrow">→</span><span class="node">Pay</span></div>
      </div><p class="cap">One tap sends A’s arrangement to B.</p></div>""",
        None,
        None,
    ),
    (
        "Read the Similarity badge",
        "A <b>Similarity</b> badge floats between the panels, showing <b>Q(A, B)</b> from 0 to 1 — "
        "how behaviourally alike the two processes are. It refreshes automatically whenever you "
        "change a filter or date on either side.",
        """<div class="mock"><div class="badge"><span class="badge-t">⇄ Similarity</span>
        <span class="badge-v">0.56</span></div>
      <div class="pills" style="margin-top:10px">
        <span class="pill on2">green ≥ 0.70 — very similar</span>
        <span class="pill on3">blue 0.31–0.69 — partial</span>
        <span class="pill on4">red ≤ 0.30 — different</span>
      </div>
      <p class="cap">The colour is decided by these thresholds. See the <b>Process Similarity</b>
        guide for exactly how Q is calculated.</p></div>""",
        None,
        None,
    ),
]

BEYOND = [
    "<b>Fully independent panels.</b> Each side has its own filters, metric, KPI strip and "
    "Presets — so you can apply different presets to A and B at the same time.",
    "<b>A is the master.</b> Both the valve sync and Copy layout flow from A to B.",
    "<b>Process Goodness in A/B.</b> Each panel’s Process Goodness KPI tile is green when this "
    "side beats the other, red when lower, blue when equal within 0.005.",
    "<b>Compare reality with a what-if.</b> Point one side at a stored Simulation (Sim-A / "
    "Sim-B) and the other at the Original data to see the effect of a change before you make it.",
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
kbd{background:var(--card);border:1px solid var(--line);border-bottom-width:2px;border-radius:6px;
  padding:1px 7px;font:600 13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}
/* Mock illustrations */
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
.flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px}
.flow.sm{font-size:12px;gap:5px}
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);font-weight:600}
.flow.sm .node{padding:4px 8px}
.arrow{color:var(--soft);font-weight:700}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.lab{color:var(--soft);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  margin-bottom:5px}
/* the split view */
.split{display:flex;align-items:stretch;gap:0;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.pane{flex:1;min-width:0;padding:12px 14px;background:var(--card)}
.pane .ph{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:750;
  color:var(--soft);margin-bottom:10px}
.pane .ph .edit{color:var(--accent);font-weight:700;font-size:12px;
  background:rgba(58,109,240,.1);border-radius:999px;padding:2px 8px}
.pane .ph .copy{margin-left:auto;color:var(--accent);font-weight:700;font-size:12px;
  border:1px solid rgba(58,109,240,.4);border-radius:7px;padding:3px 8px}
.divider{flex:0 0 auto;width:34px;display:grid;place-items:center;color:var(--accent);
  font-weight:800;background:rgba(58,109,240,.06);border-left:1px solid var(--line);
  border-right:1px solid var(--line)}
/* segmented control */
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:12.5px}
.seg span{padding:5px 11px;border-right:1px solid var(--line)}
.seg span:last-child{border-right:0}
.seg span.on{background:var(--accent);color:#fff}
.seg.big span{padding:7px 18px;font-size:15px;font-weight:750}
/* valve chips */
.valve{border:1px solid var(--line);border-radius:999px;padding:6px 13px;font-size:13px;
  font-weight:650;color:var(--soft);background:var(--card)}
.valve.open{background:var(--accent);border-color:var(--accent);color:#fff}
/* similarity badge + threshold pills */
.badge{display:inline-flex;flex-direction:column;align-items:center;gap:2px;border:1px solid var(--line);
  border-radius:12px;padding:8px 16px;background:var(--card);box-shadow:0 8px 20px rgba(20,30,50,.12)}
.badge-t{font-size:11px;font-weight:700;color:var(--soft);text-transform:uppercase;letter-spacing:.05em}
.badge-v{font-size:22px;font-weight:800;color:var(--accent);font-variant-numeric:tabular-nums}
.pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12.5px;background:var(--card)}
.pill.on2{color:var(--good);border-color:rgba(30,158,90,.45);background:rgba(30,158,90,.1)}
.pill.on3{color:var(--accent);border-color:rgba(58,109,240,.45);background:rgba(58,109,240,.1)}
.pill.on4{color:var(--bad);border-color:rgba(212,69,59,.45);background:rgba(212,69,59,.1)}
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
<title>56 - A/B Comparison</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Guide</span>
  <h1>A/B Comparison</h1>
  <p>Put two filtered process views side by side — A-Chart and B-Chart — and compare them
     directly: two segments, two periods, or the real process against a simulation. Sync the
     viewports, copy layouts, and read a live similarity score between the panels.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    <b>A/B Comparison</b> shows two independent maps at once. Choose <b>what each side loads</b>
    (Original data, a sample, or a stored simulation), give each its own filters and metric, then
    use the <b>valve</b> to synchronise the viewports and the <b>Similarity badge</b> to measure
    how alike the two processes really are. <b>A is always the master.</b>
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">A/B Comparison turns “these two look different” into something you can see
      side by side and measure — with one number, the similarity score, on top.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — A/B Comparison</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
