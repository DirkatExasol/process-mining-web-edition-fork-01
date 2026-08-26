#!/usr/bin/env python3
"""Generate the self-contained HTML guide for the Happy Path view: define an ideal
step sequence (with splits that rejoin), then measure how closely real journeys
follow it.

Self-contained (CSS-drawn mocks, no screenshots). Facts mirror the in-app Help.
Run:  python3 docs/58-build-happypath-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "58-Happy-Path.html"
_BUILDER = pathlib.Path(__file__).name

_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

STEPS = [
    (
        "What a Happy Path is",
        "A <b>Happy Path</b> is the ideal sequence a process <i>should</i> follow. The view splits "
        "in two: on the <b>left</b> the actual process map (its edges read as <b>Journey %</b>), on "
        "the <b>right</b> your ideal definition. A conformance score then measures how closely real "
        "journeys match it.",
        """<div class="mock"><div class="split">
      <div class="pane"><div class="ph">Actual Process</div>
        <div class="flow sm"><span class="node">Browse</span><span class="arrow">→</span>
          <span class="node">Cart</span><span class="arrow">→</span><span class="node">Pay</span></div></div>
      <div class="divider">🪧</div>
      <div class="pane"><div class="ph">Happy Path (ideal)</div>
        <div class="flow sm"><span class="node good">Browse</span><span class="arrow">↓</span>
          <span class="node good">Cart</span><span class="arrow">↓</span><span class="node good">Pay</span></div></div>
    </div><p class="cap">Drag the divider to widen the ideal-path editor; double-click to reset.</p></div>""",
        None,
        '<span class="k">Where.</span> Open it from the ☰ menu → <b>Happy Path</b> (an advanced view '
        "for Power users and admins).",
    ),
    (
        "Define the ideal sequence",
        "Toggle <b>✎ Edit Path</b>, then build the sequence: <b>＋</b> adds a step, <b>▲ ▼</b> "
        "reorder, <b>⊖</b> removes. Steps in your ideal path that never occur under the current "
        "filters are shown <b>dimmed</b>, so gaps are obvious.",
        """<div class="mock"><div class="ideal">
      <div class="scard"><span class="sn">Browse Catalog</span><span class="sc">96%</span></div>
      <div class="chev">⌄</div>
      <div class="scard"><span class="sn">Add to Basket</span><span class="sc">71%</span></div>
      <div class="chev">⌄</div>
      <div class="scard dim"><span class="sn">Apply Voucher</span><span class="sc">not seen</span></div>
      <div class="chev">⌄</div>
      <div class="scard"><span class="sn">Checkout</span><span class="sc">68%</span></div>
    </div><p class="cap">Each card shows its <b>coverage</b> — the share of journeys that pass through
      that step. “Apply Voucher” is dimmed: it’s in the ideal but not in the filtered data.</p></div>""",
        None,
        None,
    ),
    (
        "Splits — legitimate alternatives that rejoin",
        "Real processes branch. Add a <b>⑂ Split</b> where the process may take one of several valid "
        "routes; fill each <b>branch</b> with its own steps. Steps you add <i>after</i> the split are "
        "the shared continuation all branches lead into — name the split (✎) and the rejoin (⑃). A "
        "branch can itself contain a split (nesting).",
        """<div class="mock"><div class="ideal">
      <div class="scard"><span class="sn">Select Payment</span></div>
      <div class="fork">⑂ payment method</div>
      <div class="branches">
        <div class="branch"><div class="bt">Branch 1</div><div class="scard sm"><span class="sn">Credit Card</span></div></div>
        <div class="branch"><div class="bt">Branch 2</div><div class="scard sm"><span class="sn">PayPal</span></div></div>
      </div>
      <div class="fork join">⑃ rejoin</div>
      <div class="scard"><span class="sn">Order Confirmed</span></div>
    </div><p class="cap">Both routes are “happy” — a journey taking either is scored fairly, not
      penalised for the alternative it didn’t take.</p></div>""",
        None,
        '<span class="k">Ending in a split?</span> If a split is the last thing on the path, its '
        "branches are simply alternative endings — there is no rejoin to name.",
    ),
    (
        "The conformance score",
        "The score is a <b>journey-count-weighted average of edge coverage</b>: for each real "
        "journey variant, the fraction of the ideal path’s transitions that the variant actually "
        "contains, weighted by how many journeys followed it. Every start-to-end route through the "
        "splits is considered, and each journey is scored against the route it <b>matches best</b>.",
        """<div class="mock"><div class="row" style="gap:16px">
      <div class="scorebadge good"><span class="sb-t">🪧 Conformance</span><span class="sb-v">0.82</span></div>
      <div class="scorebadge warn"><span class="sb-t">🪧 Conformance</span><span class="sb-v">0.48</span></div>
      <div class="scorebadge bad"><span class="sb-t">🪧 Conformance</span><span class="sb-v">0.21</span></div>
    </div><p class="cap"><b>1.00</b> — every journey follows the ideal path perfectly ·
      <b>0.00</b> — no journey shares a single transition with it. Green ≥ 0.70 · orange in
      between · red ≤ 0.30.</p></div>""",
        None,
        None,
    ),
    (
        "Read it, refine it",
        "The badge sits in the top bar; the per-step coverage on the ideal cards shows <i>where</i> "
        "journeys drift. Tune the ideal path (or the split routes) and press <b>↻ Recompute "
        "conformance</b> to re-score against the journeys currently loaded.",
        None,
        [
            "A low score with a well-drawn ideal path means real journeys diverge — inspect the "
            "actual map on the left (in Journey %) to see where.",
            "Because splits are scored fairly, add them for every <b>legitimate</b> variation so you "
            "don’t punish valid behaviour.",
            "The Happy Path result is also appended to the <b>AI supported Documentation</b> report.",
        ],
        None,
    ),
]

BEYOND = [
    "<b>Advanced view.</b> Happy Path is available to Power users and administrators (see the "
    "Users &amp; Permissions guide).",
    "<b>Layout is remembered.</b> The width you drag the ideal-path editor to is saved per user, "
    "and each Happy Path keeps its own node layout.",
    "<b>Scored fairly.</b> Every route through the splits is evaluated and each journey takes the "
    "best-matching one — a case following a valid alternative is never unfairly penalised.",
    "<b>It measures, it doesn't change.</b> Defining a Happy Path never alters your data; it only "
    "compares reality against your intended design.",
]

CSS = r"""
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415;
  --good:#1e9e5a; --bad:#d4453b; --orange:#d98324;
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
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px}
.flow.sm{font-size:12px}
.node{border:1px solid var(--line);border-radius:8px;padding:5px 9px;background:var(--card);font-weight:600}
.node.good{border-color:rgba(30,158,90,.5);background:rgba(30,158,90,.1);color:var(--good)}
.arrow{color:var(--soft);font-weight:700}
/* split view */
.split{display:flex;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.pane{flex:1;min-width:0;padding:12px 14px}
.pane .ph{font-size:13px;font-weight:750;color:var(--soft);margin-bottom:10px}
.divider{flex:0 0 auto;width:34px;display:grid;place-items:center;background:rgba(58,109,240,.06);
  border-left:1px solid var(--line);border-right:1px solid var(--line)}
/* ideal-path column */
.ideal{display:flex;flex-direction:column;align-items:center;gap:0}
.scard{display:flex;align-items:center;gap:10px;border:1px solid rgba(30,158,90,.4);
  background:rgba(30,158,90,.08);border-radius:9px;padding:8px 14px;min-width:230px;justify-content:center}
.scard.sm{min-width:150px;padding:6px 12px}
.scard .sn{font-weight:700;color:var(--ink)}
.scard .sc{font-size:12px;font-weight:750;color:var(--good)}
.scard.dim{border-color:var(--line);background:rgba(120,120,128,.08)}
.scard.dim .sn{color:var(--soft);font-weight:600}
.scard.dim .sc{color:var(--soft)}
.chev{color:var(--soft);font-size:13px;line-height:1;padding:3px 0}
.fork{color:var(--soft);font-size:12.5px;font-weight:700;padding:7px 0}
.fork.join{color:var(--accent)}
.branches{display:flex;gap:14px;align-items:flex-start}
.branch{display:flex;flex-direction:column;align-items:center;gap:0;padding:0 6px;
  border-left:1px solid var(--line)}
.branch:first-child{border-left:0}
.branch .bt{font-size:11px;font-weight:700;color:var(--soft);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:6px}
/* score badges */
.scorebadge{display:inline-flex;flex-direction:column;align-items:center;gap:2px;border-radius:12px;
  padding:8px 16px;border:1.5px solid var(--line);background:var(--card)}
.sb-t{font-size:11px;font-weight:700;color:var(--soft);text-transform:uppercase;letter-spacing:.04em}
.sb-v{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums}
.scorebadge.good{border-color:rgba(30,158,90,.45)} .scorebadge.good .sb-v{color:var(--good)}
.scorebadge.warn{border-color:rgba(217,131,36,.45)} .scorebadge.warn .sb-v{color:var(--orange)}
.scorebadge.bad{border-color:rgba(212,69,59,.45)} .scorebadge.bad .sb-v{color:var(--bad)}
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
<title>58 - Happy Path</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Guide</span>
  <h1>Happy Path</h1>
  <p>Draw the ideal sequence a process should follow — with legitimate alternatives that branch
     and rejoin — then get one number: how closely the real journeys actually follow it.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    A <b>Happy Path</b> is your intended process, written down as an ordered sequence (with
    <b>splits</b> for valid alternatives). The view scores every real journey against it — a
    <b>journey-count-weighted edge coverage</b> from 0 to 1 — so you can see, in one figure and
    step by step, where reality drifts from the design. Defining it never changes your data.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">The Happy Path turns “this is how it should work” into a measurable, trackable
      score — and shows exactly which steps and routes pull it down.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — Happy Path</footer>
</div>
</body></html>
'''


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
