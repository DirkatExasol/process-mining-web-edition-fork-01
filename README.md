# Process Mining Demonstrator — Web Edition

## **What Is Process Mining and why it matters?**
Every transaction in your ERP, CRM, or ticketing system leaves a trace: a case ID, an activity, a timestamp. Process mining reads those event logs and reconstructs how your processes actually run — not how the flowchart says they should.
The gap between the two is where the money sits. A purchase-to-pay process designed with five steps often has forty variants in practice: rework loops, manual workarounds, orders bouncing between departments. Process mining surfaces those variants, counts them, and attaches cost and duration to each.
For business analysts, this replaces workshop guesswork with evidence. Rather than interviewing ten people about how they handle exceptions, you see the exceptions, ranked by frequency and impact. Which supplier causes the most payment delays? Does that extra approval step reduce errors, or just add four days?
For process owners, the payoff is decision confidence. Quantify a bottleneck before investing in automation, then measure whether the fix worked. Conformance checking flags compliance breaches — an invoice approved by the person who raised it — across every case, not a sample.
Process mining doesn't replace domain expertise. It gives that expertise a factual baseline, so effort targets the few variants driving most of the delay.

### From Transactions to Traces: Log Data as a New Source for Exasol
Analytical workloads are usually fed by transactional systems — orders, invoices, ledger postings — which describe state. Process mining instead consumes event logs from ERP change tables, audit trails, and application journals: append-only, high-volume, semi-structured. Reconstructing process paths requires self-joins, window functions, and sequence analysis over hundreds of millions of rows, where Exasol's in-memory columnar engine keeps exploration interactive.
***Note: this application is intended for demonstration and educational purposes only, and is not a production-ready process mining solution.***

---

## Architecture

Three independent Python processes:

| Process | Port | Responsibility |
|---|---|---|
| **Compute Backend** (`backend/`) | 8000 | Exasol access, analytics, simulation, sampling, LLM proxy, settings store |
| **GUI Server** (`frontend/`) | 8080 / 8443 | Serves the React SPA and proxies `/api/*`; binds HTTP and/or HTTPS per the TLS mode |
| **Admin Interface** (`admin/`) | 8090 | TLS/certificate management, the user allow-list, and per-user database connections |

```
Browser ──► GUI Server (:8080 / :8443) ──proxy /api──► Compute Backend (:8000) ──► Exasol
              React + ReactFlow SPA                        pyexasol / openai

Admin ────► Admin Interface (:8090) ──► security store (users, certificates, TLS mode, connections)
```

The browser only ever talks to the GUI server, so the compute backend can run on a
separate host close to the database.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full component and formula map.

## Requirements

| Item | Version |
|---|---|
| Python | 3.13 (falls back gracefully to 3.11+) |
| Node.js | 20+ (only to build the SPA) |
| Exasol | any reachable instance |
| LLM (optional) | any OpenAI-compatible endpoint |
| Docker (optional) | for the containerised deployment — see [Running with Docker](#running-with-docker) |

## Setup

```bash
# 1. Python environment + backend dependencies
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
# (optional) test dependencies:
.venv/bin/pip install -r requirements-dev.txt

# 2. Build the frontend (installs npm deps on first run)
./run.sh --build
```

## Running

```bash
./run.sh            # compute backend :8000 + GUI server :8080/:8443 + admin :8090
```

Then open the app at <http://127.0.0.1:8080> and the admin interface at
<http://127.0.0.1:8090>. For frontend development with hot reload:

```bash
./run.sh --dev      # backend :8000 + admin :8090 + Vite dev server :5173
```

Environment overrides: `PMW_BACKEND_PORT`, `PMW_FRONTEND_PORT`,
`PMW_FRONTEND_HTTPS_PORT`, `PMW_ADMIN_PORT`, `PMW_ADMIN_HTTPS_PORT`,
`PMW_BACKEND_URL`, `PMW_DATA_DIR`, `PMW_DEFAULT_ADMIN_USER`,
`PMW_DEFAULT_ADMIN_PASSWORD`, `PMW_QUERY_TIMEOUT`.

## Running with Docker

A single image runs all three services; persisted state lives in a host `./data`
directory (relative to the compose file):

```bash
docker compose up -d --build
```

App → <http://localhost:8080>, admin → <http://localhost:8090>. The compose file
publishes `8080`/`8443` (app HTTP/HTTPS) and `8090`/`8453` (admin HTTP/HTTPS); the
HTTPS ports activate once TLS is enabled in the admin. The compute backend stays
internal to the container.

- **Persistence** — everything the app must keep (the `settings`/`security`
  SQLite databases, the Fernet `secret.key`, TLS certificates and the GUI PID)
  is written under `/app/data`, bind-mounted from `./data`. Back that directory
  up to keep users, connections, certificates and settings.
- **First-run admin** — set `PMW_DEFAULT_ADMIN_PASSWORD` in `docker-compose.yml`
  before the first `up` (it only applies while the security database is empty).
- The image builds the SPA in a Node stage and runs the Python services in a
  slim runtime via `run.sh`; `.dockerignore` keeps local state and secrets out.
- **Auto-rebuild** — `docker compose watch` (or `docker compose up --watch`)
  monitors the source directories and rebuilds the image when they change. The
  build stays cheap because Docker's layer cache is the real "needs rebuilding?"
  check — untouched layers are reused, so only the affected parts rebuild.

## First use

1. Database connections are defined by an administrator (see below) and assigned
   to users. Open **Connections** in the sidebar — you'll see only the connections
   assigned to you.
2. Click a connection card to connect (click again to disconnect).
3. Open **Projects** and pick one. Explore the ten views from the **☰** menu:
   A-Chart, B-Chart, A/B Comparison, Individual Journey, AI Documentation,
   Statistics, Conformance Check, Happy Path, Notes and Simulation.

> If the sign-in panel shows a **Demo Mode** banner, no license is installed yet.
> The app runs for a limited grace period; an administrator applies a license in
> **App Control → License** (see *App licensing & Demo Mode* below).

## Administration & TLS

The admin interface at <http://127.0.0.1:8090> (and <https://127.0.0.1:8453> once
TLS is enabled) manages security. Sign in with the
default administrator (**Administrator / Administrator**) — you're prompted to
change the password on first use. It is organised into tabs: **App Control**
(restart the servers, manage the license), **TLS / SSL**, **Users**,
**Database Connections**, **Directory (LDAP)**, **Logging**, **Backup** and
**Customize**.

**TLS / SSL.** Generate a self-signed certificate (common name + SANs, validity,
key size) or upload your own PEM cert + key, mark one *active*, then choose the
mode. The **GUI server and the admin interface both follow this one mode and share
the same active certificate** — each runs under a TLS-aware launcher that binds
HTTP and/or HTTPS accordingly:

| Mode | GUI server binds | Admin interface binds |
|---|---|---|
| **Off** | HTTP only (`:8080`) | HTTP only (`:8090`) |
| **Optional** | HTTP **and** HTTPS (`:8080` + `:8443`) | HTTP **and** HTTPS (`:8090` + `:8453`) |
| **Required** | HTTPS only (`:8443`) | HTTPS only (`:8453`) |

Changes take effect on restart — the **↻ Restart app server** button rebinds
**both** launchers' listeners in place (no terminal needed). If a mode needs a
certificate but none is active, each server falls back to HTTP so nothing is left
unreachable — including the admin interface itself, so a bad certificate can't lock
you out.

**Users & sign-in.** The admin interface controls who is allowed to use the
application: create users, enable/disable access, grant/revoke the admin role, and
reset passwords. The main app shows a **sign-in panel** and authenticates against
this user store — only enabled users get in. Sign-in is enforced at the GUI server
(every `/api/*` call needs a valid session cookie); the **Require sign-in** toggle
in the admin *Users* section can turn the gate off for single-user/kiosk use
(on by default). A configurable **failed-sign-in lockout** (*Disable an account
after N failed sign-in attempts*, `0` = off) automatically disables an account —
including the built-in `Administrator` — after too many wrong passwords; the login
panel then shows a clear message and the account carries a *Locked* badge in the
*Users* tab where it can be unlocked (or restart with `PMW_RESET_LOCKOUTS=1` as a
break-glass valve). Passwords are scrypt-hashed; certificate private keys are
encrypted at rest. The security store lives in `data/security.sqlite3`.

**Customize.** The *Customize* tab sets the **login-page background** for *both*
sign-in pages (the main app and the admin interface): keep the default
theme colour (which follows light/dark mode), pick a solid colour, or upload a
background image (PNG/JPEG/GIF/WebP/SVG, up to ~3 MB, scaled to cover). The choice
is stored in the security store and applied to new sign-ins immediately; a live
preview shows the result before you save. Uploaded values are validated so they
can never inject CSS.

**Power role.** Beyond admins, a user can be granted the **power** role
(*Make power* / *Remove power* in the admin *Users* tab). Power users create and
manage their **own** database connections from within the main app — a ＋ button in
the sidebar *Connections* header opens an editor with the same DB/TLS/LLM fields and
an assign-to-users list — and edit or delete only the connections they created (an
✎ button on those cards). Every connection a power user creates is auto-assigned to
them so they can connect immediately. Admins still see and manage every connection.
The role is enforced server-side: the power endpoints reject non-power users and any
attempt to touch a connection the caller does not own.

**Database Connections.** Administrators define each connection here — the Exasol
host/port/user/password/schema, an optional OpenAI-compatible LLM server, and TLS
options — and **assign it to one or more users** (power users do the same from the
app for their own connections). Each user sees and can connect to *only* the
connections assigned to them; connection secrets never leave the server (the main
app receives host, port, schema and whether an LLM is attached, but no passwords or
API keys). Use **Test connection** to check the database (and LLM) before saving.
Leaving a password or API-key field blank on an existing connection keeps the stored
value; the backend decrypts secrets only when a user actually connects. Connection
definitions, ownership and assignments live in `data/security.sqlite3`.

**Provisioning a process-mining schema.** Both the admin connection editor and the
power-user editor offer **Create schema & tables** — using the entered credentials it
creates the named schema and the required tables (`PROJECTS`, `JOURNEYS`, `STEPS`,
`METAS`, `NOTES`) if they do not already exist (idempotent, `IF NOT EXISTS`). This
requires a database account with `CREATE SCHEMA` / `CREATE TABLE` privileges — only a
database administrator can grant those; the application cannot. The canonical DDL lives
in `backend/app/db/schema_ddl.py` (the same `NOTES` definition the app creates lazily).

**Demo content.** The power-user connection editor has two tabs — *Database / LLM
Details* and *Demo Content*. The Demo Content tab groups the generators into sections,
each with schema · journeys · Generate in one row:

- **Retail** — 📚 *Online Bookstore* (`BOOKSTORE` project): login → browse → basket →
  checkout → payment → fulfilment → delivery, with a 5% returns flow and a flaky
  bank-transfer path.
- **Finance/Insurance** — 💶 *Online Credit Application* (`CREDIT` project): bank/affiliate
  intake → application check (with a 20% rework loop) → credit assessment (*Credit
  Assessment* for bank, *Credit Check* for affiliate) → score-driven approval (<75% auto
  reject, 75–90% agent review with 50% rejection, >90% auto accept) plus a senior-agent
  step for sums over €10,000 (5% declined) → *Accepted* → *Payment to Applicant* →
  *Payment* (payout takes up to ~7 days; higher sums take longer, affiliate is faster) or
  *Rejected*. Metas: Applied Credit Sum · Income Class · Channel (Bank/Affiliate).
- **Transportation** — ✈️ *Flight Booking & Management* (`FLIGHTS` project): login →
  search (with a 30% modify-search loop) → select → book → payment → confirm. 50% of
  bookings are **interline** (multi-airline) and add a *Query Partner Airline System* /
  *Connect Partner Booking System* pair; 20% only manage an existing booking (seat
  reservation / ancillary services). Payment options: Credit Card, SEPA, Apple Pay,
  Google Pay, Advance Payment (5%). Star Alliance-style airlines. Metas: Journey Type ·
  Airline · Payment Method.

Each provisions the schema + tables (if needed) and loads into that dataset's own
project, replacing only that project's journeys. Needs `CREATE SCHEMA` / `CREATE TABLE` /
`INSERT` rights (DBA-granted). The generators live in `backend/app/db/demo_data.py`.

*Event-ID format.* In every dataset the stored `EVENT_ID` (the case/journey key that
ties a journey's rows together) is an **MD5 hash** of a simple synthetic reference —
the dataset prefix plus a **1-based, zero-padded 6-digit sequence number**:

| Dataset | Project | Hashed input | Example |
| --- | --- | --- | --- |
| Online Bookstore | `BOOKSTORE` | `ORD-%06d` → `ORD-000001`, `ORD-000002`, … | `md5("ORD-000001")` = `4c2a8…` |
| Online Credit Application | `CREDIT` | `CRA-%06d` → `CRA-000001`, `CRA-000002`, … | `md5("CRA-000001")` = `9f1b3…` |
| Flight Booking & Management | `FLIGHTS` | `FLT-%06d` → `FLT-000001`, `FLT-000002`, … | `md5("FLT-000001")` = `…` |

The hash is the UTF-8 MD5 lowercase hex digest (`hashlib.md5(raw).hexdigest()`). To
reproduce a specific ID from the shell: `printf 'ORD-%06d' 1 | md5` (or `md5sum` on Linux).

**Directory (LDAP / Active Directory).** When enabled, the **main application** login
also accepts directory accounts via **search + bind**: the server binds with a
read-only service account (or anonymously), searches the base DN with a filter such
as `(uid={username})` (OpenLDAP) or `(sAMAccountName={username})` (AD), then re-binds
as that user with the supplied password. Configure the server URI (`ldap://` or
`ldaps://`, with optional StartTLS and certificate verification — plain LDAP is
allowed for a lab), the service-account bind DN + password, the base DN, and the
user/attribute names, then use **Test** to verify the service bind and a real user
login. On first successful sign-in a directory user is **created locally as a plain,
enabled account** (shown as *directory* in the Users tab) so you can assign database
connections and, if you wish, the admin role to them. Key rules:

- **Local accounts always work** (break-glass), and are checked first — a bad
  directory config can never lock out the local `Administrator`.
- **Admin is never granted from LDAP** — a directory user is a normal user until an
  admin promotes them locally; disabling them locally blocks their sign-in.
- **The admin panel (`:8090`) is admins only** — it accepts local admins *and*
  directory users who have been tagged Admin (same login flow: local first, then
  LDAP). A directory user must first sign in to the app once (which creates their
  local record) and be promoted by an existing admin before they can reach `:8090`;
  the seeded local `Administrator` bootstraps that. Every admin request re-checks
  the account is still an enabled admin, so revoking the role ends access at once.

The service-account password is Fernet-encrypted at rest like other secrets.

**App licensing & Demo Mode.** The compute backend requires a signed license.
Upload the `license.json` you were issued in **App Control → License** — the panel
shows the licensee and expiry date, and lets you remove it. With no valid license
the app runs in **Demo Mode** for a **one-time** grace period (the sign-in panel
shows *Demo Mode — remaining time*, then *No License installed* once it is spent),
after which the compute backend stops itself until a license is applied; applying
one during the grace window cancels the shutdown, and the admin interface keeps
working even after the backend stops so you can always upload one. Licenses are
Ed25519-signed and verified against a public key embedded in the app; the license
file lives at `data/license.json` and the demo marker at `data/demo_grace.json`
(`PMW_LICENSE_GRACE_SECS` tunes the grace period; `PMW_RESET_DEMO=1` clears the
one-time marker). This runtime **app** license is separate from the project's own
software [`LICENSE`](LICENSE).

Environment overrides: `PMW_ADMIN_PORT` (8090), `PMW_FRONTEND_HTTPS_PORT` (8443),
`PMW_DEFAULT_ADMIN_USER`, `PMW_DEFAULT_ADMIN_PASSWORD`, `PMW_ADMIN_SESSION_TTL`.

## Database schema

Reads from `PROJECTS`, `JOURNEYS`, `STEPS`, `METAS` (all required). A `NOTES`
table and the `JOURNEYS.SAMPLE_SET` column are created automatically on first use
if the connecting user has the necessary rights. The schema is documented in the
in-app **Help → Database setup** chapter and `ARCHITECTURE.md`.

## Tests

The suite has two parts: pure model & simulation logic (no database required) and
a UI/launch smoke check. It is split across the two tech stacks.

| Target | Framework | What it covers |
|---|---|---|
| **Backend** (`backend/tests/`) | pytest | Pure model, simulation, analytics, backup, SQL-builder and security (users/certs/TLS) logic — no Exasol connection |
| **Frontend** (`frontend/web/src/**/*.test.ts`) | Vitest + Testing Library | Ported pure TypeScript (layout, colours, formatting, model helpers) and a component render smoke test |

Run everything (installs test deps on first run):

```bash
./test.sh                # backend + frontend
./test.sh backend        # pytest only
./test.sh frontend       # vitest only
```

Or invoke each stack directly:

```bash
# backend
.venv/bin/pip install -r requirements-dev.txt   # once
cd backend && ../.venv/bin/python -m pytest

# frontend
cd frontend/web && npm test        # single run
cd frontend/web && npm run test:watch
```

Both runners are **verbose by default** — pytest lists each test with its
outcome and the ten slowest tests, and Vitest prints every `suite > test` name
with its duration. To silence pytest for a quick pass, override with
`../.venv/bin/python -m pytest -q`.

All tests are deterministic (the simulation tests seed the RNG) and require no
Exasol connection or LLM endpoint.

### Backend — `backend/tests/`

Cover the model & simulation logic plus the web-specific compute layer.

| File | What it covers |
|---|---|
| `test_models.py` | `TimeGranularity.auto` bucketing; `TransitionMetric.is_time_based`; `ProcessTransition.metric_value` / `.id`; `ProcessGraph` maxima and the empty-graph fallback; `HappyPath` legacy decode + branch round-trip; `DatabaseServer` / `LLMServer` / `ConnectionProfile` defaults and round-trips; `NoteTarget` node/edge round-trips; `SampleSet` SQL fragments |
| `test_simulation.py` | The Markov Monte-Carlo engine and `build_graph`: journey counts, per-journey event counts, chronological ordering, cycle-time stats, variant accounting/paths, excluded & required steps, the `maxStepsPerJourney` cap on cyclic graphs, and transition statistics (avg/min/max/stdDev) |
| `test_analytics.py` | Random / temporal-stratified / path-diverse sampling; happy-path conformance (full match, journey-weighting, best-branch); process-goodness coverage penalty; the A/B similarity Q-metric (identical → 1.0, disjoint → low) |
| `test_repository.py` | Value coercion (`as_int` / `as_float` / `parse_date` / `dur_label`) and the SQL clause builders (sample-set, date, step include/exclude, score, combined filters) — verified without a database |
| `test_backup.py` | AES-256-GCM encrypt/decrypt round-trip and wrong-password handling; backup summary; the connection-splitting logic on restore (against an in-memory store) |
| `test_security.py` | User store (seeded admin, case-insensitive auth, enable/disable, last-admin guard), TLS mode & plan (off/optional/required), self-signed generation, cert/key pair validation, encrypted-at-rest keys, scrypt password hashing, per-user database connections (encrypted secrets, assignment filtering, secret-preserving updates), and LDAP directory auth (config encryption, JIT provisioning, local-first `authenticate_app`, admin-panel stays local-only) |
| `test_auth.py` | The GUI server's sign-in gate — `/api/*` gated without a session, `/api/health` exempt, login/session/logout cookie flow, disabled-user rejection, and open access when sign-in is not required (drives the real GUI app with a stub backend) |
| `test_admin_api.py` | The admin interface's connection + LDAP endpoints — admin guard, connection create/list/delete, per-user assignment roundtrip, password-preserving updates, the connection-test `{dbError, llmError, llmModels}` shape, and the LDAP config roundtrip (bind password hidden/preserved) + test endpoint (drives the real admin app with stubbed probes) |
| `test_ldap.py` | The directory search+bind flow against ldap3's in-memory `MOCK_SYNC` server — valid/invalid/unknown login, empty-password and filter-injection guards, canonical-username resolution, and the admin "Test" result shape (no real directory needed) |
| `test_connections_api.py` | The compute backend's connection endpoints — `GET /api/connections` filtered by the trusted `X-PMW-User` header (secrets stripped, open access without it) and the `POST …/connect` authorization gate (403 unassigned, decrypted secret passed through when assigned, 404 unknown id) |
| `test_docgen.py` | The AI-documentation report builder: transition table, journey-paths HTML, conformance gap analysis, happy-path section and prompt assembly |

### Frontend — `frontend/web/src/`

| File | What it covers |
|---|---|
| `graph/layout.test.ts` | The Sugiyama layout: layer assignment for linear and fork graphs, determinism, cyclic-graph safety, timestamped-node height, and non-overlapping `BELONGS_TO` group boxes |
| `graph/colors.test.ts` | `namedColor` (named / hex / fallback), gradient interpolation, deterministic `groupColor`, and per-metric default schemas |
| `graph/format.test.ts` | Count / duration / compound-seconds formatting and the ISO-date round-trip |
| `types.test.ts` | `metricValue`, `maxMetricValue`, `isTimeBased`, sample-set labels and note-target keys/labels |
| `components/ui.test.tsx` | Render smoke tests: `Unavailable`, `Switch`, `Segmented`, `RangeSlider`, and the Markdown renderer's headings/bold/tables/lists |

## Data & privacy

- App preferences — filter presets, happy paths, target norms and node layouts —
  live in `data/settings.sqlite3`.
- Users, admin-defined database connections and their assignments, TLS
  certificates and the directory (LDAP) configuration live in
  `data/security.sqlite3`.
- Secrets — database passwords, LLM API keys, the LDAP service-account password
  and certificate private keys — are encrypted (Fernet) using the key file
  `data/secret.key` (created with mode `0600`); user passwords are scrypt-hashed.
- Backups export as JSON, optionally encrypted with AES-256-GCM.

The whole `data/` directory (default location; override with `PMW_DATA_DIR`, or
bind-mount it with Docker) is git-ignored — back it up to preserve users,
connections, certificates and settings.

## Features

A collapsible left sidebar, the KPI strip, node drag / group collapse / pan-zoom
interactions, valve-synchronised A/B panels, titled threaded sticky notes on nodes
and edges (a title/subject shown as a heading, a NORMAL/INFO/IMPORTANT/URGENT
importance badge and a resolved flag, attributed to the signed-in user — the real
name for directory accounts; anyone who can see a note may add a titled comment to
the top of the thread, while only its author changes its classification or deletes
it; the list is filterable by importance, author, time and status, and paged), and
a full analytics suite: process goodness, happy-path conformance, A/B similarity Q
and a Markov simulation engine.

## License

See [`LICENSE`](LICENSE) for the full license text.
