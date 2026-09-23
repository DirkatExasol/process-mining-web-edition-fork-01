#!/usr/bin/env python3
"""Generate the self-contained HTML guide "60 - Working with an AI Agent".

A generic overview of Conversational Process Mining: talking to your process data through
an AI agent (via the MCP server) instead of only clicking charts. Concept, building blocks,
what you can ask, the read-only boundary, and where to go next (guides 15 and 61).

Run:  python3 docs/60-build-ai-agent-overview-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "60-Working-with-an-AI-Agent.html"
_BUILDER = pathlib.Path(__file__).name

_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each chapter: (title, body_html, mock_html | None, bullets | None, tip_html | None).
STEPS = [
    (
        "What “Conversational Process Mining” means",
        "<b>Conversational Process Mining</b> is asking questions about your processes in plain "
        "language and letting an AI agent answer them from the live data — instead of (or "
        "alongside) opening charts and setting filters by hand. You type <i>&ldquo;which process "
        "has the most journeys, and where does it get stuck?&rdquo;</i>; the agent queries the "
        "Process Mining tool, reads the numbers back, and can immediately drill into the cases "
        "behind them. The chart-driven Workbench and the conversation are two views of the "
        "<b>same data</b> — use whichever fits the question.",
        None,
        None,
        '<span class="k">Same data, different door.</span> The agent can only see what you can '
        "see in the app: your assigned connections, the same projects, the same journeys. It is "
        "a faster way to <i>ask</i>, not a way to reach more.",
    ),
    (
        "How it works — the building blocks",
        "Three pieces connect your words to your data. You set them up once (guides 15 and 61); "
        "after that it is just conversation.",
        """<div class="mock">
      <pre class="calc">You ──ask in plain language──▶ AI agent (Claude, …)
                                   └─ picks and calls read-only MCP tools
AI agent ──MCP + OAuth token──▶ MCP server (the 7th surface)
                                   └─ verifies you via Authentik
                                   └─ answers from your assigned connections</pre>
      <table class="tbl">
        <tr><th>Piece</th><th>Role</th></tr>
        <tr><td><b>MCP server</b></td><td>The read-only query endpoint on the Process Mining side (metrics, paths, metadata). Off until an admin enables it.</td></tr>
        <tr><td><b>OAuth provider</b> (Authentik)</td><td>Proves who you are; the token maps to your Process Mining user and its connection assignments.</td></tr>
        <tr><td><b>AI client</b> (Claude Desktop)</td><td>Where you have the conversation. It discovers the tools and calls them for you.</td></tr>
      </table>
    </div>""",
        None,
        None,
    ),
    (
        "What you can ask",
        "The agent has a small set of <b>read-only</b> tools covering the same ground as the "
        "Workbench. In practice you never name the tools — you ask in words and the agent maps "
        "your question to them. Typical things to ask:",
        None,
        [
            "<b>Discover</b> — &ldquo;What connections and projects can I see? Which project has "
            "the most journeys?&rdquo;",
            "<b>Shape of the process</b> — &ldquo;Show me the process map for project 1&rdquo;, "
            "&ldquo;What are the most common paths (variants)?&rdquo;",
            "<b>Performance</b> — &ldquo;What's the average and median time between <i>Approve</i> "
            "and <i>Ship</i>? Where are the slowest transitions?&rdquo;",
            "<b>KPIs</b> — &ldquo;How many journeys in the last 30 days, and what's the "
            "process-goodness score?&rdquo;",
            "<b>Drill down</b> — &ldquo;List the five slowest cases that hit <i>Payment "
            "Failed</i>&rdquo;, then &ldquo;show me the full trace of that first one&rdquo;.",
            "<b>Metadata</b> — &ldquo;What do the meta attributes mean, and what's the date "
            "range of the data?&rdquo;",
            "<b>Notes &amp; review</b> — &ldquo;What open URGENT notes are on this process, "
            "grouped by step? Show me the shared notes but not my personal ones.&rdquo;",
        ],
        '<span class="k">Follow-ups are the point.</span> Answers become the next question — '
        '&ldquo;now filter to March&rdquo;, &ldquo;only the department = Finance cases&rdquo;, '
        "&ldquo;compare that with the sample set&rdquo;. The agent chains tools across the "
        "conversation.",
    ),
    (
        "The drill-down mental model",
        "The single most useful pattern is going from an <b>aggregate</b> to the actual "
        "<b>cases</b> behind it, then to <b>one trace</b>. Aggregates tell you <i>where</i> to "
        "look; the journey tools tell you <i>what happened</i>.",
        """<div class="mock">
      <pre class="calc">"how's project 1 doing?"        →  overall stats (count, durations, goodness)
"the slowest cases that hit X"  →  a shortlist of individual journeys
"show me that one"              →  the full ordered trace of a single case</pre>
      <p class="cap">Because the tools return real case ids, the agent can walk this chain on
        its own: a statistic → the cases → one journey's step-by-step timeline.</p>
    </div>""",
        None,
        None,
    ),
    (
        "Good to keep in mind",
        "A few habits make the conversation accurate and safe:",
        None,
        [
            "<b>Name the connection and project</b> when you have several — &ldquo;on connection "
            "<i>Prod</i>, project 1&rdquo; — so the agent doesn't guess.",
            "<b>Read-only, always.</b> There is no tool to write, delete, sample or edit — the "
            "agent cannot change your data or configuration.",
            "<b>Your boundary travels with the token.</b> If a connection isn't assigned to you, "
            "the agent can't query it, and it will say so.",
            "<b>Numbers come from the database</b>, not the model — the agent reports what the "
            "tools return. If it can't get data, it tells you rather than inventing it.",
        ],
        None,
    ),
    (
        "Getting started",
        "Two short guides take you from nothing to a working conversation:",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Guide</th><th>What it covers</th></tr>
        <tr><td><b>15 · Installation of MCP Server</b></td><td>The admin/operator side: enable the MCP server and connect it to your Authentik OAuth provider.</td></tr>
        <tr><td><b>61 · Conversational Process Mining with Claude Desktop</b></td><td>Your side: add the connector in Claude Desktop, sign in, and start asking — with example queries.</td></tr>
      </table>
    </div>""",
        None,
        '<span class="k">Already enabled for you?</span> If an administrator has set the MCP '
        "server up, skip straight to guide 61 and add the connector in Claude Desktop.",
    ),
]

BEYOND = [
    "<b>Any MCP-capable AI client works.</b> Claude Desktop is the worked example (guide 61); "
    "the same idea applies to any client that supports remote HTTP MCP servers with OAuth — "
    "more client walkthroughs to follow.",
    "<b>It complements the Workbench, it doesn't replace it.</b> Use the conversation for quick "
    "questions and drill-downs; switch to the charts when you want to see the map, tune filters "
    "visually, or compare A/B.",
    "<b>Nothing new to secure on your side.</b> You sign in through the same OAuth provider your "
    "organisation already trusts; the agent never handles a database password.",
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
.hero a{color:#fff}
.lead{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 22px;
  margin:0 0 30px;color:var(--soft)}
.lead b{color:var(--ink)}
.lead code, .step ul li code, .cap code, .step p.body code{background:var(--bg);border-radius:4px;
  padding:0 5px;font-size:13px}
.step{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 22px 8px;
  margin:0 0 22px;box-shadow:0 1px 2px rgba(20,30,50,.04)}
.step-head{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.num{flex:0 0 auto;width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  font-weight:800;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent2))}
.step h2{font-size:20px;margin:0;font-weight:750}
.step p.body{margin:2px 0 16px}
.step p.body a{color:var(--accent)}
.step ul{margin:0 0 12px;padding-left:20px;color:var(--soft)}
.step ul li{margin:3px 0}
.tip{background:var(--tipbg);border-left:4px solid var(--tipbar);color:var(--tipink);
  border-radius:8px;padding:10px 14px;margin:0 0 16px;font-size:14.5px}
.tip b{color:var(--tipink)}
.tip .k{font-weight:700;margin-right:6px}
.tip code{background:rgba(58,109,240,.10);border-radius:4px;padding:0 4px;font-size:13px}
.beyond{background:var(--warnbg);border:1px solid #f0d9b8;border-left:4px solid var(--warnbar);
  color:var(--warnink);border-radius:14px;padding:20px 22px;margin:34px 0 0}
.beyond h2{margin:0 0 8px;font-size:19px;color:#7a4d13}
.beyond ul{margin:8px 0 0;padding-left:20px}
.beyond li{margin:3px 0}
.beyond code{background:rgba(0,0,0,.06);border-radius:4px;padding:0 4px;font-size:13px}
.beyond .note{margin-top:12px;font-size:14.5px}
footer{color:var(--soft);font-size:13px;text-align:center;margin-top:34px}
.mock{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin:0 0 16px;box-shadow:0 6px 18px rgba(20,30,50,.08)}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.tbl{border-collapse:collapse;font-size:13px;width:100%}
.tbl th{color:var(--soft);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;
  text-align:left;padding:4px 12px 6px 0;border-bottom:2px solid var(--line)}
.tbl td{padding:5px 12px 5px 0;border-bottom:1px solid var(--line);vertical-align:top}
.tbl td code{background:var(--bg);border-radius:4px;padding:0 4px;font-size:12px}
.calc{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px;
  margin:0;font:12.5px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;
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
<!-- Generated documentation page — open this file in a WEB BROWSER.
     It is NOT a script; to rebuild it run:  python3 docs/{_BUILDER} -->
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>60 - Working with an AI Agent</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Conversational Process Mining</span>
  <h1>Working with an AI Agent</h1>
  <p>Ask your processes questions in plain language and let an AI agent answer from the live
     data. This overview explains <b>Conversational Process Mining</b> — the idea, the pieces
     that make it work, and what you can ask.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    <b>Conversational Process Mining</b> turns process analysis into a dialogue: you ask, an
    AI agent queries the Process Mining tool through its read-only <b>MCP server</b>, and you
    get answers you can immediately drill into — all within the same data boundary as the app.
    It sits beside the chart-driven Workbench, not on top of it.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Next: <b>guide 15</b> to enable the MCP server, then
      <b>guide 61</b> to connect Claude Desktop and start asking.</p>
  </div>

  <footer>Process Mining Demonstrator · Suite — Working with an AI Agent (Conversational Process Mining)</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
