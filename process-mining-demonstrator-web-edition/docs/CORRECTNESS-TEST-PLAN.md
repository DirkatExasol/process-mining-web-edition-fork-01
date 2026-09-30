# Process-Mining Correctness Test Plan

**Status:** design (no implementation yet) · **Date:** 2026-09-25 · **Dataset:** 10-step process

Verifies that the Process Mining Suite computes **every metric correctly**, with and without
filtering, by ingesting a hand-crafted 10-step event log with a **known ground truth** into a
disposable Sandbox and comparing the Suite's numbers against **independently derived literal
expected values**.

## Agreed decisions
1. **Oracle = literals** — expected values hand-computed here, hard-coded in tests; formula-
   dependent ones pinned once against the documented algorithm (§8).
2. **CI gates on a disposable Exasol** — throwaway `exasol/docker-db` per pipeline (§9).
3. **All metrics** — incl. stochastic (sampling/simulation) as invariants (§6).
4. **Both surfaces** — REST **and** MCP must return identical numbers (§7).

---

## 1. The Sandbox dataset (ground truth) — a 10-step order-to-cash process

### 1.1 Steps (`STEPS`) — S10 is end-of-process
| Code | Step | SCORE | END |
|---|---|---|---|
| S01 | Receive Order | 1 | |
| S02 | Validate | 2 | |
| S03 | Check Credit | 3 | |
| S04 | Approve | 4 | |
| S05 | Pick | 5 | |
| S06 | Pack | 6 | |
| S07 | Ship | 7 | |
| S08 | Invoice | 8 | |
| S09 | Payment | 9 | |
| S10 | Close | 10 | ✓ |

### 1.2 Cases (6) — path, metadata, journey score (Σ step scores over events)
| Case | Path | Region (M1) | Segment (M2) | Channel (M3) | Start | Events | Score |
|---|---|---|---|---|---|---|---|
| P1 | S01→S02→S03→S04→S05→S06→S07→S08→S09→S10 (full) | EU | Gold | Web | 2026-01-05 09:00 | 10 | 55 |
| P2 | full | US | Silver | App | 2026-01-05 10:00 | 10 | 55 |
| P3 | full | EU | Silver | Web | 2026-02-10 09:00 | 10 | 55 |
| P4 | skip Credit: S01→S02→S04→…→S10 | US | Gold | App | 2026-02-10 10:00 | 9 | 52 |
| P5 | rework: S01→S02→S03→**S02**→S04→…→S10 | EU | Gold | App | 2026-03-01 09:00 | 11 | 57 |
| P6 | cancel: S01→S02→S10 | US | Silver | Web | 2026-03-01 10:00 | 3 | 13 |

Total events = **53**.

### 1.3 Transition-gap map (seconds) — the single source of all timing numbers
Absolute `EVENT_TIME` = case start + cumulative gaps along its path (the loader computes them).

| Transition | occ | gaps by case |
|---|---|---|
| S01→S02 | 6 | P1 60, P2 120, P3 180, P4 240, P5 300, P6 900 |
| S02→S03 | 4 | P1 180, P2 240, P3 360, P5 420 |
| S03→S04 | 3 | P1 300, P2 600, P3 900 |
| S03→S02 | 1 | P5 120 |
| S02→S04 | 2 | P4 480, P5 720 |
| S04→S05 | 5 | P1 120, P2 240, P3 360, P4 480, P5 600 |
| S05→S06 | 5 | 180 (all) |
| S06→S07 | 5 | 240 (all) |
| S07→S08 | 5 | 300 (all) |
| S08→S09 | 5 | 3600 (all) |
| S09→S10 | 5 | 120 (all) |
| S02→S10 | 1 | P6 60 |

Occurrence check: Σ occ = 47 = 53 events − 6 journeys. ✓
Journey durations (Σ gaps): **P1 5100, P2 5640, P3 6240, P4 5640, P5 6600, P6 960** s.

---

## 2. Baseline expected values (no filter)

**Journey count = 6** · total events = **53**

### 2.1 Node/step occurrences
S01 6 · S02 **7** (P5 twice) · S03 4 · S04 5 · S05 5 · S06 5 · S07 5 · S08 5 · S09 5 · S10 6

### 2.2 Variants
| Path | count | % |
|---|---|---|
| full (S01→…→S10) | 3 (P1,P2,P3) | 50.00 |
| skip Credit (…S02→S04…) | 1 (P4) | 16.67 |
| rework (…S02→S03→S02→S04…) | 1 (P5) | 16.67 |
| cancel (S01→S02→S10) | 1 (P6) | 16.67 |

### 2.3 Transition metrics (seconds; **stddev = sample, n−1** — calibrated §11)
The app uses SQL `STDDEV` = Exasol `STDDEV_SAMP` (sample, n−1). **Confirmed on Exasol Nano:** a
**single-occurrence** edge returns **0.0** (Exasol's `STDDEV` of one row is 0, *not* the
SQL-standard NULL).
| Transition | occ | avg | median | min | max | σ (sample) |
|---|---|---|---|---|---|---|
| S01→S02 | 6 | 300 | 210 | 60 | 900 | 305.94 |
| S02→S03 | 4 | 300 | 300 | 180 | 420 | 109.54 |
| S03→S04 | 3 | 600 | 600 | 300 | 900 | 300.00 |
| S03→S02 | 1 | 120 | 120 | 120 | 120 | 0.00 |
| S02→S04 | 2 | 600 | 600 | 480 | 720 | 169.71 |
| S04→S05 | 5 | 360 | 360 | 120 | 600 | 189.74 |
| S05→S06 | 5 | 180 | 180 | 180 | 180 | 0.00 |
| S06→S07 | 5 | 240 | 240 | 240 | 240 | 0.00 |
| S07→S08 | 5 | 300 | 300 | 300 | 300 | 0.00 |
| S08→S09 | 5 | 3600 | 3600 | 3600 | 3600 | 0.00 |
| S09→S10 | 5 | 120 | 120 | 120 | 120 | 0.00 |
| S02→S10 | 1 | 60 | 60 | 60 | 60 | 0.00 |

(S01→S02 median = mean of 3rd,4th of `[60,120,180,240,300,900]` = (180+240)/2 = 210; S02→S03
even-count median = (240+360)/2 = 300 — pins Exasol `MEDIAN()` = `PERCENTILE_CONT(0.5)`
interpolation.)

### 2.4 Journey-duration stats (seconds; stddev = sample, n−1)
| min | avg | median | max | σ (sample) |
|---|---|---|---|---|
| 960 | 5030 | 5640 | 6600 | 2061.21 |

(median = mean of 3rd,4th of `[960,5100,5640,5640,6240,6600]` = (5640+5640)/2.)

### 2.5 Goodness / happy path (calibrated §11)
- **Happy path** declared = full path S01→…→S10. Conformance is **journey-count-weighted edge
  coverage**, not exact-match: full 9/9, skip-credit 7/9, rework 8/9, cancel 1/9 →
  (3·1 + 7/9 + 8/9 + 1/9)/6 = **0.7963 (79.63%)**. (Confirmed by running
  `analytics.happy_path_conformance` on the fixture.)
- **Process goodness (raw)** = AVG over journeys of `total_score/√path_length − 0.01·duration_s`
  = **−34.5996** (baseline). Both REST and MCP apply the coverage penalty
  `raw·(filtered/total)^0.5`, so at baseline goodness == raw and under a filter it is the
  penalised value on both surfaces (see the §11 finding — now resolved).

---

## 3. Filter scenarios — surviving cases (determine every filtered metric)
| # | Filter | Surviving cases | Count | Variants (count) |
|---|---|---|---|---|
| F0 | none | P1–P6 | 6 | full 3, skip 1, rework 1, cancel 1 |
| F1 | fromDate=2026-02-01 | P3,P4,P5,P6 | 4 | full 1, skip 1, rework 1, cancel 1 |
| F2 | toDate=2026-01-31 | P1,P2 | 2 | full 2 |
| F3 | includedSteps=[S03] | P1,P2,P3,P5 | 4 | full 3, rework 1 |
| F4 | excludedSteps=[S03] | P4,P6 | 2 | skip 1, cancel 1 |
| F5 | includedSteps=[S07] (shipped) | P1,P2,P3,P4,P5 | 5 | full 3, skip 1, rework 1 |
| F6 | meta1="EU" | P1,P3,P5 | 3 | full 2, rework 1 |
| F7 | meta3="App" | P2,P4,P5 | 3 | full 1, skip 1, rework 1 |
| F8 | minSteps=10 | P1,P2,P3,P5 | 4 | full 3, rework 1 |
| F9 | maxSteps=9 | P4,P6 | 2 | skip 1, cancel 1 |
| F10 | minJourneyTime=5000 | P1,P2,P3,P4,P5 | 5 | full 3, skip 1, rework 1 |
| F11 | maxJourneyTime=5700 | P1,P2,P4,P6 | 4 | full 2, skip 1, cancel 1 |
| F12 | minScore=55 | P1,P2,P3,P5 | 4 | full 3, rework 1 |
| F13 | maxScore=52 | P4,P6 | 2 | skip 1, cancel 1 |
| F14 | fromDate=2026-02-01 AND meta1="EU" | P3,P5 | 2 | full 1, rework 1 |

Transition/duration tables for any filter recompute deterministically from the surviving set +
the §1.3 gap map. **Worked example — F3 (includedSteps=[S03], P1,P2,P3,P5)** journey-duration
stats over {5100,5640,6240,6600}: min 5100, avg 5895, median 5940, max 6600, σ 661.59 (sample); the
`skip-credit` edge `S02→S04` keeps only P5's 720 (occ 1), and `S02→S10` disappears.
**Active-in-window note:** F1's date window still counts P5's early events in full (whole
journey survives), and edge `S02→S10` (P6, March) is retained while Jan-only edges vanish.

---

## 4. Meta-value counts (`get_attribute_values`)
M1: EU 3 (P1,P3,P5) · US 3 (P2,P4,P6) — M2: Gold 3 (P1,P4,P5) · Silver 3 (P2,P3,P6) —
M3: Web 3 (P1,P3,P6) · App 3 (P2,P4,P5).

---

## 5. Deeper-analysis metrics (exact) — REST **and** MCP power tools
### 5.1 Bottlenecks — total wait = occ × avg (s)
S08→S09 **18000** (dominant) · S01→S02 1800 · S03→S04 1800 · S04→S05 1800 · S07→S08 1500 ·
S02→S03 1200 · S02→S04 1200 · S06→S07 1200 · S05→S06 900 · S09→S10 600 · S03→S02 120 ·
S02→S10 60. Σ = 30180 = Σ journey durations ✓. Rework: **S02 repeated in P5** (1 journey, 1
extra visit). Self-loops: none.

### 5.2 Trend by month (by journey start)
Jan {P1 5100, P2 5640}: n 2, avg 5370, median 5370 · Feb {P3 6240, P4 5640}: n 2, avg 5940,
median 5940 · Mar {P5 6600, P6 960}: n 2, avg 3780, median 3780.

### 5.3 Outcome drivers — outcome = reach **S07 (Ship)** · base 5/6 = 0.833
| Factor | n | reach | rate | Δ pts | lift |
|---|---|---|---|---|---|
| M1=EU | 3 | 3 | 1.000 | +16.7 | 1.200 |
| M1=US | 3 | 2 (P2,P4) | 0.667 | −16.7 | 0.800 |

### 5.4 Conformance rules (`check_conformance`), checked = 6
| Rule | violations | cases |
|---|---|---|
| forbidden {S03} | 4 | P1,P2,P3,P5 |
| requires {S04} | 1 | P6 |
| precedes {before S03, after S04} | 1 | P4 |
| max_duration {6000 s} | 2 | P3,P5 |
| max_gap {S08→S09, 3000 s} | 5 | P1,P2,P3,P4,P5 |

### 5.5 Segment compare (A=EU, B=US)
EU {P1,P3,P5}: count 3, avg 5980, median 6240 · US {P2,P4,P6}: count 3, avg 4080, median 5640.
Both end 100 % at S10.

### 5.6 Single-case lookups
`get_journey("P5")` → 11 events S01,S02,S03,S02,S04,S05,S06,S07,S08,S09,S10; duration 6600 s;
Region EU/Segment Gold/Channel App. `find_journey("P5")` → one match, duration 6600 s.

---

## 6. Stochastic metrics — invariants
- **Sampling** (random/temporal/pathDiverse, in-DB **and** app-side): count 3 → exactly 3
  distinct journeys, each with **all** its events copied, tagged `SAMPLE_1`, ⊆ ORIGINAL,
  ORIGINAL untouched; count ≥ 6 → all 6; in-DB ≡ app-side on these invariants; temporal/
  pathDiverse cover each bucket without over-drawing.
- **Simulation** (seed the RNG): total = requested; every walk starts at **S01**, ends at
  **S10** (or hits max-steps); variants ⊆ reachable; cycle times > 0; min ≤ median ≤ max.
  **Exact where σ=0:** every constant-gap edge (S05→S06 … S09→S10, S03→S02, S02→S10) is
  deterministic, so a resource-lever on those edges is asserted exactly (e.g. a 0.5 factor on
  S08 halves the S08→S09 mean to 1800 s).

## 7. Cross-surface & cross-mode equivalence (must agree)
REST ≡ MCP for `get_transition_metrics` / `get_statistics` / `get_variants` / `get_metadata`
across §2–§3; **materialized ≡ live** transitions (`use_materialized_transitions` on/off);
**in-DB ≡ app-side** sampling invariants.

## 8. Formula pinning (calibration) — **RESOLVED, see §11**
All formula-dependent values are now pinned (σ = sample, MEDIAN interpolated, single-row σ = 0,
goodness formula, happy-path = edge-coverage). Calibration also surfaced two real findings (my
happy-path hand-math was wrong; REST≠MCP goodness under filters). Details and the corrected
literals are in **§11 Calibration results**.

---

## 9. Resolved decisions (the four open items)

### D1 — Fixture ingest path: **the real event-receiver `/ingest` sink**
Load the §1.2 log by POSTing it to a Sandbox **AI-agent event-receiver sink** with a test
bearer token, so the test exercises the **production path**: HTTP ingest → EVENT_ID **MD5
hashing** → `JOURNEYS`/`METAS` writes → size/validation guards. A thin helper posts all events
in one batch (absolute times computed from start + §1.3 gaps). *Rejected:* a direct-SQL loader
— it would bypass the hashing/ingest logic we specifically want covered. (A direct loader may
still be offered as a fast local option for the pure-value unit checks, but CI uses the sink.)

### D2 — Sandbox connection/schema: **a fresh `PM_SANDBOX` schema per run, one project**
On the disposable CI Exasol, `provision_process_mining_schema("PM_SANDBOX")` creates the schema
+ tables fresh each run; register it as an admin **connection "Sandbox"** assigned to a
dedicated test user; the log lives under **project id 1**. Lifecycle: provision → ingest →
assert → drop (session-scoped fixture; truncate between test modules if reused). Isolated from
any real data by construction.

### D3 — MCP auth in CI: **a local stub OIDC issuer (real token path)**
Run a tiny in-process OIDC stub (FastAPI) that serves `/.well-known/openid-configuration` and a
`/jwks` built from a **test RSA keypair**, and mints RS256 tokens for the test user. Point the
MCP server's issuer/JWKS settings at the stub; mint a token and call `/mcp` over HTTP. This
exercises the **real verification path** (JWKS fetch, RS256, issuer/audience/group checks, user
mapping) with no Authentik/Keycloak dependency. *Rejected:* calling handlers directly bypasses
auth — kept only as a fast-path for value-only unit assertions, never for the auth tests.

### D4 — Exasol in CI: **Exasol Nano (multi-arch: ARM64 + x86) as a pipeline service**
Use **Exasol Nano** — the lightweight free single-node build, which ships an **ARM64** image
(so it runs on Apple-Silicon dev machines *and* arm64 CI runners) as well as x86, giving one
image for **both architectures**. A dedicated `correctness` job runs it as a service (or
`docker run`), waits for readiness (poll until SQL is accepted), runs the whole suite
session-scoped against it, and discards the container with the job. Far lighter than the full
`exasol/docker-db` appliance (smaller image, faster boot, no hugepages/privileged appliance
setup). Pin the image by digest for reproducibility; nothing DB-side is cached. The job gates
the pipeline but runs in parallel with the fast unit jobs.

---

## 10. Test matrix
Each metric family × each filter F0–F14 (where applicable), asserted **REST == literal** and
**MCP == literal** (== each other): journey count · variants · transition metrics · node
occurrences · duration stats · goodness/happy-path · attribute values · bottlenecks · trend ·
outcome drivers · conformance · segment compare · get_journey/find_journey · sampling
invariants · simulation invariants · equivalence checks. Est. ~160–200 assertions.

---

## 11. Calibration results (spike, 2026-09-25)
Phase 0 (source review) + Phase 1 (live checks) + Phase 2 (pinning). Ran against the app's
real code and a live **Exasol Nano** (the `exanano` container, read-only inline-`VALUES`
queries only — no schema/table/data touched).

**Pinned / corrected literals:**
| Item | Result | Method |
|---|---|---|
| Transition & duration **σ** | **sample** (`STDDEV`=`STDDEV_SAMP`); S01→S02 305.94, journey 2061.21 | source + live Nano (305.94 vs POP 279.28) |
| Single-occurrence σ | **0.0** (Exasol quirk — not SQL-standard NULL) | live Nano `STDDEV((VALUES(120)))` = 0.0 |
| **MEDIAN** even-count | **interpolated** (S02→S03 300, duration 5640) | live Nano = `PERCENTILE_CONT(0.5)` |
| **Happy-path conformance** | **0.7963** (edge-coverage weighted; my hand-math of 0.8148 was wrong) | ran `analytics.happy_path_conformance` |
| **Process goodness (raw)** | **−34.5996** baseline (`total_score/√len − 0.01·dur`, averaged) | source formula + Python |

**Findings (not just calibration):**
- **REST vs MCP goodness under filters — RESOLVED.** Calibration found that REST applied the
  coverage penalty `raw·(filtered/total)^0.5` while MCP `get_statistics` returned the raw
  value, so they diverged under a filter. Fixed: `get_statistics` now applies the same penalty
  (total = the project's unfiltered journey count on the sample set), so REST == MCP everywhere.
  An integration test asserts equality at baseline *and* under a filter.

**Decisions validated by running them:**
- **D3 (MCP auth):** an in-process stub-OIDC RS256 keypair drives the real `_authenticate`
  end-to-end — valid token → mapped user; wrong-audience / missing-group / unknown-user /
  expired / tampered-signature all rejected with the correct 401/403. No Authentik/Keycloak
  needed for tests.
- **D4 (Exasol):** **Exasol Nano runs natively on ARM64** (`exasol/nano:latest`, one image for
  Apple-Silicon dev and arm64/x86 CI) — a live instance was queried successfully. This replaces
  the earlier (wrong) "not runnable on Apple Silicon" note.

**Still pending a full live run (needs the app wired to a fresh Nano schema, not just SQL):**
end-to-end **ingest (`/ingest`) → REST → MCP** on the seeded fixture, confirming the goodness
SQL execution equals −34.5996 and that REST==MCP holds everywhere except the goodness-under-
filter case above. This is the first slice of the harness build (D1/D2), not a calibration gap.
