#!/usr/bin/env python3
"""Generate the self-contained HTML quick-start guide for drilling into Σ aggregates.

Unlike the Work-Bench / Administration guides, this one needs no screenshots — each step
carries a small CSS-drawn mock of the UI — so the single .html file is fully self-contained.
Run:  python3 docs/build-drilldown-guide.py
"""
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "Drill-Down-Quick-Start.html"

# Each step: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
# body/mock/bullets/tip are passed through as HTML (only the title is escaped).
STEPS = [
    (
        "Spot a Σ aggregate step",
        "On a high-level process map, aggregated sub-processes appear as a single accent-coloured "
        "step whose name starts with <b>Σ</b>. In the left <b>Projects</b> list, aggregate maps are "
        "marked with a <b>Σ</b> too.",
        """<div class="mock"><div class="row">
      <span class="node">Check-in</span><span class="arrow">→</span>
      <span class="sig">Σ Security &amp; Boarding <small>Σ</small></span>
      <span class="arrow">→</span><span class="node">Gate</span>
    </div><p class="cap">The <b>Σ</b> step stands in for several real steps that were grouped together.</p></div>""",
        None,
        None,
    ),
    (
        "Open the step’s menu",
        "<b>Click the Σ step</b> to open its menu. An aggregate offers two ways to drill down — pick "
        "whichever suits what you’re doing.",
        """<div class="mock">
      <div class="menu">
        <div class="t">Σ Security &amp; Boarding</div>
        <div class="i acc">⤵ Drill down · new panel</div>
        <div class="i acc">⤵ Drill down · in place</div>
        <div class="i">✎ Show Notes</div>
      </div>
    </div>""",
        None,
        '<span class="k">Both use real numbers.</span> The two options show exactly the same '
        "figures — they only differ in <i>where</i> the detail appears.",
    ),
    (
        "“New panel” — the sub-process on its own",
        "Choose <b>Drill down · new panel</b> to open the aggregate’s steps in a pop-up panel, wired "
        "to the steps just before and after it. The panel shows:",
        """<div class="mock">
      <div class="flow">
        <span class="node ctx">Check-in</span>
        <span class="lbl">1,432</span><span class="arrow">→</span>
        <span class="node">Security</span><span class="arrow">→</span>
        <span class="node">Passport</span><span class="arrow">→</span>
        <span class="node">Boarding</span>
        <span class="lbl">1,290</span><span class="arrow">→</span>
        <span class="node ctx">Gate</span>
      </div>
      <div class="pills">
        <span class="pill on"># Count</span><span class="pill">% Percentage</span>
        <span class="pill">% Journey&nbsp;%</span><span class="pill">⏱ Avg&nbsp;Time</span>
        <span class="pill">⌄ Min</span><span class="pill">⌃ Max</span><span class="pill">〰 Std&nbsp;Dev</span>
      </div>
      <p class="cap">Dashed steps (Check-in, Gate) are the <b>incoming / outgoing</b> connections —
        shown for context, kept outside the aggregate. The chips switch the edge metric,
        just like the main map.</p>
    </div>""",
        [
            "The step’s <b>incoming and outgoing connections</b> (with their metrics) are drawn.",
            "The <b>date range</b> and <b>journey count</b> are shown at the top.",
            "Switch the <b>metric</b> with the chips (Count, %, Avg/Min/Max Time, Std Dev).",
            "The panel is <b>resizable</b> — drag its bottom-right corner; the chart re-fits.",
        ],
        '<span class="k">Tip.</span> The panel opens fitted to the whole sub-process. Close it with '
        "<b>✕</b> or <kbd>Esc</kbd> to return to the map.",
    ),
    (
        "“In place” — expand inside the map",
        "Choose <b>Drill down · in place</b> to burst the Σ step open <b>within the current map</b>: "
        "its real steps replace the Σ node and connect to the same neighbours, while everything else "
        "stays exactly where it was.",
        """<div class="mock"><div class="row">
      <span class="node">Check-in</span><span class="arrow">→</span>
      <span class="node">Security</span><span class="arrow">→</span>
      <span class="node">Passport</span><span class="arrow">→</span>
      <span class="node">Boarding</span><span class="arrow">→</span>
      <span class="node">Gate</span>
    </div><p class="cap">The Σ node is gone — its steps are now part of the map, in its place.</p></div>""",
        [
            "Surrounding steps and their group boxes <b>don’t move</b>; only the expanded part changes.",
            "Other Σ steps stay collapsed — you can expand <b>several</b> of them.",
            "To collapse back, use <b>⤴ Drill up</b> — the button above the map, or any step’s menu.",
        ],
        '<span class="k">Which one?</span> Use <b>in place</b> to keep the surrounding context while '
        "you look inside; use <b>new panel</b> to focus on just the sub-process.",
    ),
    (
        "Numbers follow your filters",
        "The drill-down always reflects your current <b>date window</b> — it’s shown in the panel — and "
        "updates automatically when you move the date slider or apply a filter. So a Σ step’s detail "
        "and the high-level map always tell the same story.",
        None,
        None,
        '<span class="k">Why totals can look higher inside.</span> An aggregate only hides steps for '
        "readability; the detail counts the same journeys as the high-level map for the same dates. "
        "(Journey-<i>duration</i>, score and step-count filters aren’t applied to the detail, because "
        "a collapsed map measures those differently than the full data.)",
    ),
]

BEYOND = [
    "<b>Drill down is read-only.</b> You’re inspecting the real process — nothing is changed.",
    "<b>Show or hide aggregates.</b> Under <b>Configuration → Aggregations</b> you can hide the "
    "aggregate detail projects/connections from the sidebar to keep it tidy; the high-level map "
    "always stays visible.",
    "<b>Who builds aggregates.</b> Creating Σ super-steps is a developer task; anyone who can open "
    "the map can drill into them.",
]

CSS = """
:root{
  --bg:#f6f7f9; --card:#ffffff; --ink:#1c2530; --soft:#5b6672; --line:#e5e8ec;
  --accent:#3a6df0; --accent2:#6b5cf0; --tipbg:#eef3ff; --tipink:#2b3a63; --tipbar:#3a6df0;
  --warnbg:#fff7ed; --warnbar:#d98324; --warnink:#5c4415;
  --sigma:#5b6bff;
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
kbd{background:var(--card);border:1px solid var(--line);border-bottom-width:2px;border-radius:6px;
  padding:1px 7px;font:600 13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace}
/* Mock illustrations (no screenshots needed) */
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.sig{display:inline-flex;align-items:center;gap:6px;background:var(--sigma);color:#fff;
  font-weight:800;border-radius:9px;padding:8px 14px}
.sig small{background:rgba(255,255,255,.22);border-radius:5px;padding:0 5px;font-weight:700}
.menu{width:270px;border:1px solid var(--line);border-radius:10px;overflow:hidden;
  background:var(--card);box-shadow:0 10px 26px rgba(20,30,50,.16);font-size:14px}
.menu .t{padding:8px 12px;font-weight:700;border-bottom:1px solid var(--line);background:rgba(0,0,0,.02)}
.menu .i{padding:9px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--line)}
.menu .i:last-child{border-bottom:0}
.menu .i.acc{color:var(--accent);font-weight:600}
.row{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
.flow{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px}
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);font-weight:600}
.node.ctx{opacity:.7;border-style:dashed}
.arrow{color:var(--soft);font-weight:700}
.lbl{color:var(--soft);font-size:11px}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.pill{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12.5px;background:var(--card)}
.pill.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.cap{color:var(--soft);font-size:13px;margin:6px 2px 0}
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
<title>Drill-Down Quick-Start</title>
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Quick-Start</span>
  <h1>Drilling into a Σ aggregate</h1>
  <p>An aggregate hides a busy part of the process behind one <b>Σ</b> super-step so the map
     stays readable. Drilling down reveals the real steps behind it — with the same numbers
     the full, un-aggregated map would show.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    An <b>aggregate</b> is only a way of <b>seeing</b> the process — it never changes the data.
    Wherever a <b>Σ</b> step appears on a map, you can open it to inspect the sub-process it
    stands for, either in a <b>separate panel</b> or expanded <b>right inside the map</b>.
    Every figure you see matches the original flowchart for the same date range.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Aggregates make a large process readable at a glance, and drill-down lets you go
      from that overview straight to the real detail — without ever leaving the numbers behind.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — Drilling into a Σ aggregate</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
