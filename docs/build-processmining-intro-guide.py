#!/usr/bin/env python3
"""Generate the self-contained HTML introduction to Process Mining (general, not
app-specific), using the Online Bookstore process as the running example.

Like the Drill-Down guide, every illustration is a small CSS-drawn mock — no
screenshots — so the single .html file is fully self-contained.
Run:  python3 docs/build-processmining-intro-guide.py
"""
import base64
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "Process-Mining-Introduction.html"

# App logo (frontend/web/public/logo.svg) embedded as a data-URI favicon, so the
# browser tab shows the suite's icon while the page stays fully self-contained.
_LOGO_SVG = (ROOT / "frontend" / "web" / "public" / "logo.svg").read_text(encoding="utf-8")
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(_LOGO_SVG.encode("utf-8")).decode("ascii")

# Each chapter: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
# body/mock/bullets/tip are passed through as HTML (only the title is escaped).
STEPS = [
    (
        "Everything starts with an event log",
        "Whenever a customer clicks through an online bookstore, the shop's systems quietly write "
        "it all down: <b>who</b> (an order), <b>did what</b> (a step), <b>and when</b> (a "
        "timestamp). Process mining needs nothing more than these three columns — data that "
        "almost every IT system already records.",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Order (case)</th><th>Step (activity)</th><th>Timestamp</th></tr>
        <tr><td>#1041</td><td>Login</td><td>09:02:11</td></tr>
        <tr><td>#1041</td><td>Browse Catalog</td><td>09:03:24</td></tr>
        <tr><td>#1041</td><td>Add to Basket</td><td>09:07:58</td></tr>
        <tr><td>#1042</td><td>Login</td><td>09:04:02</td></tr>
        <tr><td>#1041</td><td>Checkout</td><td>09:08:30</td></tr>
        <tr><td>#1042</td><td>Browse Catalog</td><td>09:05:11</td></tr>
      </table>
      <p class="cap">An <b>event log</b>: each row is one thing that happened to one order. The rows
        of different orders interleave — sorting by order and time untangles them.</p>
    </div>""",
        None,
        '<span class="k">The three essentials.</span> A <b>case ID</b> (which order / customer '
        "journey), an <b>activity</b> (what happened) and a <b>timestamp</b> (when). Extra columns "
        "— payment method, customer segment, order value — enrich the analysis later.",
    ),
    (
        "Discovery — the data draws the flowchart",
        "Sort each order's events by time and you get its <b>journey</b>: the exact route that "
        "order took through the shop. Count how often each step follows another across thousands "
        "of journeys, and a flowchart emerges — <b>nobody drew it; it was mined from the data</b>. "
        "That is process discovery.",
        """<div class="mock">
      <div class="flow">
        <span class="node">Login</span>
        <span class="lbl">12,480</span><span class="arrow">→</span>
        <span class="node">Browse Catalog</span>
        <span class="lbl">9,062</span><span class="arrow">→</span>
        <span class="node">Add to Basket</span>
        <span class="lbl">7,911</span><span class="arrow">→</span>
        <span class="node">Checkout</span>
        <span class="lbl">7,388</span><span class="arrow">→</span>
        <span class="node good">Order Confirmed</span>
      </div>
      <p class="cap">Each arrow carries a number: how many journeys took it. The picture shows the
        process <b>as it really ran</b> — not as a workshop whiteboard imagined it.</p>
    </div>""",
        [
            "The map reflects <b>reality</b>, including routes nobody designed on purpose.",
            "Rare paths appear thin, common paths thick — the main flow is visible at a glance.",
            "Re-mine tomorrow and the map updates itself: it is always as current as the data.",
        ],
        None,
    ),
    (
        "Reality has more paths than the ideal process",
        "On the whiteboard, every customer logs in, picks a book, pays and receives it. The mined "
        "map tells a richer story: customers loop between browsing and book details, payments "
        "fail and are retried, orders come back as returns. These <b>deviations are not noise — "
        "they are usually where the money leaks</b>.",
        """<div class="mock">
      <div class="flow">
        <span class="node">Select Payment Method</span><span class="arrow">→</span>
        <span class="node">Payment Processing</span>
        <span class="lbl">18&nbsp;%</span><span class="arrow">→</span>
        <span class="node bad">Payment Failed</span>
        <span class="arrow">→</span>
        <span class="node">Payment Retry</span>
        <span class="arrow">↩</span>
      </div>
      <p class="cap">A loop the designed process never mentioned: failed payments circling back
        through retry. In the bookstore data, bank-transfer payments fail far more often than
        credit cards — the map makes that visible immediately.</p>
    </div>""",
        None,
        '<span class="k">The happy path.</span> The intended ideal sequence is often called the '
        "<b>happy path</b>. Comparing it with the mined reality shows exactly how many journeys "
        "follow the plan — and where the rest branch off.",
    ),
    (
        "Numbers on the map: frequencies and times",
        "Every arrow can be read with different questions in mind: <b>how many</b> journeys took "
        "it, what <b>share</b> of all journeys that is, and <b>how long</b> the step-to-step "
        "transition took on average, at minimum, at maximum. Slow arrows are bottlenecks; thick "
        "arrows into failure steps are systematic problems.",
        """<div class="mock">
      <div class="pills">
        <span class="pill"># Count</span><span class="pill on">% Journey&nbsp;%</span>
        <span class="pill">⏱ Avg&nbsp;Time</span><span class="pill">⌄ Min</span>
        <span class="pill">⌃ Max</span><span class="pill">〰 Std&nbsp;Dev</span>
      </div>
      <div class="flow" style="margin-top:10px">
        <span class="node">Warehouse Packing</span>
        <span class="lbl">avg 2.1&nbsp;days</span><span class="arrow">→</span>
        <span class="node">Shipped</span>
        <span class="lbl">avg 1.4&nbsp;days</span><span class="arrow">→</span>
        <span class="node good">Delivered</span>
      </div>
      <p class="cap">The same map, read through a time lens: 2.1 days from packing to shipping is
        where this bookstore's delivery promise is lost — not at the carrier.</p>
    </div>""",
        [
            "<b>Frequency metrics</b> answer “where do journeys actually go?”",
            "<b>Time metrics</b> answer “where do they wait?”",
            "<b>Spread</b> (min/max/std&nbsp;dev) answers “is it reliably slow, or unpredictably slow?”",
        ],
        None,
    ),
    (
        "Conformance — compare reality with the plan",
        "Once the intended process is written down as a reference sequence, every mined journey "
        "can be <b>scored against it</b>: does it follow the plan, skip steps, add extra ones? "
        "The share of conforming journeys becomes a single, trackable number — and the "
        "non-conforming ones can be isolated and inspected.",
        """<div class="mock">
      <div class="flow">
        <span class="node">Checkout</span><span class="arrow">→</span>
        <span class="node">Enter Shipping Address</span><span class="arrow">→</span>
        <span class="node">Select Payment Method</span><span class="arrow">→</span>
        <span class="node good">Payment Confirmed</span>
      </div>
      <div class="score-row">
        <span class="score good-s">✅ 71&nbsp;% conform</span>
        <span class="score warn-s">⚠️ 24&nbsp;% retry loops</span>
        <span class="score bad-s">❌ 5&nbsp;% abandon at payment</span>
      </div>
      <p class="cap">Conformance turns “the process feels messy” into measurable shares that can be
        tracked over time.</p>
    </div>""",
        None,
        None,
    ),
    (
        "From insight to improvement — and around again",
        "Process mining is a loop, not a report. In the bookstore: the mined map exposed the "
        "bank-transfer failure loop and the packing delay. After fixing both — a better payment "
        "provider, an extra packing shift — the <b>next mining run proves whether it worked</b>, "
        "on the same data the systems record anyway.",
        """<div class="mock">
      <div class="flow" style="justify-content:center">
        <span class="node">Discover</span><span class="arrow">→</span>
        <span class="node">Analyse</span><span class="arrow">→</span>
        <span class="node">Improve</span><span class="arrow">→</span>
        <span class="node">Monitor</span><span class="arrow">↩</span>
      </div>
      <p class="cap">Because the evidence is the event log itself, every improvement claim can be
        verified with the next run.</p>
    </div>""",
        [
            "<b>Filter</b> to a segment (only bank-transfer orders, only Premium customers) and the map redraws for exactly those journeys.",
            "<b>Drill into</b> a suspicious region of the process without losing the overall picture.",
            "<b>Track</b> conformance and cycle times release by release.",
        ],
        None,
    ),
]

BEYOND = [
    "<b>Three classic disciplines.</b> <i>Discovery</i> (mine the map from the log), "
    "<i>conformance checking</i> (compare reality with the intended process) and "
    "<i>enhancement</i> (extend the map with times, costs and other data).",
    "<b>It works on any process that leaves timestamps.</b> Orders, support tickets, patient "
    "pathways, insurance claims, IT incidents — if a system logs case, activity and time, it "
    "can be mined.",
    "<b>The entry cost is low.</b> No new sensors, no interviews, no workshops to reconstruct "
    "the process from memory: the raw material already sits in the systems' databases.",
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
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);font-weight:600}
.node.good{border-color:rgba(30,158,90,.55);background:rgba(30,158,90,.10);color:var(--good)}
.node.bad{border-color:rgba(212,69,59,.55);background:rgba(212,69,59,.10);color:var(--bad)}
.arrow{color:var(--soft);font-weight:700}
.lbl{color:var(--soft);font-size:11px}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
.pill{border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12.5px;background:var(--card)}
.pill.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.cap{color:var(--soft);font-size:13px;margin:6px 2px 0}
.tbl{border-collapse:collapse;font-size:13px;width:100%;max-width:520px}
.tbl th{color:var(--soft);font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;
  text-align:left;padding:4px 12px 6px 0;border-bottom:2px solid var(--line)}
.tbl td{padding:5px 12px 5px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.score-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.score{border-radius:999px;padding:4px 12px;font-size:13px;font-weight:600;border:1px solid var(--line)}
.good-s{color:var(--good);background:rgba(30,158,90,.10);border-color:rgba(30,158,90,.4)}
.warn-s{color:#b26a00;background:rgba(217,131,36,.12);border-color:rgba(217,131,36,.4)}
.bad-s{color:var(--bad);background:rgba(212,69,59,.10);border-color:rgba(212,69,59,.4)}
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
<title>What is Process Mining?</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Process Mining · Introduction</span>
  <h1>What is Process Mining?</h1>
  <p>Your systems already know how your processes really run — they log every step of every
     order, ticket and claim. Process mining turns those logs into a living flowchart of
     reality: discovered from data, not drawn from memory.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    <b>Process mining</b> reconstructs and analyses business processes from the digital traces
    ("event logs") that IT systems record as a side effect of normal work. This introduction
    follows one running example — an <b>online bookstore</b>, from login to delivery (and the
    occasional return) — to show the principles. They apply unchanged to any process that
    leaves timestamps behind.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">The core promise of process mining: decisions about processes stop being
      debates about opinions, because the process itself — as recorded — is on the table.</p>
  </div>

  <footer>What is Process Mining? — a general introduction, illustrated with an online bookstore</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
