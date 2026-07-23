# Process Mining Demonstrator — Web Edition

A web port of the macOS/SwiftUI **Process Mining Demonstrator**. It connects to an
[Exasol](https://www.exasol.com) database, reads a journey/event log, and renders
how real cases flow through your business processes as an interactive map — with
filtering, A/B comparison, Monte Carlo simulation, conformance checking, sampling
and optional AI-assisted documentation.

Flow charts are drawn with [ReactFlow](https://reactflow.dev) (`@xyflow/react`,
MIT — non-Pro features only).

> **Demo & education only.** This is a demonstrator for log-file analysis and
> process mining on the Exasol Analytical Database. It is not designed or
> validated for production use.

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

## Administration & TLS

The admin interface at <http://127.0.0.1:8090> (and <https://127.0.0.1:8453> once
TLS is enabled) manages security. Sign in with the
default administrator (**Administrator / Administrator**) — you're prompted to
change the password on first use. It is organised into five tabs: **App Control**
(restart the servers), **TLS / SSL**, **Users**, **Database Connections** and
**Directory (LDAP)**.

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
(on by default). Passwords are scrypt-hashed; certificate private keys are
encrypted at rest. The security store lives in `data/security.sqlite3`.

**Database Connections.** Administrators define each connection here — the Exasol
host/port/user/password/schema, an optional OpenAI-compatible LLM server, and TLS
options — and **assign it to one or more users**. Each user sees and can connect to
*only* the connections assigned to them; connection secrets never leave the admin
interface (the main app receives host, port, schema and whether an LLM is attached,
but no passwords or API keys). Use **Test connection** to check the database (and
LLM) before saving. Leaving a password or API-key field blank on an existing
connection keeps the stored value; the backend decrypts secrets only when a user
actually connects. Connection definitions and assignments live in
`data/security.sqlite3`.

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

Environment overrides: `PMW_ADMIN_PORT` (8090), `PMW_FRONTEND_HTTPS_PORT` (8443),
`PMW_DEFAULT_ADMIN_USER`, `PMW_DEFAULT_ADMIN_PASSWORD`, `PMW_ADMIN_SESSION_TTL`.

## Database schema

Reads from `PROJECTS`, `JOURNEYS`, `STEPS`, `METAS` (all required). A `NOTES`
table and the `JOURNEYS.SAMPLE_SET` column are created automatically on first use
if the connecting user has the necessary rights. The schema is identical to the
macOS app — see the in-app **Help → Database setup** chapter or `ARCHITECTURE.md`.

## Tests

The suite mirrors the macOS app's two test targets: pure model & simulation logic
(no database required) and a UI/launch smoke check. It is split across the two
tech stacks.

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

Ported directly from the Swift `ModelLogicTests` and `SimulationEngineTests`, plus
coverage of the web-specific compute layer.

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
| `components/ui.test.tsx` | Render smoke tests (the web analogue of the Swift UI launch tests): `Unavailable`, `Switch`, `Segmented`, `RangeSlider`, and the Markdown renderer's headings/bold/tables/lists |

## Data & privacy

- App preferences — filter presets, happy paths, target norms and node layouts —
  live in `data/settings.sqlite3`.
- Users, admin-defined database connections and their assignments, TLS
  certificates and the directory (LDAP) configuration live in
  `data/security.sqlite3`.
- Secrets — database passwords, LLM API keys, the LDAP service-account password
  and certificate private keys — are encrypted (Fernet) using the key file
  `data/secret.key` (created with mode `0600`); user passwords are scrypt-hashed.
- Backups export as JSON, optionally encrypted with AES-256-GCM, and are
  interchangeable with the macOS version's backups.

The whole `data/` directory (default location; override with `PMW_DATA_DIR`, or
bind-mount it with Docker) is git-ignored — back it up to preserve users,
connections, certificates and settings.

## Parity with the macOS app

Functionality and look-and-feel mirror the SwiftUI original: the collapsible left
sidebar, the KPI strip, node drag / group collapse / pan-zoom interactions, the
valve-synchronised A/B panels, sticky notes on nodes and edges, and every
analytics formula (process goodness, happy-path conformance, A/B similarity Q,
the Markov simulation engine) are ported directly from the Swift sources.

## License

See [`LICENSE`](LICENSE) for the full license text.
