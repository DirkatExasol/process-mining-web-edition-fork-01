#!/usr/bin/env python3
"""Generate a self-contained HTML quick-start guide for everyday (standard) users.
Screenshots are embedded as base64 data URIs so the single .html file needs nothing else."""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "manual" / "screenshots"
OUT = ROOT / "docs" / "Work-Bench-Quick-Start.html"


def data_uri(name: str) -> str:
    b = (SHOTS / name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(b).decode()


STEPS = [
    (
        "app-login.png",
        "Sign in",
        "Open the Work-Bench in your browser and enter your <b>username</b> and <b>password</b>. "
        "If your organisation requires it, you will then confirm a 6-digit code from your "
        "authenticator app, or sign in with a <b>passkey</b> (Touch&nbsp;ID, Windows&nbsp;Hello or a "
        "security key).",
        "The background image and the version line are set by your administrator — they do not "
        "affect how you sign in.",
    ),
    (
        "app-01-shell.png",
        "Find your data",
        "After signing in you land in the Work-Bench: the <b>sidebar</b> on the left, an empty chart "
        "area on the right. Open the <b>Connections</b> section and click the connection your "
        "administrator assigned to you. A green dot shows you are connected.",
        "Creating or editing connections is an administrator task, so you will not see a &#65291; "
        "button here — just pick the one that was shared with you.",
    ),
    (
        "app-02-projects.png",
        "Open a project",
        "Open the <b>Projects</b> section and select a project. The A-Chart loads automatically and "
        "the sidebar tidies its sections away so the map has room.",
        "A project is one process &mdash; for example an order-to-cash flow or a support workflow.",
    ),
    (
        "app-03-achart.png",
        "Read the A-Chart",
        "The <b>A-Chart</b> is your process map, discovered directly from the data. <b>Boxes are "
        "steps</b>, <b>arrows are the transitions</b> between them, and a <b>thicker arrow</b> means "
        "the selected metric is higher. The tiles across the top (KPIs) summarise the filtered data.",
        "Map vocabulary: a node is a step, an arrow is a transition, a dashed box is a group of "
        "steps, and the tiles above are KPIs.",
    ),
    (
        "app-04-metrics.png",
        "Choose a metric",
        "The <b>Metrics</b> chips decide what the arrow thickness means: <b>Count</b>, <b>Percentage</b> "
        "(share of a step&rsquo;s outgoing journeys), <b>Journey&nbsp;%</b> (share of all journeys), or "
        "the transition times <b>Avg</b>, <b>Min</b>, <b>Max</b> and <b>Std&nbsp;Dev</b>. Exactly one "
        "is active at a time.",
        "Each chart view remembers its own metric independently.",
    ),
    (
        "app-05-filters.png",
        "Filter to your question",
        "The <b>Filters</b> section narrows the picture: a <b>date range</b>, steps that must or must "
        "not appear, how many steps a journey has, how long it took, its score, and up to three "
        "business (meta) fields. An active filter shows a badge; the &#8855; clears just that one. "
        "Save a useful combination as a <b>preset</b> to reuse later.",
        "Filters drive everything at once &mdash; the map, the KPIs and every other view update "
        "together.",
    ),
    (
        "app-12-individual-journey.png",
        "Follow a single case",
        "Switch the view menu to <b>Individual Journey</b>, type an <b>Event&nbsp;ID</b> in the "
        "sidebar and press <b>Load Journey</b>. One case is drawn step by step, with the time shown "
        "on each node and its own KPI tiles above.",
        None,
    ),
    (
        "app-10-b-chart.png",
        "Bring in a second view (B-Chart)",
        "The <b>B-Chart</b> is a second, fully independent process map with its own filters and its "
        "own layout. Use it to set up a &ldquo;before vs after&rdquo; or &ldquo;region&nbsp;A vs "
        "region&nbsp;B&rdquo; picture.",
        None,
    ),
    (
        "app-11-a-b-comparison.png",
        "Compare side by side (A/B Comparison)",
        "<b>A/B Comparison</b> puts panel A and panel B next to each other, with a <b>similarity "
        "badge</b> along the bottom, so you can see at a glance how the two filtered pictures differ.",
        "Set the filters on each panel first (in A-Chart and B-Chart), then switch to A/B Comparison "
        "to view them together.",
    ),
    (
        "app-14-statistics.png",
        "Dig into the numbers (Statistics)",
        "The <b>Statistics</b> view lists the most common <b>routes</b> (journey variants) in a "
        "sortable table, above a journeys-over-time chart. Sort to find the busiest or the rarest "
        "paths.",
        None,
    ),
    (
        "app-17-notes.png",
        "Capture what you find (Notes)",
        "Add a <b>note</b> to any step or transition to record an observation. Give it a title and an "
        "importance; it keeps the exact filter context so it still makes sense later. You and your "
        "colleagues can search, filter and mark notes as resolved.",
        None,
    ),
    (
        "app-13-ai-supported-documentation.png",
        "Optional: AI-supported Documentation",
        "If your connection has an AI model attached, the <b>AI supported Documentation</b> view "
        "turns the current A-Chart and its context into a written report you can save as a PDF. The "
        "cards shown before you run it summarise exactly what will be sent.",
        "You can generate the report; editing the underlying analysis prompt is reserved for advanced "
        "users.",
    ),
    (
        "app-19-help.png",
        "Help, preferences & your account",
        "The <b>?</b> button (or <b>&#8984;/Ctrl&nbsp;+&nbsp;/</b>) opens the floating Help panel. The "
        "<b>Configuration</b> section holds display preferences &mdash; theme, font sizes and KPI "
        "order. At the very bottom of the sidebar you can manage <b>two-factor</b> / <b>passkeys</b> "
        "and <b>sign out</b>.",
        None,
    ),
]

BEYOND = [
    "Journey <b>Sampling</b>",
    "<b>Conformance Check</b> and <b>Happy Path</b>",
    "<b>Simulation</b>",
    "Creating or editing <b>connections</b>",
    "Editing the <b>AI analysis prompt</b>",
    "The <b>Action Designer</b> and <b>Integration</b> console",
    "The <b>Administration</b> site",
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
.shot{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:12px;
  box-shadow:0 6px 18px rgba(20,30,50,.10);margin:0 0 16px}
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
@media (prefers-color-scheme:dark){
  :root{--bg:#14171c;--card:#1d2127;--ink:#e7eaee;--soft:#a3adba;--line:#2c333c;
    --tipbg:#182338;--tipink:#cdd9f5;--warnbg:#2a2213;--warnink:#e9d3ac}
}
@media print{
  body{background:#fff}
  header.hero{box-shadow:none;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .step,.lead,.beyond{break-inside:avoid;box-shadow:none}
  .shot{box-shadow:none}
}
"""


def render() -> str:
    steps_html = []
    for i, (img, title, body, tip) in enumerate(STEPS, start=1):
        tip_html = (
            f'<div class="tip"><span class="k">Tip</span>{tip}</div>' if tip else ""
        )
        steps_html.append(
            f"""<section class="step">
  <div class="step-head"><div class="num">{i}</div><h2>{html.escape(title)}</h2></div>
  <p class="body">{body}</p>
  <img class="shot" alt="{html.escape(title)}" src="{data_uri(img)}">
  {tip_html}
</section>"""
        )
    beyond_items = "\n".join(f"<li>{b}</li>" for b in BEYOND)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Work-Bench Quick-Start</title>
<style>{CSS}</style>
</head><body>
<header class="hero"><div class="hero-inner">
  <span class="chip">For everyday users</span>
  <h1>Process Mining Work-Bench<br>Quick-Start Guide</h1>
  <p>A short, step-by-step walk through a simple analysis &mdash; from signing in to sharing what
     you find &mdash; using only the features available to a standard user.</p>
</div></header>
<div class="wrap">
  <div class="lead">This guide follows one path end to end: <b>sign in &rarr; open a project &rarr;
    read the A-Chart &rarr; filter &rarr; compare with A/B &rarr; record your findings</b>. Everything
    here is available without any special role &mdash; no setup or administration required.</div>
  {''.join(steps_html)}
  <div class="beyond">
    <h2>Beyond the basics</h2>
    <p>A few features are hidden from everyday users because they change shared data or configuration.
       They need a <b>Power user</b>, <b>Developer</b> or <b>Administrator</b> role:</p>
    <ul>{beyond_items}</ul>
    <p class="note">If you need one of these, ask your administrator &mdash; nothing you do as a
       standard user can change another person&rsquo;s data or the system&rsquo;s configuration.</p>
  </div>
  <footer>Process Mining Demonstrator &mdash; Work-Bench &middot; Everyday-user quick-start</footer>
</div>
</body></html>"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
