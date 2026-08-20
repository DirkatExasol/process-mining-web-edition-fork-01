#!/usr/bin/env python3
"""Generate the self-contained HTML deep-dive: how the Simulation view works — the
Markov-chain model fitted from the observed process, and the Monte-Carlo generation
on top of it — with worked examples.

Every number in the worked examples was verified by running the app's actual
simulation engine (backend/app/services/simulation.py — MarkovModel + simulate)
on a mini bookstore graph; the quoted run used a fixed random seed.

Like the other guides, all illustrations are CSS-drawn mocks — no screenshots — so
the single .html file is fully self-contained.
Run:  python3 docs/build-simulation-guide.py
"""
import html
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "Simulation-Explained.html"

# Each chapter: (title, body_html, mock_html | None, bullets: list[str] | None, tip_html | None).
# body/mock/bullets/tip are passed through as HTML (only the title is escaped).
STEPS = [
    (
        "What the Simulation view does",
        "The Simulation view generates <b>synthetic journeys</b> that behave like the real ones: "
        "it learns a statistical model from the process you currently have on screen (the "
        "filtered flowchart) and then plays that model forward — thousands of imaginary "
        "customers walking through your process step by step. Nothing is written to the "
        "database; it is a laboratory copy of your process.",
        """<div class="mock">
      <div class="pills">
        <span class="pill on">Journeys: 200</span>
        <span class="pill">Start date</span>
        <span class="pill">Avg inter-arrival: 2 h</span>
        <span class="pill">Max steps: 60</span>
        <span class="pill">Exclude steps…</span>
        <span class="pill">Require steps…</span>
      </div>
      <p class="cap">The simulation controls. Exclude a step to test a world without it;
        require a step to generate only journeys that pass through it.</p>
    </div>""",
        None,
        '<span class="k">Why simulate?</span> To answer <i>what-if</i> questions the historical '
        "data cannot: What happens to cycle times if the payment-retry loop disappears? What "
        "does a month of traffic look like at a different arrival rate?",
    ),
    (
        "The underlying technique: a Markov chain",
        "A <b>Markov chain</b> is a model of a system that moves between <b>states</b> (here: "
        "process steps) where the next move depends <b>only on the current state</b> — not on "
        "how the journey got there. This is the famous <i>memoryless</i> property. Each step "
        "carries a set of outgoing probabilities that sum to 100&nbsp;%, like a weighted die "
        "rolled every time a journey stands on that step.",
        """<div class="mock">
      <div class="prob">
        <span class="node">Browse Catalog</span>
        <div class="prob-arms">
          <div class="arm"><span class="p">65 %</span><span class="arrow">→</span><span class="node">View Book Details</span></div>
          <div class="arm"><span class="p">35 %</span><span class="arrow">→</span><span class="node">Add to Basket</span></div>
        </div>
      </div>
      <p class="cap">Standing on <b>Browse Catalog</b>, the simulated customer rolls the die:
        65 % of rolls continue to book details, 35 % go straight to the basket. The roll knows
        nothing about the journey's past — that is the Markov assumption.</p>
    </div>""",
        None,
        '<span class="k">Why “chain”?</span> Because journeys are chains of such rolls: '
        "state → roll → next state → roll → … until an end state is reached. The whole process "
        "becomes a graph of states with a probability on every arrow.",
    ),
    (
        "Fitting the model: probabilities from your own data",
        "The probabilities are not invented — they are <b>estimated from the observed "
        "flowchart</b>. For every step, each outgoing edge's probability is its share of the "
        "step's total outgoing occurrences:",
        """<div class="mock">
      <div class="formula">P(A → B) &nbsp;=&nbsp; occurrences(A → B) &nbsp;/&nbsp; Σ occurrences(A → *)</div>
      <table class="tbl" style="margin-top:12px">
        <tr><th>From Browse Catalog</th><th>occurrences</th><th>probability</th></tr>
        <tr><td>→ View Book Details</td><td>6,500</td><td>6,500 / 10,000 = <b>0.65</b></td></tr>
        <tr><td>→ Add to Basket</td><td>3,500</td><td>3,500 / 10,000 = <b>0.35</b></td></tr>
        <tr><td>From Payment Processing</td><td></td><td></td></tr>
        <tr><td>→ Payment Confirmed</td><td>6,150</td><td><b>0.82</b></td></tr>
        <tr><td>→ Payment Failed</td><td>1,350</td><td><b>0.18</b></td></tr>
      </table>
      <p class="cap">Verified against the app's <code>MarkovModel</code>: it stores exactly these
        values (as cumulative thresholds 0.65 → 1.00 and 0.82 → 1.00 for fast sampling).</p>
    </div>""",
        [
            "<b>Entry points</b> are detected from the original graph: a step whose incoming "
            "count is less than <b>20&nbsp;%</b> of its outgoing count is a start (Login: 0 in / "
            "10,000 out → start; Browse Catalog: 12,500 in / 10,000 out = 1.25 → not a start). "
            "If nothing qualifies, the step with the most outgoing traffic is used.",
            "<b>Excluded steps</b> are removed, then a reachability sweep from the start steps "
            "prunes anything that became disconnected — no journey can wander into a dead region.",
            "<b>Start weights</b> are re-derived after pruning, so an excluded step's share is "
            "redistributed instead of leaving a gap.",
        ],
        None,
    ),
    (
        "Time is a distribution, not a number",
        "Real transition times are skewed: most payments clear quickly, a few take very long. "
        "The engine therefore draws each edge's duration from a <b>lognormal distribution</b> "
        "fitted to the edge's observed average and standard deviation (method of moments):",
        """<div class="mock">
      <div class="formula">μ = ln( avg² / √(avg² + var) )<br>σ = √( ln( 1 + var / avg² ) )</div>
      <pre class="calc">Edge Checkout → Payment Processing:  avg = 2 h (7,200 s),  sd = 1 h

μ = ln(7200² / √(7200² + 3600²)) = 8.7703
σ = √(ln(1 + 3600²/7200²))       = 0.4724

median journey  = e^μ           ≈ 6,440 s ≈ 1 h 47 m   (the typical case)
mean            = e^(μ + σ²/2)  = 7,200 s = 2 h        (matches the data)</pre>
      <p class="cap">The median is <i>below</i> the mean — the fitted distribution reproduces the
        real-world skew: many quick transitions, a long tail of slow ones. Verified against the
        app's fitted parameters.</p>
    </div>""",
        [
            "Each sample is drawn via the <b>Box–Muller transform</b> (two uniform random numbers "
            "→ one normally distributed value → exponentiated to lognormal).",
            "An edge with an average but <b>no standard deviation</b> gets exactly its average "
            "every time (σ = 0).",
            "An edge with <b>no timing data</b> at all falls back to a default of about 1 hour "
            "with moderate spread.",
            "Every sampled duration is floored at <b>60 seconds</b> — no zero-time hops.",
        ],
        None,
    ),
    (
        "Arrivals: a Poisson process",
        "Journeys do not start on a fixed clock grid. New arrivals are generated as a "
        "<b>Poisson process</b>: the gap to the next arrival is drawn from an exponential "
        "distribution around your configured average inter-arrival time.",
        """<div class="mock">
      <div class="formula">gap &nbsp;=&nbsp; −&nbsp;avg_interarrival · ln(u) &nbsp;&nbsp;&nbsp; u ~ uniform(0, 1)</div>
      <pre class="calc">Avg inter-arrival = 2 h:
  u = 0.90 → gap = −2·ln(0.90) = 0.21 h  (a burst — arrivals close together)
  u = 0.50 → gap = −2·ln(0.50) = 1.39 h
  u = 0.10 → gap = −2·ln(0.10) = 4.61 h  (a quiet spell)</pre>
      <p class="cap">Short gaps are common, long gaps are rare but real — exactly how independent
        customers actually arrive. The average works out to your configured 2 h.</p>
    </div>""",
        None,
        None,
    ),
    (
        "Walking one journey — a worked random walk",
        "One synthetic journey is a chain of die rolls. With the bookstore model above, one "
        "walk might look like this (u is the roll; compare it to the cumulative thresholds):",
        """<div class="mock">
      <pre class="calc">start: Login                              (only start step, weight 1.0)
Login            →  Browse Catalog        (only edge)
Browse Catalog:   u = 0.71  &gt; 0.65     →  Add to Basket
Add to Basket    →  Checkout              (only edge)
Checkout         →  Payment Processing    (duration drawn: 1 h 52 m)
Payment Proc.:    u = 0.90  &gt; 0.82     →  Payment Failed
Payment Failed   →  Payment Retry         (only edge)
Payment Retry    →  Payment Processing    (the loop!)
Payment Proc.:    u = 0.42  ≤ 0.82      →  Payment Confirmed   ■ end of process

path:  Login → Browse → Basket → Checkout → Processing → Failed
       → Retry → Processing → Confirmed</pre>
      <p class="cap">The walk ends when it reaches a step flagged <b>end of process</b>, hits a
        dead end, or exceeds the <b>max steps per journey</b> cap (default 60 — the safety net
        that keeps loops from running forever).</p>
    </div>""",
        None,
        '<span class="k">Memorylessness in action.</span> On its second visit to Payment '
        "Processing the journey rolls the same 82/18 die as on the first — the model does not "
        "know it already failed once. Real customers might behave differently after a failure; "
        "that is a known limit of the Markov assumption (see “Good to know”).",
    ),
    (
        "Monte Carlo: from one walk to statistics",
        "One random walk proves nothing — the power comes from generating <b>many</b> journeys "
        "and reading the statistics. A run of 1,000 journeys through the bookstore model (fixed "
        "seed, real engine) produced:",
        """<div class="mock">
      <table class="tbl">
        <tr><th>Variant</th><th>share</th><th>avg cycle</th></tr>
        <tr><td>Login → Browse → Basket → Checkout → Processing → Confirmed</td><td>31.5 %</td><td>6.6 h</td></tr>
        <tr><td>… with View Book Details</td><td>29.8 %</td><td>7.8 h</td></tr>
        <tr><td>… with a browse-details loop</td><td>9.2 %</td><td>10.0 h</td></tr>
        <tr><td>… with one payment retry</td><td>5.7 %</td><td>11.4 h</td></tr>
      </table>
      <pre class="calc">Total: 1,000 journeys
cycle time:  avg 8.55 h   min 3.06 h   max 19.94 h   std dev 2.76 h</pre>
      <p class="cap">The simulated event log is then aggregated back into a directly-follows
        flowchart — so the simulated process can be inspected with exactly the same map,
        metrics and variant table as the real one.</p>
    </div>""",
        None,
        '<span class="k">Monte-Carlo noise.</span> Every run differs slightly — that is by '
        "design. More journeys → steadier numbers. If a rare path matters, raise the journey "
        "count until its share stabilises.",
    ),
    (
        "What-if experiments",
        "The controls turn the model into a laboratory. <b>Excluding</b> the payment-retry loop "
        "(remove Payment Failed and Payment Retry) re-runs the same 1,000 journeys in a world "
        "where every payment clears first time:",
        """<div class="mock">
      <pre class="calc">                     baseline      without retry loop
avg cycle time        8.55 h            7.95 h        (−7 %)
top variant           31.5 %            39.9 %  (main route, no detour)
retry variants        ~9 %              0 %</pre>
      <p class="cap">Both numbers come from real engine runs with the same seed. The comparison
        quantifies what fixing the payment provider would be worth — before touching anything
        in production.</p>
    </div>""",
        [
            "<b>Exclude steps</b> — simulate the process without them; probabilities and start "
            "weights are re-normalised so the remaining traffic redistributes realistically.",
            "<b>Require steps</b> — keep only journeys that visit them (the engine generates and "
            "discards until enough qualify, up to a 20× attempt budget).",
            "<b>Arrival rate & start date</b> — stretch or compress the same behaviour over a "
            "different calendar to preview load patterns.",
        ],
        None,
    ),
]

BEYOND = [
    "<b>The Markov assumption is a simplification.</b> The next step depends only on the "
    "current step — a journey that already failed payment twice rolls the same die as a "
    "first-timer. Processes with strong history effects will simulate slightly “too smooth”.",
    "<b>No queueing or resources.</b> Durations are drawn independently per edge; the model "
    "does not know that ten journeys hitting the warehouse at once would slow each other down.",
    "<b>Loops are capped, not solved.</b> A journey that keeps rolling into a loop is cut off "
    "at the max-steps limit (default 60) rather than walking forever.",
    "<b>Nothing is written.</b> Simulation reads the on-screen graph, generates in memory, and "
    "renders — your data is never touched.",
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
.node{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--card);
  font-weight:600;font-size:13px;display:inline-block}
.arrow{color:var(--soft);font-weight:700}
.cap{color:var(--soft);font-size:13px;margin:8px 2px 0}
.cap code, .calc code{background:var(--bg);border-radius:4px;padding:0 4px}
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
.prob{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.prob-arms{display:flex;flex-direction:column;gap:8px}
.arm{display:flex;align-items:center;gap:8px}
.p{font:700 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);
  background:rgba(58,109,240,.10);border:1px solid rgba(58,109,240,.35);border-radius:999px;
  padding:4px 9px}
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
<title>Simulation Explained</title>
<style>{CSS}</style>
</head>
<body>
<header class="hero"><div class="hero-inner">
  <span class="chip">Work-Bench · Deep Dive</span>
  <h1>How Simulation works — Markov chains &amp; Monte Carlo</h1>
  <p>The Simulation view learns a statistical model of your process from the data on screen,
     then generates thousands of synthetic journeys through it. This guide explains the
     underlying technique — a fitted Markov chain — with worked examples, every number
     verified against the app's engine.</p>
</div></header>

<div class="wrap">

  <div class="lead">
    Three ingredients: a <b>Markov chain</b> fitted from the flowchart (which way do journeys
    go at each step?), <b>lognormal edge durations</b> fitted from the observed times (how long
    does each hop take?), and <b>Poisson arrivals</b> (when do new journeys begin?). A
    <b>Monte-Carlo</b> run then rolls the dice thousands of times and aggregates the outcomes
    into variants, cycle-time statistics and a simulated flowchart.
  </div>

  {''.join(steps_html)}

  <div class="beyond">
    <h2>Good to know — assumptions and limits</h2>
    <ul>
{beyond_items}
    </ul>
    <p class="note">Rule of thumb: simulation is at its best for <b>relative</b> comparisons —
      baseline vs what-if under identical assumptions — rather than absolute forecasts.</p>
  </div>

  <footer>Process Mining Demonstrator · Work-Bench — How Simulation works (Markov chains &amp; Monte Carlo)</footer>
</div>
</body></html>
"""


OUT.write_text(render(), encoding="utf-8")
kb = OUT.stat().st_size / 1024
print(f"WROTE {OUT}  ({kb:.0f} KB)")
