#!/usr/bin/env python3
"""Generate the self-contained HTML guide to the sidebar Filters: every filter
sub-section with a worked example, how they combine, and how they are applied.

Self-contained (CSS-drawn mocks, no screenshots). Facts mirror the in-app Help /
manual chapter 8.
Run:  python3 docs/52-build-filters-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "52-Filters.html"
_BUILDER = pathlib.Path(__file__).name

_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

STEPS = [
    (
        "One journey set, narrowed from every side",
        "Every filter narrows the <b>same</b> set of journeys, and they combine with <b>AND</b>: a "
        "journey is kept only if it satisfies <b>all</b> of them. Clearing one sub-section drops just "
        "that condition, leaving the rest in place.",
        """<div class="mock"><div class="flist">
      <div class="fitem">✓ falls inside the <b>date window</b></div>
      <div class="fitem">✓ contains <b>every</b> Include step</div>
      <div class="fitem">✓ contains <b>none</b> of the Exclude steps</div>
      <div class="fitem">✓ its length, duration &amp; score sit inside the <b>sliders</b></div>
      <div class="fitem">✓ matches every <b>Meta</b> value you set</div>
    </div><p class="cap">Edits are <b>staged</b> in the sidebar; they reach the chart when you press
      <b>Apply</b> (step 6).</p></div>""",
        None,
        None,
    ),
    (
        "Date window",
        "The <b>Date</b> sub-section sets the <b>From</b> / <b>To</b> window — only journeys inside it "
        "are counted. The date slider above the chart is the same window; drag its handles to sweep "
        "through time and the map redraws live.",
        """<div class="mock"><div class="row" style="gap:12px">
      <span class="pick">From <b>2026-01-01</b></span><span class="arrow">→</span>
      <span class="pick">To <b>2026-01-31</b></span>
    </div><p class="cap"><b>Example:</b> “only January”. Widen the window and older journeys re-enter;
      narrow it to zoom into a spike.</p></div>""",
        None,
        None,
    ),
    (
        "Include & Exclude steps",
        "<b>Include Steps</b> keeps only journeys that contain <b>all</b> the chosen steps; "
        "<b>Exclude Steps</b> drops any journey that contains <b>any</b> of them. A step can’t be on "
        "both sides — picking it on one disables it on the other.",
        """<div class="mock"><div class="row" style="gap:22px;align-items:flex-start">
      <div><div class="lab">Include Steps</div><div class="steplist">
        <div class="srow on">◉ Checkout</div>
        <div class="srow on">◉ Payment Confirmed</div>
        <div class="srow">○ Browse Catalog</div></div></div>
      <div><div class="lab">Exclude Steps</div><div class="steplist">
        <div class="srow on">◉ Payment Failed</div>
        <div class="srow">○ Return Initiated</div></div></div>
    </div><p class="cap"><b>Example:</b> journeys that reached <b>Checkout</b> and <b>Payment
      Confirmed</b> but never hit <b>Payment Failed</b>. On the map, a node’s menu offers
      <b>✓ Require in journeys</b> / <b>⊖ Exclude from journeys</b> — one click writes into these
      lists and reloads.</p></div>""",
        None,
        None,
    ),
    (
        "The range sliders — length, time, score",
        "Three dual-handle sliders keep journeys whose <b>number of steps</b>, <b>total duration</b> "
        "or <b>total score</b> fall inside a range. Each spans the project’s own min–max.",
        """<div class="mock">
      <div class="sl"><span class="sllab">Num Steps</span>
        <div class="track"><i style="left:12%;right:26%"></i><b style="left:12%"></b><b style="left:74%"></b></div>
        <span class="slval">4 – 12</span></div>
      <div class="sl"><span class="sllab">Journey Time</span>
        <div class="track"><i style="left:6%;right:48%"></i><b style="left:6%"></b><b style="left:52%"></b></div>
        <span class="slval">3m – 2d</span></div>
      <div class="sl"><span class="sllab">Journey Score</span>
        <div class="track"><i style="left:40%;right:6%"></i><b style="left:40%"></b><b style="left:94%"></b></div>
        <span class="slval">+5 – +40</span></div>
    </div><p class="cap"><b>Example:</b> “short, high-value journeys” — 4–12 steps, up to 2 days,
      score ≥ +5. <b>Journey Score</b> is the sum of the step scores a journey passes through.</p></div>""",
        None,
        '<span class="k">Only where it makes sense.</span> A slider is disabled when the project’s '
        "min equals its max (nothing to range over).",
    ),
    (
        "Meta filters",
        "If the project defines case-level attributes (<b>META_1–3</b>, shown with your business "
        "names), each gets an <b>autocomplete</b> field. Focus it to list the distinct values, or type "
        "to narrow; every field you set must match.",
        """<div class="mock"><div class="combos">
      <div class="combo"><span class="clab">Payment</span><span class="cval">PayPal <span class="cv">▾</span></span></div>
      <div class="combo"><span class="clab">Segment</span><span class="cval">Premium <span class="cv">▾</span></span></div>
      <div class="combo"><span class="clab">Order value</span><span class="cval">High (&gt;100 EUR) <span class="cv">▾</span></span></div>
    </div><p class="cap"><b>Example:</b> “PayPal orders from Premium customers over €100.” The Meta
      section appears only when the project has meta titles; up to 50 distinct values are listed.</p></div>""",
        None,
        None,
    ),
    (
        "Apply, reset, presets — and Event ID",
        "Filters are <b>staged</b> until you commit them. <b>Apply</b> reloads the map (or, in "
        "Statistics, recomputes that view); <b>↺ Reset</b> restores the project defaults; <b>🔖 Save "
        "Preset</b> stores the whole set to reapply later. Presets are <b>per chart</b>, so A-Chart "
        "and B-Chart can each carry their own.",
        """<div class="mock"><div class="btnrow">
      <span class="tb">↺ Reset</span><span class="tb">🔖 Save Preset…</span><span class="tb prom">Apply</span>
    </div>
    <div class="row" style="margin-top:14px"><span class="pick">Event ID <b>ORD-000123</b></span>
      <span class="cap" style="margin:0 0 0 8px">→ pulls up one journey (Individual Journey view)</span></div>
    </div>""",
        [
            "Staged filters also apply when you <b>click a preset</b>, use a node’s "
            "<b>✓ Require</b> / <b>⊖ Exclude</b> action, or <b>release</b> a handle of the date /"
            " journey-time slider above the chart.",
            "In <b>Individual Journey</b> mode the Filters section becomes a single <b>Event ID</b> "
            "field — type a source id (auto-hashed) or a raw 32-char hash to load exactly one journey.",
            "In <b>A/B Comparison</b> each side stages and applies its filters independently; "
            "<b>Statistics</b> always starts from the A-Chart’s filters.",
        ],
        None,
    ),
]

BEYOND = [
    "<b>AND, always.</b> Filters never widen the set — each one only removes journeys. To see more, "
    "clear a sub-section (its ⊗) rather than adding another filter.",
    "<b>Staged, not live.</b> Typing and dragging in the sidebar previews nothing until <b>Apply</b> "
    "(or a preset, a node action, or a slider release) commits it — so you can set several filters "
    "before a single reload.",
    "<b>Presets carry the lot.</b> A saved preset restores the date window, include/exclude lists, "
    "all three sliders and the meta fields in one click, per chart.",
    "<b>Advanced views inherit A-Chart.</b> Statistics, Conformance and the AI report all read the "
    "A-Chart's current filters, so set the segment there first.",
]

CSS = r"""
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415; --good:#1e9e5a;
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
.step ul li code, .cap code{background:var(--bg);border-radius:4px;padding:0 5px;font-size:12.5px}
.tip{background:var(--tipbg);border-left:4px solid var(--tipbar);color:var(--tipink);
  border-radius:8px;padding:10px 14px;margin:0 0 16px;font-size:14.5px}
.tip b{color:var(--tipink)} .tip .k{font-weight:700;margin-right:6px}
.beyond{background:var(--warnbg);border:1px solid #f0d9b8;border-left:4px solid var(--warnbar);
  color:var(--warnink);border-radius:14px;padding:20px 22px;margin:34px 0 0}
.beyond h2{margin:0 0 8px;font-size:19px;color:#7a4d13}
.beyond ul{margin:8px 0 0;padding-left:20px}
.beyond li{margin:4px 0}
.beyond .note{margin-top:12px;font-size:14.5px}
footer{color:var(--soft);font-size:13px;text-align:center;margin-top:34px}
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.arrow{color:var(--soft);font-weight:700}
.lab{color:var(--soft);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}
.pick{border:1px solid var(--line);border-radius:9px;padding:7px 12px;background:var(--bg);font-size:13.5px}
/* the "kept if" list */
.flist{display:flex;flex-direction:column;gap:6px}
.fitem{border:1px solid rgba(30,158,90,.35);background:rgba(30,158,90,.07);border-radius:9px;
  padding:8px 13px;font-size:14px;color:var(--ink)}
.fitem b{color:var(--good)}
/* step lists */
.steplist{border:1px solid var(--line);border-radius:10px;overflow:hidden;min-width:190px}
.srow{padding:7px 12px;border-bottom:1px solid var(--line);font-size:13.5px;color:var(--soft)}
.srow:last-child{border-bottom:0}
.srow.on{color:var(--accent);font-weight:700;background:rgba(58,109,240,.06)}
/* range sliders */
.sl{display:flex;align-items:center;gap:12px;margin:10px 0}
.sllab{flex:0 0 110px;font-size:13px;font-weight:650;color:var(--soft)}
.track{position:relative;flex:1;height:6px;border-radius:4px;background:var(--line)}
.track i{position:absolute;top:0;bottom:0;background:var(--accent);border-radius:4px}
.track b{position:absolute;top:50%;width:14px;height:14px;margin-left:-7px;transform:translateY(-50%);
  border-radius:50%;background:#fff;border:2px solid var(--accent);box-shadow:0 1px 3px rgba(20,30,50,.3)}
.slval{flex:0 0 auto;font:600 12.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink)}
/* meta combos */
.combos{display:flex;gap:12px;flex-wrap:wrap}
.combo{flex:1;min-width:160px}
.combo .clab{display:block;font-size:12px;font-weight:700;color:var(--soft);text-transform:uppercase;
  letter-spacing:.04em;margin-bottom:4px}
.combo .cval{display:flex;justify-content:space-between;align-items:center;border:1px solid var(--line);
  border-radius:8px;padding:7px 11px;font-size:13.5px;font-weight:600;background:var(--card)}
.combo .cv{color:var(--soft)}
/* button row */
.btnrow{display:flex;gap:8px;flex-wrap:wrap}
.tb{border:1px solid var(--line);border-radius:8px;padding:7px 13px;font-size:13.5px;font-weight:650;background:var(--card)}
.tb.prom{background:var(--accent);border-color:var(--accent);color:#fff}
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
<title>52 - Filters</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Guide</span>
  <h1>Filters</h1>
  <p>The sidebar filters carve a large event log down to the journeys you care about — by date,
     by the steps a journey did or didn't take, by its length, duration, score and case
     attributes. Every filter, with a worked bookstore example.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    Filters answer “which journeys?”. They all narrow the <b>same</b> set and combine with
    <b>AND</b>, they are <b>staged</b> until you press <b>Apply</b>, and the whole set can be saved
    as a <b>preset</b>. This guide walks every sub-section — date, include/exclude steps, the three
    range sliders, and meta attributes — with an example for each.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Think of it as one sentence: “journeys <i>within these dates</i> that <i>did
      these steps</i>, <i>not those</i>, <i>this long / this valuable</i>, for <i>these
      customers</i>.” Each filter is one clause.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — Filters</footer>
</div>
</body></html>
'''


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
