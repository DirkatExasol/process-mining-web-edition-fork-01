#!/usr/bin/env python3
"""Generate the self-contained HTML deep-dive: how the Conformance Check computes
its numbers — actual values per metric, norm comparison, the minimum toggle, the
100 % budget for Count norms, and the gap-analysis table — with worked examples.

All example values are plain arithmetic applications of the app's actual rules
(frontend/web/src/views/ConformanceView.tsx and backend docgen.conformance_section);
the formulas quoted are the ones in the code.

Like the other guides, all illustrations are CSS-drawn mocks — no screenshots — so
the single .html file is fully self-contained.
Run:  python3 docs/build-conformance-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "Conformance-Explained.html"

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon, so the
# browser tab shows the suite's icon while the page stays fully self-contained.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each chapter: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
# body/mock/bullets/tip are passed through as HTML (only the title is escaped).
STEPS = [
    (
        "What the Conformance Check does",
        "The Conformance Check lays <b>target values (“norms”)</b> over the process map and "
        "judges every transition against them: <b>green</b> where the actual value meets its "
        "norm, <b>red</b> where it breaks it. Norms are stored <b>per project and per "
        "metric</b> — switch the metric chips and a different set of targets applies.",
        """<div class="mock">
      <div class="pills">
        <span class="pill on"># Count</span><span class="pill">% Percentage</span>
        <span class="pill">% Journey&nbsp;%</span><span class="pill">⏱ Avg&nbsp;Time</span>
        <span class="pill">⌄ Min</span><span class="pill">⌃ Max</span><span class="pill">〰 Std&nbsp;Dev</span>
      </div>
      <div class="flow" style="margin-top:12px">
        <span class="node">Payment Processing</span>
        <span class="edge ok">→ 82.0 % ≤ 90 % ✓</span>
        <span class="node good">Payment Confirmed</span>
      </div>
      <div class="flow" style="margin-top:6px">
        <span class="node">Payment Processing</span>
        <span class="edge miss">→ 18.0 % &gt; 10 % ✗</span>
        <span class="node bad">Payment Failed</span>
      </div>
      <p class="cap">Two norms on the same source step: the confirmation edge meets its target,
        the failure edge breaks its 10 % ceiling — drawn red on the map.</p>
    </div>""",
        None,
        '<span class="k">Setting norms.</span> Toggle <b>Edit norms</b>, click an edge, type '
        "the target. Norms survive Backup &amp; Restore, so a target model can move between "
        "installations.",
    ),
    (
        "What “actual” means — it depends on the metric",
        "Before any comparison, the app computes each edge's <b>actual value</b>. The rule "
        "differs by metric — this is the part most worth understanding:",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Metric</th><th>Actual value of edge A → B</th><th>Norm means</th></tr>
        <tr><td># Count, % Percentage</td>
            <td>occurrences(A→B) / Σ occurrences(A→*) × 100</td>
            <td>% of the traffic <b>leaving A</b></td></tr>
        <tr><td>% Journey %</td>
            <td>occurrences(A→B) / filtered journey count × 100</td>
            <td>% of <b>all journeys</b></td></tr>
        <tr><td>⏱ Avg / Min / Max / Std Dev</td>
            <td>the edge's time value, in seconds</td>
            <td>an absolute duration</td></tr>
      </table>
      <pre class="calc">Example — outgoing traffic of Payment Processing (7,500 total):
  → Payment Confirmed   6,150 / 7,500 × 100 = 82.0 %
  → Payment Failed      1,350 / 7,500 × 100 = 18.0 %</pre>
      <p class="cap">For Count, a norm of 50 % on A → B therefore reads: “at most half of
        everything leaving A may go to B”. Time norms are entered in seconds and displayed
        as s / m / h / d.</p>
    </div>""",
        [
            "<b>Self-loops (A → A) are excluded</b> from the conformance table — a step "
            "repeating itself is not a hand-over between steps.",
            "Edges <b>without a norm</b> are neutral: they are never coloured and count "
            "neither as compliant nor as a violation.",
        ],
        None,
    ),
    (
        "The comparison: norm as a ceiling (default)",
        "By default a norm is a <b>maximum</b> — the actual value must stay at or below it. "
        "For every edge with a norm, the app computes the <b>delta</b> and a verdict:",
        """<div class="mock">
      <div class="formula">delta = actual − norm &nbsp;&nbsp;·&nbsp;&nbsp; violation ⇔ actual &gt; norm</div>
      <table class="tbl" style="margin-top:12px">
        <tr><th>Edge</th><th>Actual</th><th>Norm</th><th>Delta</th><th>Status</th></tr>
        <tr><td>Payment Processing → Payment Failed</td><td>18.0 %</td><td>10 %</td><td>+8.0 %</td><td>❌ Violation</td></tr>
        <tr><td>Warehouse Packing → Shipped (Avg)</td><td>2.1 d</td><td>1.0 d</td><td>+1.1 d</td><td>❌ Violation</td></tr>
        <tr><td>Checkout → Payment Processing (Avg)</td><td>2.0 h</td><td>4.0 h</td><td>−2.0 h</td><td>✅ Compliant</td></tr>
        <tr><td>Payment Processing → Payment Confirmed</td><td>82.0 %</td><td>90 %</td><td>−8.0 %</td><td>✅ Compliant</td></tr>
        <tr><td>Login → Browse Catalog</td><td>100.0 %</td><td>—</td><td>—</td><td>— No norm</td></tr>
      </table>
      <p class="cap">Exactly the app's rule: red as soon as the actual exceeds the target,
        green at or below it, neutral without a target.</p>
    </div>""",
        None,
        None,
    ),
    (
        "“Norm is a minimum” — flipping the comparison",
        "Some targets are floors, not ceilings: “at least 95 % of shipped orders must reach "
        "Delivered”. The <b>Norm is a minimum</b> toggle flips the verdict for the whole view:",
        """<div class="mock">
      <div class="formula">maximum (default): violation ⇔ actual &gt; norm<br>
minimum (toggled): &nbsp;violation ⇔ actual &lt; norm</div>
      <pre class="calc">Shipped → Delivered:   actual 93.0 %,  norm 95 %

norm as maximum:  93.0 ≤ 95  → ✅ compliant  (wrong reading!)
norm as minimum:  93.0 &lt; 95  → ❌ violation  (2 % never arrive)</pre>
      <p class="cap">Same numbers, opposite meaning — choose the reading that matches how your
        targets are phrased. The toggle applies to the current view's judgement, not to the
        stored norm values.</p>
    </div>""",
        None,
        '<span class="k">Reports follow the toggle.</span> The gap analysis appended to the '
        "AI Documentation report applies the same reading as the live view, and states which "
        "one it used (“Norms are read as maximums/minimums”).",
    ),
    (
        "Count norms are a 100 % budget",
        "Because Count norms are shares of one source step's outgoing traffic, all norms "
        "leaving the same step should <b>sum to at most 100 %</b>. The norm editor enforces "
        "this live while you type:",
        """<div class="mock">
      <pre class="calc">Norms already set from Browse Catalog:
  → View Book Details   60 %
  → Add to Basket       35 %      assigned to other edges: 95 %

Editing a third edge from Browse Catalog:
  remaining = 100 − 95 = 5 %
  you type 8 →  total = 95 + 8 = 103 %  &gt; 100  →  shown in RED</pre>
      <p class="cap">The editor shows the live “remaining %” for the source step and warns as
        soon as the step's outgoing norms would exceed 100 % — so a target model stays a
        consistent branching plan.</p>
    </div>""",
        None,
        None,
    ),
    (
        "The gap-analysis table",
        "<b>Show gaps</b> opens the full table — every edge with from, to, actual, norm, delta "
        "and status. It is sorted so the worst problems surface first: <b>violations before "
        "everything else, largest delta first</b>, and it is summarised in one line:",
        """<div class="mock">
      <pre class="calc">Summary: 2 violation(s) · 2 compliant · 1 without norm</pre>
      <table class="tbl">
        <tr><th>#</th><th>Edge</th><th>Delta</th><th>Status</th></tr>
        <tr><td>1</td><td>Warehouse Packing → Shipped</td><td>+1.1 d</td><td>❌ Violation</td></tr>
        <tr><td>2</td><td>Payment Processing → Payment Failed</td><td>+8.0 %</td><td>❌ Violation</td></tr>
        <tr><td>3</td><td>Payment Processing → Payment Confirmed</td><td>−8.0 %</td><td>✅ Compliant</td></tr>
        <tr><td>4</td><td>Checkout → Payment Processing</td><td>−2.0 h</td><td>✅ Compliant</td></tr>
        <tr><td>5</td><td>Login → Browse Catalog</td><td>—</td><td>— No norm</td></tr>
      </table>
      <p class="cap">Reading order = priority order: start fixing at row 1.</p>
    </div>""",
        None,
        None,
    ),
    (
        "Conformance in the AI report",
        "When at least one metric has norms defined, the AI Documentation report gains a "
        "<b>“Conformance Check – Gap Analysis”</b> chapter: one gap table per metric that has "
        "norms, the currently selected metric first, each with its violations / compliant / "
        "no-norm summary. The chapter is assembled in Python from your data — the report's "
        "language model never sees or influences the conformance numbers.",
        None,
        [
            "Per metric: the same actual-value rules as the live view (branching share for "
            "Count, absolute seconds for time metrics).",
            "Rows are sorted violations-first, largest delta first — identical to the gap table.",
            "Metrics without any norms are omitted entirely.",
        ],
        None,
    ),
]

BEYOND = [
    "<b>Norms are per (project, metric).</b> Each metric carries its own independent target "
    "set; switching the metric chip switches the whole conformance picture.",
    "<b>Neutral is not a pass.</b> Edges without norms are excluded from both counts — a "
    "process with one norm and one violation is “100 % violating”, not “mostly fine”.",
    "<b>Norms travel.</b> They are included in Backup &amp; Restore, so a target model built "
    "once can be shared or moved between installations.",
    "<b>Who sees it.</b> Conformance Check is an advanced-analysis view for Power users and "
    "administrators.",
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
/* Mock illustrations (no screenshots needed) */
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px}
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);
  font-weight:600;display:inline-block}
.node.good{border-color:rgba(30,158,90,.55);background:rgba(30,158,90,.10);color:var(--good)}
.node.bad{border-color:rgba(212,69,59,.55);background:rgba(212,69,59,.10);color:var(--bad)}
.edge{font-weight:700;font-size:12px;padding:2px 8px;border-radius:6px;font-variant-numeric:tabular-nums}
.edge.ok{color:var(--good);background:rgba(30,158,90,.10)}
.edge.miss{color:var(--bad);background:rgba(212,69,59,.10)}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12.5px;background:var(--card)}
.pill.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.formula{font:600 15px/1.7 ui-monospace,SFMono-Regular,Menlo,monospace;text-align:center;
  background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px;
  overflow-x:auto}
.tbl{border-collapse:collapse;font-size:13px;width:100%}
.tbl th{color:var(--soft);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;
  text-align:left;padding:4px 12px 6px 0;border-bottom:2px solid var(--line)}
.tbl td{padding:5px 12px 5px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.calc{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px;
  margin:12px 0 0;font:12.5px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;
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
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conformance Check Explained</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Deep Dive</span>
  <h1>How the Conformance Check calculates</h1>
  <p>Target norms on the map, green and red edges, deltas and the gap-analysis table —
     this guide explains exactly how each number is computed, with worked bookstore
     examples that follow the app's rules to the letter.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    The pipeline has three stages: compute each edge's <b>actual value</b> (the rule depends
    on the metric), compare it against the edge's <b>norm</b> (as a ceiling by default, as a
    floor with the minimum toggle), and rank the results in the <b>gap-analysis table</b> —
    violations first, biggest gap on top. Norms are stored per project and per metric.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Conformance turns a target operating model into something the map can
      check continuously — every reload re-judges the live process against the same yardstick.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — How the Conformance Check calculates</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
