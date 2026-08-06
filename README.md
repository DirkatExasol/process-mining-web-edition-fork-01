<div align="center">

<img src="frontend/web/public/logo.svg" width="128" height="128">

# Process Mining Demonstrator —- Web-Edition


[![Exasol|database](https://img.shields.io/badge/Exasol-database-blue.svg)](https://www.exasol.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

**In-place lakehouse query engine for Exasol. DataFusion runs in Rust UDFs and queries Iceberg
and Databricks tables straight from SQL.**

</div>











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

Four independent Python processes:

| Process | Port | Responsibility |
|---|---|---|
| **Compute Backend** (`backend/`) | 8000 | Exasol access, analytics, simulation, sampling, LLM proxy, settings store |
| **GUI Server** (`frontend/`) | 8080 / 8443 | Serves the React SPA and proxies `/api/*`; binds HTTP and/or HTTPS per the TLS mode |
| **Admin Interface** (`admin/`) | 8090 / 8453 | TLS/certificate management, the user allow-list, and per-user database connections |
| **Integration Console** (`integration/`) | 8100 / 8463 | Data-source configuration; developers and admins only |

```
Browser ──► GUI Server (:8080 / :8443) ──proxy /api──► Compute Backend (:8000) ──► Exasol
              React + ReactFlow SPA                        pyexasol / openai

Admin ────► Admin Interface (:8090 / :8453) ──► security store (users, certificates, TLS mode, connections)

Developer ► Integration Console (:8100 / :8463) ──► data-source configuration (same sign-in, role-gated)
```

The GUI, admin and integration surfaces share one sign-in stack (password, TOTP
two-factor, WebAuthn passkey) and the same TLS mode + active certificate.

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
./run.sh            # backend :8000 + GUI :8080/:8443 + admin :8090 + integration :8100
```

Then open the app at <http://127.0.0.1:8080>, the admin interface at
<http://127.0.0.1:8090>, and (for developers / admins) the integration console
at <http://127.0.0.1:8100>. For frontend development with hot reload:

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

**Logging.** A shared, structured log written by all servers. Each entry carries a
timestamp, severity (INFO → USAGE → WARN → ERROR → DEBUG), client IP, user, an
*operation* (which code path wrote it) and an optional **tag** — a coarser category
grouping a whole activity across operations and severities. Three tags ship today: **`SQL`** on every entry that quotes an executed statement (the
per-statement DEBUG trace and the error/timeout entries), **`BACKUP/RESTORE`** on every
export, inspect and restore including their failures, and **`DATA`** on data imports: the start and result of every import, whether run by hand in the integration
console or by a file-source watchdog, at **USAGE** on success and **WARN/ERROR** on
failure. Filter by tag to see the complete import history. The exported `.log` line is
`DATE -- TIME -- SEVERITY -- CLIENT-IP -- USER -- TAG -- text`.

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
after N failed sign-in attempts*, **default 3**, `0` = off) automatically disables
an account after too many wrong passwords; the login panel then shows a clear
message and the account carries a *Locked* badge in the *Users* tab where it can be
unlocked (or restart with `PMW_RESET_LOCKOUTS=1` as a break-glass valve). The
built-in `Administrator` is deliberately **exempt from auto-lockout** — it's the
sole recovery account, so letting an unauthenticated attacker who knows its name
disable it would be a denial-of-service; it's protected instead by the throttle
below plus scrypt cost. Independently, **both sign-in pages are rate-limited per
source IP** (a short auto-recovering cooldown after repeated failures from one
host, returning `429`; shared implementation in `app/services/login_throttle.py`),
so username-rotation guessing — and TOTP-code guessing — is throttled even for
accounts the lockout doesn't cover (the built-in Administrator) and for the code
step (where a wrong code deliberately does **not** disable the account). The
throttle keys on the **socket peer address** (it never trusts `X-Forwarded-For`,
which a client can spoof), so run the app/admin server as the **edge TLS listener**
(as `run.sh` does). Behind a reverse proxy the peer is the proxy, so every request
would share one bucket — terminate TLS at the app, or add trusted-proxy handling
before fronting it. Passwords are scrypt-hashed; certificate private
keys are encrypted at rest. Both the admin and app servers send hardening response
headers (`X-Frame-Options: DENY` + CSP `frame-ancestors 'none'` against
clickjacking, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
and HSTS when TLS is on). The security store lives in `data/security.sqlite3`.

**Passkeys (WebAuthn).** Both the app and the admin interface accept **passkey**
sign-in (Touch ID, Windows Hello, a hardware security key) as an *alternative* to
the password — the password (or directory sign-in) always remains a fallback, so a
lost device never locks anyone out. Passkeys are **admin-gated per user**: the
*Passkey* column in the admin *Users* tab (with an all-users master checkbox) grants
who may enrol and use one; both local and directory accounts qualify. An allowed
user enrols a device while signed in — from the main app (**🔑 Passkeys**, next to
*Sign out*) or, for admins, from **App Control → Passkeys** — then signs in by typing
their username and clicking **Sign with Passkey**. Because the Relying-Party ID is
the host without its port, **one passkey works for both** the app (`:8443`) and the
admin panel (`:8453`) on the same host. Only the credential's public key and a
replay-guarding signature counter are stored (`credentials` table); turning a user's
permission off — or deleting the user — invalidates their passkeys immediately. The
"Sign with Passkey" button is always shown; the ceremony is **enumeration-resistant** —
the begin step returns the same response (a challenge with a stable *decoy* credential
id derived from an install secret) for unknown or ineligible usernames as for real ones,
so probing the endpoint never reveals which accounts exist or have a passkey. Only
genuine WebAuthn verification at the finish step tells them apart.
WebAuthn requires a **secure context** (HTTPS, or `localhost` for local testing), so
off-localhost run TLS *Optional*/*Required*. It also requires a **real hostname** — the
standard forbids a bare **IP address** (or single-label host) as the domain a passkey is
bound to, so reaching the app by IP (e.g. a tablet connecting to a Mac on the LAN) fails
with *"the effective domain … is not a valid domain."* Use a name the client can resolve —
the host's `.local` Bonjour name, or a LAN/DNS entry — and issue the TLS certificate for
that name; the UI hides the passkey controls (with a hint) when it detects an IP, and
password sign-in works regardless. For split app/admin sub-domains, set
`PMW_PASSKEY_RP_ID` to the shared parent domain and list allowed origins in
`PMW_PASSKEY_ORIGINS` (both optional; single-host deployments need neither).

**Two-factor authentication (TOTP).** Both surfaces also support an authenticator-app
**second factor** (Google Authenticator, 1Password, Authy…) after the password —
*admin-gated* via the **2FA** column in the admin *Users* tab (with an all-users master
checkbox). Enabling it makes 2FA **mandatory** for that user: if they haven't configured
it, their next sign-in stops after the password and **forces enrolment** (QR + confirm +
recovery codes) before any session is issued — on both the app and the admin panel — so
it can't be bypassed by simply never enrolling. Turning the column back off removes the
requirement. An allowed user sets it up from
**🔒 Two-factor** in the app (or **App Control → Two-factor** for admins) by scanning a
QR and confirming one code; they're then issued one-time **recovery codes** (shown once)
for a lost device. At sign-in, after the password an enrolled user is asked for the
current 6-digit code or a recovery code — a **passkey** sign-in already counts as strong
auth and skips the step. The TOTP secret is stored **encrypted** and recovery codes only
as **hashes** (`mfa_recovery_codes` table); revoking a user's 2FA permission relaxes the
factor rather than locking them out, and deleting the user clears both. **Turning off 2FA
(from the app or admin) requires the current code**, so a hijacked session alone can't
strip the second factor; an admin who needs to help a locked-out user instead unticks 2FA
for them in the *Users* tab. The two-step login holds the "password verified" state in a
short-lived signed cookie (with a namespaced audience so it can never be accepted as a real
session), so no session exists until the code checks out. Set `PMW_MFA_ISSUER` to change
the label shown in the authenticator app (defaults to the product name).

**Scheduled backups.** The *Backup* tab can write an **encrypted backup on a
schedule** while the admin server is running (an in-process scheduler; no external
cron needed). Enable it, build the schedule like a crontab — a frequency
(hourly/daily/weekly/monthly) + time via dropdowns, or a raw five-field cron
expression, with a live cron string and plain-English preview — set the retention
count and the AES-256-GCM password, then save. The password is stored **encrypted
at rest** (Fernet) so unattended runs work, and is never returned to the client
(only a *set* flag). Files are written under `data/backups/` (git-ignored) as
timestamped encrypted `.json` envelopes; older files beyond the retention count are
pruned. A *Run backup now* button tests the configuration, and the last run's
outcome is shown. Endpoints: `GET|POST /api/backup/schedule`, `POST
/api/backup/run-now` (admin only).

**Customize.** The *Customize* tab sets the **login-page background** for *both*
sign-in pages (the main app and the admin interface): keep the default
theme colour (which follows light/dark mode), pick a solid colour, or upload a
background image (PNG/JPEG/GIF/WebP/SVG, up to ~3 MB, scaled to cover). The choice
is stored in the security store and applied to new sign-ins immediately; a live
preview shows the result before you save. Uploaded values are validated so they
can never inject CSS.

**Timezone.** *App Control* has a **display-timezone** setting (a searchable list of
all IANA zones, populated from the browser). It governs every server-rendered
timestamp — the **log viewer and exported `.log`**, **backup times**, and the
**backup schedule** itself (so "daily at 02:00" fires at 02:00 in the chosen zone,
DST-aware). Timestamps that the admin panel renders client-side (last sign-in,
certificate dates, last-built) follow it too. Leave it *Server local* to use the
server's own clock (the default). Log instants are stored as UTC epochs, so
changing the zone re-renders history correctly — nothing is rewritten. Named zones
need the IANA database, so `tzdata` is a backend dependency (the slim container
image ships no system zoneinfo). The **main app** shows each user their own
browser's local time, independent of this setting.

**Power role.** Beyond admins, a user can be granted the **power** role
(*Make power* / *Remove power* in the admin *Users* tab). Power users create and
manage their **own** database connections from within the main app — a ＋ button in
the sidebar *Connections* header opens an editor with the same DB/TLS/LLM fields and
an assign-to-users list — and edit or delete only the connections they created (an
✎ button on those cards). Every connection a power user creates is auto-assigned to
them so they can connect immediately. Admins still see and manage every connection.
**Developers** get the same connection management. The connection editor also has a
**Projects** tab that lists the projects stored in the connection's schema — each with
its journey and event counts — and can **delete a project** (clearing its rows from
`PROJECTS`, `JOURNEYS`, `STEPS`, `METAS`, `NOTES` and `TRANSITIONS_RAW`); the same tab
exists in the admin *Database Connections* editor.
Power users (and admins) also get the advanced-analysis views — Conformance Check,
Happy Path and Simulation — and the **journey Sampling** section of the left panel
(creating or deleting samples rewrites the shared sample sets for everyone on the
connection). The role is enforced server-side: the power/sampling endpoints reject
non-power users, and any attempt to touch a connection the caller does not own. The
in-app Help has a **Users & Permissions** chapter with the full capability matrix.

**Developer role & the Integration console.** A user can be granted the **Developer**
role (the *Developer* checkbox in the admin *Users* tab). It grants access to the
**Integration console** — a fourth surface for configuring data sources, served on a
separate port (the admin port + 10 → HTTP `8100` / HTTPS `8463` by default). Only
**power users, developers and admins** may sign in; everyone else is refused with a
clear message. The console reuses the same sign-in stack (password, TOTP, passkey,
mandatory-2FA enrolment) and follows the same TLS mode + certificate as the app and
admin (change them in *TLS / SSL*; a restart applies to all three surfaces at once).
Admins can turn the whole console off from **Admin → Integration**. The data-source
configuration features themselves are being built on this scaffold.

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
- **A directory login never adopts a same-named local account.** If a directory
  username collides with an existing *local* (non-directory) account, the LDAP
  sign-in is refused rather than binding onto that account and inheriting its role
  and connection assignments. Practical note when migrating from local accounts to
  LDAP: delete (or rename) the old local rows first, or those users keep signing in
  with their local password — a directory login won't silently take them over.
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

## Integration abstraction layer (extractor API)

The Integration console is fronted by an **abstraction layer** (`backend/app/integration/`)
into which you **plug in extractors**. An extractor reads some source (a file, an API,
another database) and the layer **pushes the extracted records into the schema of the
user's selected connection**. Extractors never touch the database directly — they are
handed an `IngestSession` bound to the target schema, and the layer owns the connection,
batches the writes, tallies rows for the live **status**, and escapes everything.

```
   ┌───────────┐   push records   ┌─────────────────────┐   DDL/DML   ┌──────────────┐
   │ Extractor │ ───────────────► │ Abstraction layer   │ ──────────► │ Target schema│
   │ (plug-in) │  IngestSession   │ (session + status)  │  (backend)  │ (connection) │
   └───────────┘                  └─────────────────────┘             └──────────────┘
```

### The contract (`app/integration/contract.py`)

An extractor implements the `Extractor` protocol and pushes through the `IngestSession`
it is given. **This is the stable API** — it is all an extractor needs:

```python
class Extractor(Protocol):
    info: ExtractorInfo                      # id (slug), name, version, description
    def run(self, session: IngestSession) -> ExtractResult: ...

class IngestSession(Protocol):
    schema: str                              # target schema (from the connection) — read-only

    # Declare (and create if absent) a target table. Idempotent; call before push().
    #   columns: {name: ColumnType};  keys: business-key column names (informational)
    def define_table(self, table, columns, *, keys=()) -> None: ...

    # Append rows to a defined table; returns the count written. Each row is a
    # {column: value} mapping — missing columns become NULL, unknown columns raise.
    # Rows stream in batches, so you can pass a generator over a huge source.
    def push(self, table, rows) -> int: ...

    # Emit a progress line that shows up in the layer status.
    def log(self, message) -> None: ...
```

`ColumnType` is the portable type set the layer maps to concrete database types —
`STRING`, `INT`, `DECIMAL`, `TIMESTAMP`, `BOOL` — so extractors stay database-agnostic.

### Writing and registering an extractor

```python
from app.integration import (
    ColumnType, ExtractResult, ExtractorInfo, IngestSession, layer,
)

class CsvFolderExtractor:
    info = ExtractorInfo(id="csv-folder", name="CSV folder", version="1.0",
                         description="Loads *.csv files from a folder into staging.")

    def run(self, session: IngestSession) -> ExtractResult:
        session.define_table("EVENTS", {
            "CASE_ID":   ColumnType.STRING,
            "ACTIVITY":  ColumnType.STRING,
            "TIMESTAMP": ColumnType.TIMESTAMP,
        })
        session.log(f"loading into {session.schema}.EVENTS")
        rows = 0
        for chunk in read_csv_chunks(...):          # your source, streamed
            rows += session.push("EVENTS", chunk)    # a list of {col: value} dicts
        return ExtractResult(records=rows, tables=("EVENTS",), detail="import complete")

# Plug it in (e.g. at startup):
layer.register(CsvFolderExtractor())
```

The layer runs `extractor.run()` off the event loop, so blocking I/O in `run` is fine.
Raising from `run` marks the run **failed** and records the error in the status; returning
an `ExtractResult` marks it **completed**.

### Where the records land — ingest backends (`app/integration/backends.py`)

The session delegates writes to an `IngestBackend`:

- **`InMemoryIngestBackend`** — keeps tables in memory; the default for local dev and
  the tested reference target (no database needed).
- **`SqlIngestBackend`** — generates schema-qualified DDL/DML (`CREATE TABLE IF NOT
  EXISTS …`, batched `INSERT`) and runs it through a caller-supplied `run_sql` bound to
  the user's Exasol connection. **Safety:** table/column/schema names are validated
  against a strict identifier grammar (never escaped-and-hoped), and values are rendered
  as defensively-escaped literals (`'` doubled, `NULL`/`TRUE`/`FALSE`/typed timestamps),
  so a malformed source value can't corrupt a statement.

### Status (`GET /api/integration/status`)

The layer tracks a **per-user status** the console polls:

```jsonc
{
  "state": "idle",            // idle | running | completed | failed
  "extractorId": null, "extractorName": null,
  "sourceName": null, "sourceTypeName": null,      // run origin (for the canvas)
  "connectionId": null, "connectionName": null, "schema": null,   // active/last run
  "recordsPushed": 0, "recordsDone": 0, "recordsTotal": 0,   // pushed + progress bar
  "tablesTouched": [],
  "startedAt": null, "finishedAt": null, "lastError": null, "messages": [],
  "registeredExtractors": 0,              // how many extractors are plugged in
  "activeConnectionId": null, "activeSchema": null, "connected": false // current target
}
```

`GET /api/integration/extractors` lists the registered extractors (`id`, `name`,
`version`, `description`).

**Live pipeline canvas + history.** The console's main pane renders each import as a graph
— **Source type → Source → Abstraction layer → Connection (destination)** — driven
entirely by this status. The abstraction-layer node shows the run state and a live
progress bar (`recordsDone`/`recordsTotal`), and the edges animate while a run is in
flight. Because it reads the status rather than the run trigger, it lights up for **any**
import: a manual run, or a future watchdog / API-push (any caller that passes
`source_name` / `source_type_name` / `connection_name` to `AbstractionLayer.run` labels
the canvas the same way).

The console keeps an **ingestion history** and folds it into **one** accumulating
flowchart: nodes are **reused** across runs, so every distinct source type, source and
destination is a single node and the abstraction layer is the one hub in the middle. As
imports happen the same graph grows — edges connect whatever combinations have run, the
**Source and Destination nodes show their total imported rows**, and the currently-running
path lights up. While a run is active a dot travels the path node-to-node (like the main
app's Individual Journey), and each connection is **coloured by its latest run** — blue
(idle/completed), green (running), red (failed). The history is per-user, persisted in the
browser's `localStorage`, so it survives reloads and backend restarts (which reset the
in-memory status to idle), and is kept until the user clicks **↺ Clear** (capped at the
newest 50 runs).

Nodes are **draggable** and the arrangement is **persisted per user** (also in
`localStorage`, keyed by node id), so a hand-tuned layout is restored on reload; a
**⤢ Reset layout** button returns to the automatic arrangement. A **？ Help** button
(top-right of the console, mirroring the main app) opens the in-app help; the
**Integration console** help chapters are shown to users with the **developer** role.

### Sources, source types & the File extractor

The console lets a user build the pieces of an extraction:

- A **source type** is a name + an extraction spec (a pasted example log + the
  timestamp/step/id/meta regexes), built in the source-type wizard.
- A **source** is a data origin with a generic `kind` + config. The only kind so far is
  **File**: a *path* (previewed in the wizard — the first N lines), an *encoding*, and the
  *source type* to parse it with.
- **File access is sandboxed.** By default a File source may only read from
  `PMW_INTEGRATION_FILES_DIR` (default `data/integration_files`, a mounted volume; the
  bundled `examples/*.log` are seeded there on first run). Path traversal and symlink
  escapes are rejected. Set `PMW_INTEGRATION_ALLOW_ANY_PATH=1` to instead allow any
  absolute path the server can read (developer-trusted deployments only — it enables
  reading arbitrary server files).

**Running a File source** (`POST /api/integration/sources/{id}/run {projectId}`) builds a
`FileExtractor` and calls `AbstractionLayer.run`: it reads the file line by line, applies
the source type's regexes, normalises the timestamp to a real `TIMESTAMP`, and pushes a
`JOURNEYS` row per event (`PROJECT_ID`=the project id, `EVENT_ID`/`STEP`/`EVENT_TIME` +
`META_1..3`, `SAMPLE_SET='ORIGINAL'`) into the **active connection's schema** via the
`SqlIngestBackend`. Progress and the result appear in the status panel. Lines that don't
yield a case id, step and time are skipped and counted.

**Transactions.** Rows are inserted inside a real transaction (the driver's
per-statement autocommit is turned off for the run) and committed in **brackets** — the
layer commits once `transactionRows` rows have been written, then a final commit for the
remainder. Configure the bracket per source in the wizard (*Transaction bracket*, default
**5000**; **0** = one transaction for the whole import). A larger bracket is more atomic
but holds more open in the database; a smaller one commits steadily, so a failure
part-way leaves the already-committed brackets in place. On failure the open bracket is
rolled back. The same setting applies to a manual run and to the watchdog; the layer
status reports `commits`.

**Compound steps (optional).** When the real activity is split across fields — an action
plus an outcome — a source type may carry rules that build the final `STEP` from several
extracted values:

```jsonc
{"step": "login successful",
 "when": [{"field": "step",   "op": "eq", "value": "login"},
          {"field": "status", "op": "eq", "value": "200"}]}
```

All conditions must hold (AND); rules are checked in order and the **first match wins**;
when none match the plain `step` field is used unchanged, so the feature is purely
additive. Operators: `eq`, `ne`, `contains`, `startswith`, `endswith`, `regex` (string
comparisons are case-insensitive and trimmed; `regex` is the exact-match escape hatch).
Rules may reference any named field, including the **`aux`** ("Helper") role — extracted
like the others but written to no column, so a value such as an HTTP status can drive a
rule without consuming one of the three `META` slots. Built in the source-type wizard,
which previews the derived step against your sample line.

The captured case id is **MD5-hashed** before it is written, so the raw id (which may be a
login or user id) never lands in the clear — `EVENT_ID = md5(raw).hexdigest()`, matching
the lowercase-hex convention used by every bundled dataset (see *Event-ID format* above).
The source-type wizard's *Example JOURNEYS record* still shows the **original** captured
id (labelled *stored as MD5*) so you can verify the extraction against the source line.

**Watchdog — incremental auto-import.** A File source can enable an optional **watchdog**
(configured in the same source wizard: a destination connection, a project id and a poll
interval). A background loop in the compute backend then watches the file and, whenever it
**grows**, imports only the **newly-appended** lines — never the whole file again. A
**checkpoint per source file** (`source_checkpoints` table: byte offset + a small head
signature + running record count) is persisted, so nothing is re-imported across polls or
restarts. Truncation or rotation (the file shrinks, or its head changes) resets the offset
to re-read from the start. Because it runs headless, the watchdog writes into the
**stored** connection saved with the source (not a live session); its runs surface in the
console's live pipeline just like a manual run. Endpoints: `GET
/api/integration/sources/{id}/checkpoint` and `POST …/checkpoint/reset` (force a fresh
re-read). Config: `PMW_INTEGRATION_WATCHDOG=0` disables it globally;
`PMW_INTEGRATION_WATCHDOG_TICK` sets the base loop tick (each source also has its own
interval).

> **Status:** the contract, ingest backends, registry, per-user status, the File
> extractor **and the file watchdog** are in place and tested
> (`backend/tests/test_integration_{layer,extractor,files,watchdog}.py`).
> Next: non-file source kinds.

## Database schema

Reads from `PROJECTS`, `JOURNEYS`, `STEPS`, `METAS` (all required). A `NOTES`
table and the `JOURNEYS.SAMPLE_SET` column are created automatically on first use
if the connecting user has the necessary rights. The schema is documented in the
in-app **Help → Database setup** chapter and `ARCHITECTURE.md`.

`JOURNEYS` is created with `DISTRIBUTE BY EVENT_ID` so every event of a journey
lives on one cluster node — the transition query's `LEAD() … PARTITION BY
EVENT_ID` and the filter `GROUP BY EVENT_ID` then run node-local — and
`PARTITION BY EVENT_TIME` so Exasol can prune by date range (chiefly the
"active in window" EVENT_ID selection behind the last-N-days default). Tables
that pre-date these clauses are unaffected by the `CREATE TABLE IF NOT EXISTS`;
apply them once with `ALTER TABLE JOURNEYS DISTRIBUTE BY EVENT_ID` and
`ALTER TABLE JOURNEYS PARTITION BY EVENT_TIME`.

### Optional pre-materialized transitions

Each connection can opt into reading the process map from a prebuilt
`TRANSITIONS_RAW` table (the directly-follows pairs, with their gap precomputed)
instead of running the `LEAD()` window on every request — a large speed-up for
interactive filtering on big logs. It's **off by default** and **fails safe**:
if the table isn't built (or a rebuild is mid-flight) the map falls back to the
live query, so it never breaks. The active mode is shown as a pill on the chart —
**⚡ Pre-materialized**, **↻ Live query**, or **⚠ Live (not built)** when it's
enabled but the table isn't ready yet.

Enable it per connection in the admin **Connections** tab (it takes effect on the
next chart reload — no reconnect needed), then (re)build the table after each load
of `JOURNEYS`. Three ways to rebuild:

- **Manually** — the *Rebuild now* button on the connection (shows last-built time
  and pair count).
- **From a scheduler** — `POST /api/connections/<id>/rebuild-transitions` on the
  admin server with header `Authorization: Bearer <token>`. Each connection issues
  its **own** token (Database Connections → the connection → *Rebuild from a
  script (API)*): shown once, stored only as a hash, rotatable/revocable, and
  **scoped to that connection only**. That section also renders a ready-to-copy
  `curl` example — pre-filled with the token while it's still visible, with a copy
  button and the `-k` flag (skips the TLS check for the self-signed admin cert).
  Token-triggered rebuilds are **rate-limited per connection** and never overlap,
  so a leaked token can't hammer the database.
- **During provisioning** — tick *Also build …* under *Create schema & tables*.

The rebuild runs the pairing once with `CREATE TABLE … AS SELECT` — so every
column (crucially `EVENT_ID`, which may be `HASHTYPE`, `VARCHAR`, …) inherits its
type from `JOURNEYS` and the read query's `EVENT_ID` semi-join stays
type-compatible — into a staging table that's swapped in with a `RENAME`, so live
readers are never blocked. The pairing's `LEAD()` window partitions by
`PROJECT_ID, SAMPLE_SET, EVENT_ID` (not `EVENT_ID` alone), because it runs over
the whole `JOURNEYS` table at once and `EVENT_ID` is only unique within one
project + sample set — partitioning any wider would pair events across journey
boundaries and invent spurious edges. Whether it's worth it depends on how often
you reload `JOURNEYS`: ideal for batch loads read heavily afterwards, less so for
continuous updates (the table is stale until rebuilt).

> **Rebuild any `TRANSITIONS_RAW` built before this fix.** Earlier builds
> partitioned by `EVENT_ID` alone and can show wrong per-edge values wherever an
> `EVENT_ID` recurs across projects or sample sets. Press *Rebuild now* (or hit
> the API) once per affected connection after upgrading.

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
| `test_models.py` | `TimeGranularity.auto` bucketing; `TransitionMetric.is_time_based`; `ProcessTransition.metric_value` / `.id`; `ProcessGraph` maxima and the empty-graph fallback; `HappyPath` node model (legacy `{steps,branches}` migrated to nodes, nested split/rejoin round-trip); `DatabaseServer` / `LLMServer` / `ConnectionProfile` defaults and round-trips; `NoteTarget` node/edge round-trips; `SampleSet` SQL fragments |
| `test_simulation.py` | The Markov Monte-Carlo engine and `build_graph`: journey counts, per-journey event counts, chronological ordering, cycle-time stats, variant accounting/paths, excluded & required steps, the `maxStepsPerJourney` cap on cyclic graphs, and transition statistics (avg/min/max/stdDev) |
| `test_analytics.py` | Random / temporal-stratified / path-diverse sampling; happy-path conformance (full match, journey-weighting, best-matching-route over enumerated routes through nested splits + rejoins, route cap); process-goodness coverage penalty; the A/B similarity Q-metric (identical → 1.0, disjoint → low) |
| `test_repository.py` | Value coercion (`as_int` / `as_float` / `parse_date` / `dur_label`) and the SQL clause builders (sample-set, date, step include/exclude, score, combined filters) — verified without a database; plus client-supplied `LIMIT` clamping and the generic-vs-verbose `friendly_error` (no raw driver text leaks to a plain user) |
| `test_backup.py` | AES-256-GCM encrypt/decrypt round-trip and wrong-password handling; backup summary; the connection-splitting logic on restore (against an in-memory store) |
| `test_cron.py` | The dependency-free cron matcher powering scheduled backups — minute/hour/day/month/weekday matching incl. `*`, ranges, lists and `*/n` steps, Sunday-as-0-or-7, the Vixie DOM-and-DOW OR rule, and validation rejecting malformed / out-of-range expressions |
| `test_timeutil.py` | The display-timezone resolver — `resolve_zone` (empty/unknown → server-local, never raises), `is_valid_zone`, and correct UTC→zone conversion for a known instant (CEST/EDT) |
| `test_crypto.py` | The `secret.key` first-run creation — atomic (`O_CREAT\|O_EXCL`, mode `0600` from birth, no chmod race), never overwritten by a second/concurrent process, a wedged 0-byte key is recreated rather than fatal, and `write_private_file` writes TLS keys `0600`-from-birth |
| `test_security.py` | User store (seeded admin, case-insensitive auth, enable/disable, last-admin guard), TLS mode & plan (off/optional/required), self-signed generation, cert/key pair validation, encrypted-at-rest keys, scrypt password hashing, per-user database connections (encrypted secrets, assignment filtering, secret-preserving updates), the per-connection pre-materialized-transitions flag, the hash-stored rebuild token (generate/verify/rotate/clear) and per-connection materialization status, the failed-sign-in lockout (default 3, explicit-`0` off, built-in Administrator exempt), the scheduled-backup config (cron/retention/include-flags round-trip with the password stored encrypted at rest and exposed only as a `hasPassword` flag), and LDAP directory auth (config encryption, JIT provisioning, local-first `authenticate_app`, a directory login refusing to adopt a same-named local account, admin-panel stays local-only) |
| `test_materialized_transitions.py` | The optional pre-materialized transitions: `load_transitions` picks `TRANSITIONS_RAW` when enabled and gracefully falls back to the live `LEAD()` query when it isn't built (reporting `materialized` / `fallback` / `live`), and a SQLite proof that the materialized pairs aggregate to exactly the same directly-follows graph as the live query |
| `test_auth.py` | The GUI server's sign-in gate — `/api/*` gated without a session, `/api/health` exempt, login/session/logout cookie flow, disabled-user rejection, and open access when sign-in is not required (drives the real GUI app with a stub backend) |
| `test_admin_api.py` | The admin interface's connection + LDAP endpoints — admin guard, connection create/list/delete, per-user assignment roundtrip, password-preserving updates, the connection-test `{dbError, llmError, llmModels}` shape, the LDAP config roundtrip (bind password hidden/preserved) + test endpoint, and the pre-materialized transitions surface: toggle persistence, the rebuild endpoint (admin session **or** bearer token, 401/404 paths), token generate/rotate/revoke, the provisioning build opt-in, the per-IP login throttle (repeated failures → `429`, cleared on success), the scheduled-backup endpoints (get/set with cron validation, enabling requires a password, run-now writes a decryptable encrypted file and prunes to the retention count, password never echoed) and the scheduler lifespan starting/stopping cleanly, and the dashboard render carrying the **API** tab (rebuild token + copy-able `curl` example, and the token moved out of the Connections tab) (drives the real admin app with stubbed probes) |
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

The process map carries a date-window slider (Range mode with two independently
draggable thumbs, or single-day mode). On first load a project shows the last *N*
days ending at its latest event; *N* is configurable per user under
**Configuration → Default date window** (default 30, `0` = full range).

The three `META_` case-level filters are searchable dropdowns: focus the field
(or tap the ▾) to browse the distinct values pulled from the database, then click
one or type to narrow the list. Steps sharing a `BELONGS_TO` value are wrapped in
a dashed group box whose tint and border are tuned per theme so it stays clearly
visible in both light and dark mode.

## License

See [`LICENSE`](LICENSE) for the full license text.
