# Changelog

All notable changes to the **Process Mining Demonstrator — Web Edition** are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/); from this release the
project uses a **calendar-style version** `YYYY.MINOR.PATCH` with a landmark codename.

---

## [2027.1.0] — "Tongariro"

The headline additions: a **Dashboard**, **automatic refresh** on the A-Chart and the
Dashboard, and a standalone **live demo-event generator** — plus a new version format.

### Added

- **WorkBench Mobile** — phones (iPhone / Android handsets) now run a dedicated compact shell
  instead of the desktop split layout: a top bar with a **☰ hamburger** that opens the controls
  as a slide-over drawer (no fixed sidebar), a bottom-sheet **view switcher**, a collapsible KPI
  strip, and a full-screen view area that works in **portrait and landscape**. Supported views
  on a phone are **Dashboard, A-Chart, Individual Journey, Notes and AI Documentation**; any
  desktop-only view (A/B Comparison, B-Chart, Statistics, Conformance, Happy Path, Simulation)
  redirects to the Dashboard with a short note. The process map becomes touch-driven (one-finger
  pan, pinch-zoom; the corner controls stay visible). **iPads and tablets keep the full desktop
  web layout** — only phones get the mobile shell.
- **Note notifications** — a Dashboard notification rule can now watch a process's **notes &
  comments** (a new `note` check kind), not just metrics: fire on **new notes**, **all open
  notes**, **resolutions/acknowledgements** or **new comments**, at a chosen **minimum
  importance** and **scope** (shared by default, or all incl. personal), when at least _N_
  match within a recency window. The card carries a **yellow 🗒️ sticker** and shows the match
  count and the latest note (title, importance, target); **clicking it opens that note** (the
  app connects, opens the process and lands on its note). The filter row gains a **Type**
  (Event / Note) filter plus **Note scope** and **Note severity** refinements. An acknowledged
  note re-surfaces (and re-delivers) when a newer matching note appears. (Backend: a notes
  query over the Exasol `NOTES` table, a `note` evaluator carrying the triggering note as run
  `meta`, and the engine's evaluator contract gains that metadata slot.)
- **Directory (LDAP) user-list sync** — the admin **Users** tab no longer shows a directory
  user only after their first sign-in. An opt-in background job (admin **Directory** tab →
  *Automatically sync the user list*, default **every 5 minutes**, interval configurable) mirrors
  the directory into the local user roster: **new** accounts appear, **changed** email/display
  names are refreshed, and an account **removed** from the directory is **disabled and flagged**
  "removed from directory" — never deleted, so its role and DB-connection assignments survive if
  it returns (a reappearing account is re-enabled). A **Refresh from directory** button on the
  Users tab runs it on demand, with the last run's time and outcome shown, and each user's row now
  reads their **last sign-in** or **"Never signed in"**. Local accounts are never touched; a
  directory name that collides with a local account is skipped. (New LDAP enumeration search, a
  shared-per-process sync in the security store, and an admin scheduler + `POST /api/ldap/sync`.)
- **Dashboard notifications** — a second **Notifications** section on the Dashboard: define a
  **rule** whose **check type** is either a **transition between two steps** (a metric — average /
  median / min / max time, std-dev or count — on the step-to-step transition) or a **journey
  duration** (a time aggregate — average / median / min / max time, std-dev — of the whole case's
  end-to-end duration, no steps) crossing a threshold, and a background **engine**
  checks it on its own interval (1m / 5m / 15m / 1h / 2h / 5h / 1d). A **summary strip** heads the
  section and each rule is a **gauge card** — the measured value against its limit, plus last
  value / over-or-under-limit / triggered-at / interval — **sorted by urgency then time**, with a
  one-click enable/disable and an on-demand **↻ refresh** per rule. Rules are created in a
  **Create / Edit** wizard (with a **Test now** button that evaluates against current data without
  saving) and are **shared per connection** (everyone assigned sees them and may refresh; power
  users, developers and admins manage them). Opt-in per an admin **Enable Notifications** toggle.
  The MCP server gains **`list_notifications`** and **`set_notification_enabled`**. The rule model
  carries a `kind`, so more check types can be added later without a schema change. Each rule
  has a **base period** — look back a number of minutes / days / months / years (or all history)
  — so the metric reflects only recent events (minute-precision windows supported).
- **Remote notifications** — besides the Dashboard card, a rule can deliver a **Web browser
  push** and/or an **Email** when it triggers (enabled per rule in the wizard). The push goes to
  every subscriber assigned to the rule's connection (each user enables push once per device);
  email goes to the rule's listed recipients, or — when it lists none — the addresses of the
  users assigned to the connection. Delivery fires once, on the edge into triggered. Web Push is
  implemented in-house (VAPID / RFC 8292 + aes128gcm / RFC 8291 on `cryptography`, no external
  service); email uses an admin-configured **SMTP** server (**Admin → Notifications**, with a
  test-email button). The delivery layer is a channel registry, so further channels slot in
  without changing the rule model.
- **Dashboard** — a cross-connection overview, and the landing screen on a direct sign-in
  (launching a process from the `/home` launcher still opens it directly). A flat,
  **drag-to-rearrange** set of process tiles — each carrying its **connection** as a coloured
  pill (upper-left) — shows events, last-ingest time and a weekly **ingest sparkline** (whose
  flat dashed tail makes a stalled feed obvious); your arrangement is saved per user. An
  overall card totals processes, connections and events. Click a tile to open its A-Chart.
  You can add up to **three extra metrics** — Journeys, Days since last ingest, Active span,
  Avg events/journey, and **Open notes by severity** — shown on every tile and reorderable.
  Only base process flows are listed (derived Σ aggregate / `#` detail projects are hidden).
- **Automatic refresh (A-Chart only)** — set an interval in *Configuration → Auto-refresh*
  (Off / 10s / 30s / 1m / 2m / 5m); a round **countdown ring** and a **↻ Refresh** button
  then appear in the A-Chart's control cluster, between the ▦ Transitions button and the zoom
  controls. On each reload the date window slides forward to "now" (so journeys that arrived
  since the last load appear) and the unfiltered KPI totals are re-read. The timer survives
  collapsing the sidebar and pauses automatically outside the A-Chart.
- **Dashboard auto-refresh** — the Dashboard header gains its own interval control
  (Off / 10s / 30s / 1m / 2m / 5m) with a **countdown ring** and a **↻ Refresh** button that
  reload the **whole** Dashboard on a timer — the process tiles and the Notifications section —
  so a live feed appears without reopening the view. It re-reads the current data (it does not
  re-run the notification checks — that is the background engine, or the Notifications "Refresh
  all"); the interval is remembered per user (`dashboard.autoRefreshSecs`).
- **Live demo-event generator** (`generator/launch.py`) — a standalone background process
  (shell or Docker) that **learns an existing process's structure** (the Markov model the
  Simulation view fits, plus the META value mix) and then **injects one synthetic journey at
  a user-defined interval** (`--min`/`--max` seconds) into a target project. Point an A-Chart
  (auto-refresh on) or the Dashboard at it and watch data arrive in real time. It ships its own
  **container** — a `generator/Dockerfile` and an example `generator/docker-compose.example.yml`
  whose `environment:` block drives **every** parameter through `PMG_*` variables (every CLI
  option now has an env fallback), so a demo feed is one `docker compose up` away.
- **MCP `get_notes` tool** — retrieve a project's notes through the MCP server, grouped by
  severity / status / personal-vs-shared.
- **Correctness test suites** — two independently-verified fixtures (a 10-step order-to-cash
  log and a 30-step cycles/loops log) check every metric against a hand-computed ground truth
  on a live Exasol, across the REST and MCP surfaces.
- **Schema migration** — provisioning now upgrades schemas created by an older version
  (adds and backfills `STEP_ID`, adds `SAMPLE_SET`), so existing installs keep working.

### Changed

- **New version format** — calendar-style `YYYY.MINOR.PATCH` with a landmark codename,
  replacing `V 1.0.0 – Mount Maunganui`; this release is **`2027.1.0 – Tongariro`**.
- **Uncluttered process map** — the bottom-corner canvas controls now **auto-hide behind a
  faint handle and reveal on hover**: the lower-right view controls (zoom, fit, reset and the
  optional ▦ Transitions) and the lower-left *Σ Select steps to aggregate* button appear only
  while the pointer is in their corner, each marked at rest by a dim corner handle (⋯ / Σ) so
  the reveal stays discoverable. The **auto-refresh countdown ring stays visible** on its own
  so a live feed can be watched at a glance, and the active aggregate-pick toolbar stays put.
- **Demo data** — the *Airport Passenger Flow* dataset now has a **seasonal** passenger
  volume (summer holidays and Christmas peak, September high, May low). All demo datasets are
  spread over a **rolling two-year window ending on the generation day**, so recent views
  (the Dashboard sparklines, the journeys-over-time chart) are never empty, and are written
  in **25,000-row transactions** rather than per-statement autocommit.

### Security

- **MCP** — the OAuth provider's JWKS is fetched over **TLS-verified** HTTPS by default
  (configurable CA / explicit opt-out); user mapping is hardened (no fallback to mutable
  claims, the built-in administrator can't be federated, exact group-membership match);
  added Origin validation and JSON-RPC edge-case handling.
- **Event-receiver sink** — the request body is size-capped **while streaming**; a failed
  write is never retried (no double-write of append-only journeys); the supervisor isolates a
  listener that fails to bind; step ids are scoped per project.
- **Database manager** — a dropped-socket auto-retry now fires only for read-only statements,
  never a write that may already have committed.
- **CI** — the dependency-audit job is resilient to transient PyPI outages.

### Fixed

- Removed stray NUL bytes that made a few source files read as binary to tooling.

---

## [1.0.0] — "Mount Maunganui"

Initial release. A web-based, multi-user process-mining demonstrator on Exasol:

- The **process map** (A-Chart / B-Chart) with filtering, the A/B Comparison (Process
  Goodness and Process Similarity), Individual Journey (flowchart and swimlane), Statistics,
  Conformance Check, Happy Path, Notes, Simulation and AI-supported Documentation.
- **Admin interface** (TLS, users and 2FA, per-user database connections, logging, backup,
  licensing) and role model (admin / power / developer / plain).
- **Integration console** with the extractor abstraction layer, file imports and the watchdog.
- The **Actions** surface (business-readable DSL run from node menus).
- The **AI Agent Logging Sink** (event-receiver) and the **MCP server** (OAuth-gated,
  read-only query tools plus note writes).
- Ed25519-signed licensing with a Demo-Mode grace period.
