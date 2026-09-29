# Process-Mining Correctness Test — Cycles & Loops

**Status:** implemented · **Date:** 2026-09-28 · **Dataset:** 30-step incident-resolution
process with loops · **Test:** [`backend/tests/integration/test_sandbox_cycles.py`](../backend/tests/integration/test_sandbox_cycles.py)

This is the **second** correctness test for the Process Mining Suite. The
[first one](CORRECTNESS-TEST-PLAN.md) verifies every metric on a mostly-linear 10-step
order-to-cash log. This one deliberately stresses the hardest thing a process-mining engine
has to get right: **repetition** — steps that recur because work loops back. A customer or
prospect can read this document, look at the fixture, and confirm for themselves that the
Suite counts loops, self-loops, rework and long cyclic journeys exactly.

The method is the same as before: build a **hand-designed event log with a known ground
truth**, ingest it into a disposable *Sandbox* schema on a throwaway Exasol, and compare the
Suite's output — over **both** the REST API and the **MCP** (AI-agent) surface — against
values derived **independently**. It never touches any real data: it creates and drops its
own schema.

---

## 1. Why a separate cycles test?

Real processes rarely run in a straight line. A fix fails review and goes back to
development; a deployment fails a smoke test and is redeployed; an incident is reopened and
re-triaged; a system is monitored repeatedly. Each of these makes a step appear **more than
once** in a single case, which is exactly where naive process mining goes wrong — double
counting, mis-attributing wait times, or hanging when it simulates a graph that can loop.

This fixture contains, on purpose:

| Loop kind | Example in the fixture | Where |
|---|---|---|
| **Self-loop** (a step immediately repeating) | `Monitor → Monitor` polled 13×; `Await Customer → Await Customer` | J10, J08 |
| **2-cycle / rework loop** | review reject `Code Review → Develop Fix`; smoke reject `Smoke Test → Deploy Staging` | J03, J05, J10 |
| **Back-jump** (throw work back several steps) | failed test `Test → Develop Fix` | J04, J10 |
| **Escalation cycle** | `Investigate → Escalate → Investigate` | J06 |
| **Big reopen cycle** | `Verify → Reopen → Triage → …` re-enters the whole spine | J07 |

---

## 2. The process — 30 distinct steps (an incident-resolution workflow)

`SCORE` is the step's index (1…30); `C30 Close` is the single end-of-process step. Each step
has a **fixed processing time** (seconds) — a transition's duration is simply the time of the
step it leads *into*. That one rule makes every timing number below reproducible by hand.

| Code | Step | Proc. time (s) | Code | Step | Proc. time (s) |
|---|---|--:|---|---|--:|
| C01 | Open | — (start) | C16 | Verify Resolution | 600 |
| C02 | Triage | 300 | C17 | Escalate | 1200 |
| C03 | Assign | 600 | C18 | Await Customer | 3600 |
| C04 | Investigate | 900 | C19 | Reopen | 600 |
| C05 | Reproduce | 600 | C20 | Put On Hold | 7200 |
| C06 | Develop Fix | 1800 | C21 | Rollback | 900 |
| C07 | Code Review | 1200 | C22 | Hotfix | 1800 |
| C08 | Build | 600 | C23 | Root Cause Analysis | 3600 |
| C09 | Test | 1800 | C24 | Document | 1200 |
| C10 | Deploy Staging | 900 | C25 | Notify Stakeholders | 600 |
| C11 | Smoke Test | 600 | C26 | Update Knowledge Base | 900 |
| C12 | UAT | 3600 | C27 | Peer Sign-off | 600 |
| C13 | Approve Release | 1800 | C28 | Retrospective | 1800 |
| C14 | Deploy Production | 900 | C29 | Archive | 300 |
| C15 | Monitor | 300 | C30 | Close | 120 |

All 30 steps are visited by at least one journey, so every step is exercised.

---

## 3. The event log — 13 cases, 295 events, longest visits 50 steps

Each journey runs on its own calendar day starting 2026-01-05 08:00. Loops are shown in
**bold**. "Duration" is last-event − first-event = the sum of the processing times along the
path.

| Case | Path (loops in bold) | Steps | Duration | Priority / Team / Source |
|---|---|--:|--:|---|
| J01 | full happy path + full closure (…C16→C24→C25→C26→C27→C28→C29→C30) | 23 | 6.12 h | P2 / Core / Portal |
| J02 | happy path, short closure | 18 | 4.03 h | P3 / Core / Email |
| J03 | one review reject: …C07→**C06→C07**→C08… | 22 | 6.03 h | P2 / Payments / Portal |
| J04 | one test failure: …C09→**C06→C07→C08→C09**→C10… | 22 | 5.53 h | P1 / Payments / Phone |
| J05 | one smoke failure: …C11→**C10→C11**→C12… | 21 | 5.45 h | P2 / Core / Email |
| J06 | escalation cycle: …C04→**C17→C04**→C05… | 21 | 4.78 h | P1 / Platform / Phone |
| J07 | reopen cycle: …C16→**C19→C02→C03→C04→…→C16**→C24… | 32 | 7.62 h | P2 / Platform / Portal |
| J08 | await self-loop: …C04→**C18→C18→C18**→C05… | 22 | 7.20 h | P3 / Core / Email |
| J09 | production rollback: …C14→C15→**C21→C22→C14→C15**→C16→C23… | 23 | 6.12 h | P1 / Platform / Phone |
| **J10** | **chronic flapping**: 2 review rejects + 2 test failures + 2 smoke failures + **Monitor ×13** | **50** | **12.12 h** | P1 / Payments / Portal |
| J11 | put on hold, re-triage: C01→C02→**C20→C02**→C03… | 20 | 6.12 h | P3 / Core / Portal |
| J12 | cancelled early: C01→C02→C30 | 3 | 0.12 h | P3 / Core / Email |
| J13 | identical path to J02 (a second short-closure incident) | 18 | 4.03 h | P2 / Payments / Email |

**J10 expanded** (the 50-step case): `C01 C02 C03 C04 C05 C06` · `C07` · **`C06 C07`** ·
**`C06 C07`** · `C08 C09` · **`C06 C07 C08 C09`** · **`C06 C07 C08 C09`** · `C10 C11` ·
**`C10 C11`** · **`C10 C11`** · `C12 C13 C14` · **`C15`×13** · `C16 C24 C25 C26 C27 C29 C30`.

---

## 4. Ground truth (the numbers the Suite must reproduce)

### 4.1 Shape
- **13 journeys**, **295 events**, **30 distinct steps**; longest journey **50 events** (J10),
  shortest **3** (J12).

### 4.2 Step (node) occurrences — loop-inflated counts
| C01 13 | C02 15 | C03 13 | C04 14 | C05 5 | C06 **19** | C07 **19** | C08 16 | C09 16 | C10 16 |
|---|---|---|---|---|---|---|---|---|---|
| **C11 16** | C12 4 | C13 13 | C14 14 | **C15 26** | C16 13 | C17 1 | C18 3 | C19 1 | C20 1 |
| C21 1 | C22 1 | C23 1 | C24 12 | C25 12 | C26 2 | C27 2 | C28 1 | C29 12 | C30 13 |

`C15 Monitor` = 26 (inflated by J10's 13-poll self-loop); `C06`/`C07` = 19 each (every fix is
followed by a review, and both recur through the loops).

### 4.3 Self-loops (a step directly following itself)
| Self-loop | Occurrences |
|---|--:|
| C15 → C15 (Monitor) | **12** (all in J10's 13-event poll run) |
| C18 → C18 (Await Customer) | **2** (J08's 3-event wait) |

### 4.4 Rework (a step visited more than once *within* a case)
| Step | Journeys with rework | Extra visits |
|---|--:|--:|
| C15 Monitor | 3 | **14** |
| C06 Develop Fix | 4 | 7 |
| C07 Code Review | 4 | 7 |
| C08 Build | 3 | 4 |
| C09 Test | 3 | 4 |
| C10 Deploy Staging | 3 | 4 |
| C11 Smoke Test | 3 | 4 |
| C04 Investigate | 2 | 2 |
| C02 Triage | 2 | 2 |
| C14 Deploy Production | 2 | 2 |
| C18 Await Customer | 1 | 2 |
| C03 Assign / C13 Approve / C16 Verify | 1 each | 1 each |

### 4.5 Loop / back edges (the cycle "return" transitions)
| Edge | Meaning | Occurrences |
|---|---|--:|
| C07 → C06 | review reject | 3 |
| C09 → C06 | test-failure back-jump | 3 |
| C11 → C10 | smoke-test reject | 3 |
| C17 → C04 | escalation returns to investigate | 1 |
| C16 → C19 → C02 | reopen cycle | 1 |

### 4.6 Variants and durations
- **12 distinct variants** across the 13 journeys — J02 and J13 share the same path (that
  variant has count 2; the other 11 are unique).
- Journey durations (seconds): **min 420, median 21 720, mean ≈ 20 843.08, max 43 620,
  σ (sample) ≈ 9 597.24**. Total processing time across all journeys = 270 960 s.

---

## 5. How the expected values are derived (the oracle)

The test does **not** trust hand-typed numbers for the whole matrix (295 events across 13
looping journeys is too much to hand-total reliably). Instead it recomputes every expected
value with an **independent Python oracle** — plain counting plus the standard-library
`statistics` module (`mean`, `median`, `stdev` = sample/n−1) — from the fixture definition.
This is a genuinely different code path from the Suite's SQL, so agreement between the two is
real evidence, not a tautology. The **headline** cycle facts in §4 are *additionally* pinned
as explicit literals in the test, so a reader can trace them directly to the journey table.

> Statistical conventions match the engine and are validated by the first test's calibration:
> `STDDEV` = sample (n−1), single-occurrence edge σ = 0.0 (an Exasol convention, not NULL),
> `MEDIAN` = interpolated `PERCENTILE_CONT(0.5)`.

---

## 6. What is asserted

Against a live Exasol, over the fixture above:

- **Structure** — journey count, total events, 30-step catalog, longest/shortest journey.
- **Node occurrences** — every step's count equals the oracle (loop-inflated counts included).
- **Transition metrics** — for **every** edge: occurrences, average, median, min, max and
  σ equal the oracle; the loop/back edges and the forward loop edge `C06→C07` (19×) are pinned.
- **Self-loops** — `C15→C15` (12) and `C18→C18` (2), value and interval.
- **Rework** — journeys-affected and extra-visits per step equal the oracle; Monitor's 14
  extra visits and the develop/review pair (7 each) are pinned.
- **Durations** — mean/median/min/max/σ over the 13 journeys.
- **Variants** — 12 distinct paths, with the shared J02/J13 variant carrying count 2.
- **MCP equivalence** — the MCP `get_transition_metrics`, `get_bottlenecks` (rework +
  self-loops), `get_metadata`, `get_process_map` and `get_journey` tools return the same
  numbers as REST; `get_journey("J10")` reconstructs the exact 50-step loop order; power tools
  reject a non-power user.
- **Simulation on a cyclic graph** — a seeded Monte-Carlo run over this loop-heavy graph
  **terminates** (never diverges): every walk starts at `C01` and either reaches `C30` or is
  cut at the max-steps cap, visits only observed steps, and yields well-ordered cycle-time
  statistics (min ≤ mean ≤ max).

---

## 7. Running it

The test is opt-in (marker `integration`) and **auto-skips** when no Exasol is reachable.

```bash
# needs a reachable Exasol (defaults to Exasol Nano at 127.0.0.1:8563, sys/exasol;
# override with PMW_SANDBOX_HOST / _PORT / _USER / _PASSWORD)
cd backend && ../.venv/bin/python -m pytest tests/integration/test_sandbox_cycles.py -m integration
```

In CI it runs in the dedicated `correctness` job alongside the 10-step test, against a
disposable **Exasol Nano** service (ARM64 + x86). Both fixtures use their own schema
(`PM_SBX_TEST` and `PM_SBX_CYCLES`) and drop it on teardown, so they are fully isolated.
