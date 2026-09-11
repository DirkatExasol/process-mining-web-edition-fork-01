# Process Mining Demonstrator — Web Edition
## Manual-writer notes: Exasol data model & database operations
Sources: `backend/app/db/manager.py`, `backend/app/db/schema_ddl.py`, `backend/app/db/repository.py`, `backend/app/db/demo_data.py`, `backend/app/models.py`, `backend/app/api/connections.py`, `backend/app/api/projects.py`, `backend/app/services/net_guard.py`, `backend/app/config.py`, `backend/app/store/security.py`, `admin/server.py`, `admin/pages.py`, `frontend/web/src/components/ConnectionEditor.tsx`, `frontend/web/src/views/DetailPane.tsx`.

---

## 1. The Exasol data model (the "canonical process-mining schema")

The app reads and writes six tables inside one Exasol schema (the schema name is part of each connection definition). Five are the canonical set; the sixth (`TRANSITIONS_RAW`) is an optional performance table. The source tables normally arrive with the customer's data; the app can also create them itself (see §4 Provisioning). All provisioning DDL uses `IF NOT EXISTS`, so re-running never disturbs existing data.

### 1.1 PROJECTS
One row per process-mining project.

| Column | Type | Constraint/Default |
|---|---|---|
| PROJECT_ID | VARCHAR(100) | NOT NULL, PRIMARY KEY |
| TITLE | VARCHAR(500) | default `''` |
| DESCRIPTION | VARCHAR(2000) | default `''` |

The project picker lists projects ordered by TITLE.

### 1.2 JOURNEYS (the event log)
One row per (event, step). This is the only large table.

| Column | Type | Constraint/Default |
|---|---|---|
| PROJECT_ID | VARCHAR(100) | NOT NULL |
| EVENT_ID | VARCHAR(200) | NOT NULL — the journey/case identifier |
| STEP | VARCHAR(500) | NOT NULL |
| STEP_ID | DECIMAL(18,0) | orders steps that share the same EVENT_TIME |
| EVENT_TIME | TIMESTAMP | NOT NULL |
| META_1 / META_2 / META_3 | VARCHAR(1000) | free-form attributes |
| SAMPLE_SET | VARCHAR(20) | default `'ORIGINAL'` |

Physical layout declared in the DDL (new tables only):
- `DISTRIBUTE BY EVENT_ID` — co-locates all events of one journey on one cluster node so the transition query's LEAD() window and every GROUP BY EVENT_ID filter run node-local. EVENT_ID is high-cardinality, so rows spread evenly.
- `PARTITION BY EVENT_TIME` — lets Exasol prune by date range (helps the "active in window" EVENT_ID selection more than the final scan). The partition column must differ from the distribution column.
- **Gotcha for pre-existing tables:** `IF NOT EXISTS` leaves existing tables untouched. A DBA must apply the layout manually with:
  - `ALTER TABLE JOURNEYS DISTRIBUTE BY EVENT_ID;`
  - `ALTER TABLE JOURNEYS PARTITION BY EVENT_TIME;`
- **EVENT_ID type varies by deployment** (VARCHAR, HASHTYPE, DECIMAL, …). The app tolerates this; TRANSITIONS_RAW is deliberately built with CREATE TABLE AS SELECT so its EVENT_ID inherits the exact JOURNEYS type — hard-coding a type would make the semi-join raise Exasol's "Incomparable Types" error (see §2).
- **EVENT_ID hashing in demo data:** the generators do not use raw order numbers. Each demo EVENT_ID is the **MD5 hex hash** of a synthetic key — `ORD-000001…` (retail), `CRA-000001…` (finance), `FLT-000001…` (transportation); the SPA's dataset descriptions state this verbatim ("Each EVENT_ID is the MD5 hash of "ORD-000001", "ORD-000002", … (the prefix ORD- plus a 6-digit sequence number).").

**SAMPLE_SET semantics.** Values: `ORIGINAL` (the source data), `SAMPLE_1`, `SAMPLE_2`, `SAMPLE_3`. Everywhere the app filters by sample set, `NULL` is treated as ORIGINAL (`SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL`), so legacy tables without the column-value work unchanged. On demand the app runs a quiet migration: `ALTER TABLE JOURNEYS ADD COLUMN SAMPLE_SET VARCHAR(20) DEFAULT 'ORIGINAL'` plus a backfill `UPDATE … SET SAMPLE_SET='ORIGINAL' WHERE SAMPLE_SET IS NULL` (failures ignored — e.g. the column already exists). Samples are **physical copies**: creating a sample INSERT-SELECTs the chosen journeys' rows back into JOURNEYS with the new SAMPLE_SET value, in batches of 200 event-IDs per INSERT. Deleting a sample deletes only rows with that SAMPLE_SET (ORIGINAL can never be deleted this way — the call is a no-op for ORIGINAL). Sampling strategies offered: `random`, `temporal`, `pathDiverse`.

### 1.3 STEPS (per-step presentation and scoring; edited via the app's Step editor)

| Column | Type | Constraint/Default |
|---|---|---|
| PROJECT_ID | VARCHAR(100) | NOT NULL, PK part |
| STEP | VARCHAR(500) | NOT NULL, PK part |
| DESCRIPTION | VARCHAR(2000) | default `''` |
| BG_COLOR | VARCHAR(30) | default `''` |
| FG_COLOR | VARCHAR(30) | default `''` |
| SCORE | DECIMAL(18,2) | nullable |
| SHAPE | VARCHAR(50) | default `''` |
| END_OF_PROCESS | BOOLEAN | default FALSE |
| BELONGS_TO | VARCHAR(500) | nullable (step group) |

Reader defaults when a value is missing/not a string: description falls back to the step name, bgColor `blue`, fgColor `white`, shape `stadium`. Steps that appear in transitions but have no STEPS row are synthesized in gray (`bgColor gray`, `fgColor white`, `stadium`).

**STEPS cache (gotcha):** STEPS is cached per user per project inside the user's DatabaseManager (it is read on every map reload / journey view). The cache is invalidated when: a step is edited via the Step editor; the user disconnects or connects to another connection (never carried across connections); a manager deletes a project via the connection editor; demo content is generated. It relies on STEPS having one row per (PROJECT_ID, STEP) — duplicates would multiply journey rows in score joins.

### 1.4 METAS (labels for the three META columns)

| Column | Type | Constraint/Default |
|---|---|---|
| PROJECT_ID | VARCHAR(100) | NOT NULL, PRIMARY KEY |
| META_1_TITLE / META_2_TITLE / META_3_TITLE | VARCHAR(500) | default `''` |

If a title is empty/absent the UI shows generic meta labels.

### 1.5 NOTES (created lazily by the app)
Created on demand with `CREATE TABLE IF NOT EXISTS` the first time notes are used, then quietly migrated (each statement's failure ignored): add IS_SHARED, EDITED_BY, IMPORTANCE, RESOLVED, TITLE columns; widen NOTE from the legacy VARCHAR(8000) to VARCHAR(100000) so append-only comment threads have room.

| Column | Type | Constraint/Default |
|---|---|---|
| ID | VARCHAR(36) | NOT NULL, PRIMARY KEY |
| PROJECT_ID | VARCHAR(100) | NOT NULL |
| NOTES_DATE | TIMESTAMP | NOT NULL (created at) |
| EDITED_DATE | TIMESTAMP | nullable |
| NOTE_USER | VARCHAR(200) | default `''` (author login name) |
| NOTE | VARCHAR(100000) | default `''` (thread text; newest comment prepended on top) |
| IS_SHARED | BOOLEAN | default FALSE |
| EDITED_BY | VARCHAR(200) | default `''` |
| IMPORTANCE | VARCHAR(20) | default `'NORMAL'` — one of NORMAL, INFO, IMPORTANT, URGENT (anything else normalizes to NORMAL) |
| RESOLVED | BOOLEAN | default FALSE |
| TITLE | VARCHAR(500) | default `''` |
| TARGET_TYPE | VARCHAR(10) | default `'node'` (`node` or `edge`) |
| TARGET_FROM | VARCHAR(500) | default `''` |
| TARGET_TO | VARCHAR(500) | nullable |
| FILTER_SNAPSHOT | VARCHAR(4000) | JSON snapshot of the filters at note time |

Visibility fails closed: a user sees their own notes plus unowned (`NOTE_USER=''`) and shared ones. Only the author may delete; in anonymous mode (sign-in disabled) the author is the empty string.

### 1.6 TRANSITIONS_RAW — see §2.

---

## 2. Pre-materialized transitions (TRANSITIONS_RAW)

### 2.1 What it is and why
The process map's directly-follows graph is normally computed **live** on every reload: a `LEAD()` window over JOURNEYS pairs each event with its successor (ordered by EVENT_TIME, then STEP_ID), then aggregates COUNT/AVG/MIN/MAX/STDDEV of the gap per (from-step, to-step). On large logs the window function dominates the query time. `TRANSITIONS_RAW` stores the pairing **once**: one row per consecutive step pair, with columns PROJECT_ID, EVENT_ID, FROM_STEP, TO_STEP, FROM_TIME, TO_TIME, DUR_SECS (precomputed gap in seconds), SAMPLE_SET. With it, the map query is a pure GROUP BY aggregate — no window function at request time — "much faster for interactive filtering on large logs" (admin UI wording).

### 2.2 How it is built (rebuild mechanics)
- Built with **CREATE OR REPLACE TABLE … AS SELECT** into a staging table `TRANSITIONS_RAW_STAGE`, so all column types (critically EVENT_ID) inherit from JOURNEYS exactly.
- The pairing covers **every project and sample set at once**; the window partitions by (PROJECT_ID, SAMPLE_SET, EVENT_ID) because EVENT_ID is only unique within one project + sample set.
- After the build: best-effort `ALTER TABLE … DISTRIBUTE BY EVENT_ID` (a failure here never aborts the rebuild — distribution is only an optimization), a row count, then `DROP TABLE IF EXISTS TRANSITIONS_RAW` + `RENAME TABLE` swap. Readers are never blocked by the build; the swap leaves a sub-millisecond window with no live table, during which reads simply fall back to the live query.
- Result payload: `{ok, error, rows, built_at}` — `rows` is the pair count, `built_at` an ISO-8601 UTC timestamp. Idempotent and safe to re-run. Requires a schema name ("A schema name is required." if blank).
- **The table goes stale as soon as JOURNEYS changes.** The admin UI says so explicitly: "It falls back to the live query until the table is built, so rebuild it after each load of JOURNEYS." Creating/deleting a sample or loading fresh data does NOT rebuild it automatically — schedule or trigger a rebuild after each load.

### 2.3 The per-connection flag
- Admin panel (:8090) → **Connections** tab → connection editor → **Database** inner tab → checkbox "**Use pre-materialized transitions**" (bold label). Stored per connection (`useMaterializedTransitions` in the API body; default **off**). Also settable when a power user's connection is managed by an admin; the power-user SPA editor does **not** expose this checkbox — it is admin-panel-only.
- The flag is captured at connect time **and refreshed on every request**: an admin toggling it takes effect on the user's next reload without reconnecting.
- Read behavior with the flag ON: the map query reads TRANSITIONS_RAW with the same filter clauses (it carries PROJECT_ID, SAMPLE_SET, EVENT_ID). **Any** read failure (table missing, not built yet) is non-fatal: the app falls back to the live LEAD() query so the map never breaks, and logs a warning under operation `materialize` ("Pre-materialized transitions are enabled but reading TRANSITIONS_RAW failed for project … — falling back to the live query. Cause: …") visible in the admin Logging tab.
- The UI shows which path served the map, as a pill in the detail pane header (not shown for Individual Journey view):
  - "⚡ Pre-materialized" — tooltip: "Transitions are read from the pre-materialized TRANSITIONS_RAW table."
  - "⚠ Live (not built)" — mode `fallback`: flag on but table unusable; tooltip: "Pre-materialized transitions are enabled for this connection, but TRANSITIONS_RAW is not built yet — running the live query meanwhile. Rebuild it in the admin interface (Connections → Rebuild now)."
  - "↻ Live query" — flag off; tooltip: "Transitions are computed live from the event log on each load."
- The graph API also reports `transitionsMode` (`materialized` | `live` | `fallback`) and `queryMs` (server-side wall-clock of the DB queries, shown in the chart footer as e.g. "123 ms" or "1.23 s").

### 2.4 Rebuilding from the admin panel
Connections tab → connection editor → "Use pre-materialized transitions" banner:
- Button "**Rebuild now**" (disabled until the connection is saved; disabled-button tooltip "Save the connection first"). While running it shows "Rebuilding… (this runs the pairing once and may take a while)"; on success "Built N pairs." (green), on failure the error text (red) or "Rebuild failed."
- Status line beside it (from the last stored outcome): "Not built yet — the live query is used until you rebuild." / "Last built: <date> · N pairs." / red "Last rebuild failed: <error>". The last outcome is persisted per connection in the security store and re-shown when the editor opens.

### 2.5 Rebuild API + per-connection bearer token
Endpoint: `POST /api/connections/{conn_id}/rebuild-transitions` on the **admin** service. Authorization: EITHER a signed-in admin session OR the header `Authorization: Bearer <the connection's rebuild token>`. It uses the **stored** connection credentials, so the calling script never handles database passwords. A token only ever authorizes its own connection.

Token lifecycle (admin panel → connection editor → collapsible "**Rebuild from a script (API)**" box):
- Explanatory text: "Let a scheduler (cron / ETL) rebuild this connection right after loading its JOURNEYS, without an admin login. The token below is scoped to this connection only, and calls are rate-limited."
- Status text: "save the connection first" / "a token is set for this connection" / "no token set".
- Button "**Generate / rotate token**" (confirm dialog: "Generate a new token for this connection? Any existing token stops working."). The token is a 32-byte urlsafe random value; **only its SHA-256 hash is stored** and verified in constant time. Shown **once** with the caption "New token (copy it now — it is not shown again):". Generation and revocation are logged as warnings under operation `materialize`.
- Button "**Revoke**" (shown only while a token is set; confirm: "Revoke this connection's token? A scheduler using it will stop working.").
- A ready-to-copy curl example (📋 copy button, toast "curl command copied"):
  ```
  curl -k -X POST \
    -H "Authorization: Bearer <token>" \
    "https://<admin-host>:<admin-port>/api/connections/<connection-id>/rebuild-transitions"
  ```
  The real token appears in the example only while it is visible after generation, then reverts to `<token>`. UI note: "The token is shown once — copy it now; only its hash is stored. … `-k` skips the self-signed TLS check."
- Deleting a connection also deletes its rebuild token and materialization status.

Guards on the endpoint:
- 401 "Not authenticated" without a valid admin session/token; 404 "No such connection.".
- Overlap guard: two simultaneous rebuilds of one connection are refused — 409 "A rebuild is already running for this connection." (they would race on the staging swap).
- Throttle for **token** callers only (admins may force anytime): 60-second cooldown per connection — 429 "Rebuild throttled — try again in Ns."
- Every rebuild logs "…rebuilt materialised transitions for connection '<name>' (<id>) — ok, N pairs" or "…failed: <error>" under operation `materialize`; the actor is the admin username or `api-token`.

---

## 3. Connection lifecycle

### 3.1 Model: per-user live connections
- Connections are **defined** centrally (admin panel or by power users/developers in the app) and **assigned** to users. In the main app each user sees only the connections assigned to them.
- Each signed-in user gets their **own** DatabaseManager and thus their own Exasol session — users never share a live connection, so data cannot leak between users. Anonymous mode (sign-in disabled) shares one bucket. Usernames are keyed ASCII-case-insensitively (matching the user store's identity model).
- pyexasol is synchronous and one connection is not safe for concurrent statements: every query of a user is serialized through a lock and run on a worker thread. Practical consequence: two long queries from the same user queue behind each other; different users run in parallel.

### 3.2 Connecting (main app)
- `GET /api/connections` lists the caller's assigned connections (secrets stripped; users see id, name, comment, host, port, schema, hasLLM, llmURL-if-set).
- `POST /api/connections/{id}/connect`. Guards: 403 "This connection is not available to you." if not assigned; 404 "Connection not found.". Returns a ConnectionStatus `{isConnected, isLLMReachable, activeProfileId, username, lastError}`.
- Connect opens the Exasol socket (see timeouts §8), captures the connection's cert settings and the materialized-transitions flag, then probes the LLM (see §7). On driver failure the **user-facing message is the generic guidance only** (no Exasol codes, internal hostnames, or SQL-state fragments — those go to the server log under operation `db-connect`); the assigned-user variants are:
  - "Authentication failed — check your username and password."
  - "The database rejected the request." (Exasol query errors)
  - "Connection timed out. Verify the host address, port, and network connectivity."
  - "Connection refused. No server is accepting connections at this host and port."
  - "TLS certificate error. Try 'Skip verification' or configure a fingerprint in the server's security settings."
  - "Host not found. Check the hostname spelling and your DNS / network connectivity."
  - fallback: "Connection failed. Check the host, port, and credentials."
  (Power users/admins running a connection **test** see the same categories with the raw driver detail appended, and Exasol query errors as "[code] message".)
- Race protection: if an admin edits or deletes the connection **while** the (slow) open is in flight, the freshly-opened session is dropped and the caller gets "This connection changed during sign-in. Please reconnect."
- Legacy path note: "This connection has no database server selected. Edit it and choose one." can only appear via the legacy single-user profile endpoints, not the current per-user flow.

### 3.3 Disconnect / status
- `POST /api/disconnect` closes the caller's own session; the close waits for any in-flight statement to finish rather than cutting the socket mid-query. It clears connected state, LLM reachability, the materialized flag, and the STEPS cache.
- `GET /api/connection/status` returns the same ConnectionStatus shape, including `lastError`.
- Running any data query while not connected raises "Not connected." (API surfaces answer 409 "Not connected to a database." from the project endpoints).
- Forced disconnects: editing a connection, deleting it, or changing its assignments immediately drops **every** user's live session on it (revocation must take effect immediately; users re-connect against the new definition and re-pass the assignment gate). Sign-out releases the user's connection.

### 3.4 Testing a connection
- Admin panel: button "**Test connection**" → "Testing…", then banners "Database: connection OK" or "Database: <error>"; if an LLM URL is set additionally "LLM: reachable — N models" or "LLM: <error>". Failures are logged under operations `db-test` / `llm-test`.
- Main-app connection editor (power users): button "**Test**" in the sheet footer; result text "Database OK" / "Database: <error>", plus "LLM OK (N models)" / "LLM: <error>" when an LLM URL is set; colored green (all OK), orange (one of two failed), red (all failed). Separated by " · ".
- The test opens and immediately closes a throwaway connection — it never touches anyone's active session. LLM test failure message when the probe fails: "LLM server not reachable."
- **Gotcha:** the test uses the password **typed in the form**, not the stored one — with a saved connection and a blank password field, the DB test runs with an empty password and typically reports an authentication failure even though the saved connection works.

### 3.5 Who can manage connections (main app)
- Endpoints under `/api/connections` (manageable list, upsert, delete, assignments, test, provision-schema, generate-demo, projects list/delete) require a signed-in, enabled user with the **admin**, **power**, or **developer** role; otherwise 403 "You are not allowed to manage connections."
- Ownership: a power user manages only connections they created (owner = their username); an admin manages all. Violations: 403 "You cannot edit this connection." / "You cannot delete this connection." / "You cannot re-assign this connection." / "You cannot manage this connection."
- Creating a connection auto-assigns the creator so they can use it immediately.
- The identity is carried on the trusted `X-PMW-User` header injected by the GUI proxy after session validation (the backend refuses direct calls without the proxy-auth secret unless `PMW_REQUIRE_PROXY_AUTH` is disabled for dev).

### 3.6 Secrets handling in the editors
Password and LLM API key fields are write-only: placeholder "•••••• (unchanged)" (SPA) / hint "(set — leave blank to keep)" (admin) when a secret exists; leave blank to keep, type to replace; omitting the field in the API keeps it, sending `""` clears it.

---

## 4. TLS certificate modes (database connection)

Controlled per connection; fields appear when "**Use TLS**" is checked (default off).

- "**Certificate mode**" select, options exactly:
  - "Verify (system trust store)" (`verify`, the default)
  - "Pin fingerprint" (`fingerprint`)
  - "Accept any (insecure)" (`insecure`)
- Mode parsing is whitespace-tolerant and fail-**closed**: any unrecognized stored value (typo, legacy/restored data) is treated as *verify*, never as no-verification.
- **Pin fingerprint:** field "Fingerprint (SHA-256)" (placeholder "optional"). Colons are stripped and the value must be pure hex, 16–128 chars; the driver then pins the server certificate via the DSN. A blank or non-hex fingerprint in this mode **refuses to connect** with: "This connection is set to pin a certificate fingerprint, but the fingerprint is missing or not hexadecimal. Enter the server's SHA-256 fingerprint, or change the certificate mode." (This closes a former fail-open where an invalid fingerprint silently disabled verification while the UI still said "pinned". The hex check also blocks pyexasol's literal `nocertcheck` DSN value from sneaking in through this field.)
- **Accept any (insecure):** disables certificate verification and hostname checking. For lab/self-signed setups only.
- Field "**Minimum RSA key size**" (default 2048). **Gotcha for the manual:** the value is stored and carried through every operation (connect, test, provision, demo, rebuild) for compatibility with the macOS app's connection records, but the web backend's TLS options do not currently enforce it — do not present it as an active control.
- Without TLS, encryption is off entirely.

---

## 5. Schema provisioning ("Create schema & tables")

Two surfaces, same backend behavior:

**Admin panel** (Connections tab → connection editor → Database inner tab, info banner):
- Button "**Create schema & tables**". Uses the host/port/username/**typed** password/schema from the form (same blank-password gotcha as testing).
- Checkbox "**Also build pre-materialized transitions after provisioning**" (admin panel only, default unchecked) — after a successful provision it immediately runs a TRANSITIONS_RAW rebuild (the table is empty until JOURNEYS is loaded, but the structure exists and the flag can be used). Result suffix: " · transitions built (N pairs)" or " · transitions build failed: <error>".
- Banner text: "Creates the schema named above and the process-mining tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don't exist, using the credentials entered here. This requires a database account permitted to CREATE SCHEMA and CREATE TABLE — only your database administrator can grant those rights; this application cannot."
- Progress "Creating…"; success "Created: schema <name>, PROJECTS, JOURNEYS, STEPS, METAS, NOTES" (green); failure: the friendly error (red) or "Could not create the schema."

**Main app** (power user/developer/admin → connection editor sheet → "Database / LLM Details" tab):
- Same button label "Create schema & tables", disabled until a schema name is entered. Caption: "Creates the "<schema>" schema and the process-mining tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don't exist. This needs a database account permitted to CREATE SCHEMA and CREATE TABLE — only your database administrator can grant those rights; the app cannot. Uses the credentials entered above." No build-transitions checkbox here.

Behavior:
- Connects **without** opening a schema (the target may not exist yet), then `CREATE SCHEMA IF NOT EXISTS`, `OPEN SCHEMA`, and each table DDL in order PROJECTS, JOURNEYS, STEPS, METAS, NOTES. Idempotent; never disturbs existing data.
- Returns `{ok, error, created}`; on failure `created` lists what was made **before** the failure (partial progress is reported, e.g. schema created but a table failed).
- Blank schema → "A schema name is required." (Admin UI pre-check toast: "Enter a schema name first.")
- The schema identifier is safely double-quoted (embedded quotes doubled), so mixed-case/special names work — but note that a quoted name is case-sensitive in Exasol.

---

## 6. Demo data generation ("Demo Content")

Only in the main app's connection editor (power/developer/admin), tab "**Demo Content**" — the admin panel has no demo generator. Tab intro: "Generate a ready-made dataset into this connection's schema — it creates the schema and the process-mining tables if needed, then loads the journeys (replacing only that dataset's own project). Needs a database account permitted to CREATE SCHEMA, CREATE TABLE and INSERT — only your database administrator can grant those; the app cannot. Uses the credentials on the Database / LLM Details tab."

Three dataset cards, each with fields "Schema" (placeholder "DEMO", shared with the details tab), "Journeys" (numeric, default **500**, min 1, UI max 20,000) and a "Generate" button (spinner label "Generating…"):

| Card section | Icon/Title | Project ID | Project title | META titles (1/2/3) |
|---|---|---|---|---|
| Retail | 📚 "Online Bookstore" | `BOOKSTORE` | Online Bookstore | Payment Method / Customer Segment / Order Value |
| Finance/Insurance | 💶🪙 "Online Credit Application" | `CREDIT` | Online Credit Application | Applied Credit Sum / Income Class / Channel |
| Transportation | ✈️ "Flight Booking & Management" | `FLIGHTS` | Flight Booking & Management | Journey Type / Airline / Payment Method |

Dataset behavior (useful for the manual's "what will I see" sections):
- **retail** — order lifecycle login → browse → basket → checkout → payment → fulfilment → delivery, ~5% returns flow, and a deliberately unreliable Bank Transfer payment path (35% failure per processing attempt, retry loop). 24 steps grouped into Customer Interaction, Purchase Process, Payment, Fulfilment, Returns; scores from −10 (Payment Failed, Return Initiated) to +15 (Delivered).
- **finance** — Bank/Affiliate intake → application check with a ≤2-iteration rework loop (20% chance each) → Credit Assessment (bank) or Credit Check (affiliate) → score-band decision (<75% auto-reject; 75–90% agent review with 50% rejection; >90% auto-accept) → sums over 10,000 EUR need Senior Agent Approval (5% decline) → Accepted → Payment (payout up to ~7 days, larger sums slower, affiliate faster).
- **transportation** — 80% new bookings (search with ≤2 modify loops, 50% interline itineraries that query a partner airline's system and connect to the partner booking system), 20% manage-booking journeys (seat reservation / ancillary services; 60% of them pay). Payment methods: Credit Card, SEPA, Apple Pay, Google Pay, Advance Payment.
- Event times are randomly spread over 2024-01-01 08:00 to 2024-12-31 22:00.

API: `POST /api/connections/generate-demo` with the connection test body plus `journeys` (default 500) and `dataset` (`retail` | `finance` | `transportation`, default `retail`).

Guarantees & limits:
- Journey count is **hard-capped at 20,000** server-side (a larger request is silently clamped) — the cap bounds insert time. Inserts run in batches of 200 journeys' rows per INSERT.
- Provisioning is included (schema + all five tables if missing).
- **Replacement scope:** only the dataset's own project is touched. PROJECTS row, METAS row, and **all JOURNEYS rows of that project (including any samples)** are deleted and re-inserted. **STEPS rows are only added if missing**, so operator customizations (colors, shapes, scores from the Step editor) survive a regeneration.
- Success message: `Created N journeys for "<title>" in <SCHEMA>.JOURNEYS` (green). Errors (red): "Unknown demo dataset '<x>'." / "A schema name is required." / "Enter how many journeys to generate." (count < 1) / the friendly connection error / fallback "Could not generate demo content."
- After generation the caller's STEPS cache is invalidated so a reload re-reads.
- **Gotcha:** generated data does NOT rebuild TRANSITIONS_RAW; with the materialized flag on, the map shows "⚠ Live (not built)" until a rebuild runs.

---

## 7. Project listing & deletion (per connection)

Available in both the admin panel (connection editor → "Projects" inner tab) and the main app (connection editor sheet → "Projects" tab, saved connections only; the tab is absent for a new unsaved connection; admin panel shows "Save the connection first to list its projects.").

**Listing** — "Projects in this schema" / caption: "Projects stored in <schema>, with their journey and event counts." Uses the stored connection credentials. Counts consider **ORIGINAL data only** (samples excluded): journeys = distinct EVENT_IDs, events = rows. A project appears if it exists in **either** PROJECTS or JOURNEYS (so orphans on either side are visible); a missing table is tolerated (before provisioning, an empty list rather than an error). Untitled projects display their PROJECT_ID as the title. Buttons "↻ Refresh"; states "Loading projects…", "No projects found in this schema.", red error text otherwise ("Could not read the projects for this connection." fallback in the SPA / "Could not read projects." in admin).

**Deletion** — button "Delete" per row; confirmations:
- Admin: `Delete project "<id>"? This clears its rows from PROJECTS, JOURNEYS, STEPS, METAS, NOTES and TRANSITIONS_RAW in this schema. This cannot be undone.`
- SPA sheet: title "Delete project?", message `"<title>" (N journeys, M events) will be cleared from PROJECTS, JOURNEYS, STEPS, METAS, NOTES and TRANSITIONS_RAW in this schema. This cannot be undone.`, confirm button "Delete project" (destructive style).

Exact behavior:
- Tables cleared, in this order (children before PROJECTS): **JOURNEYS, STEPS, METAS, NOTES, TRANSITIONS_RAW, PROJECTS** — every `DELETE … WHERE PROJECT_ID = '<id>'`. Absent tables (NOTES may not exist yet, TRANSITIONS_RAW is optional) are **skipped, not errors**; the response's `tables` array lists what was actually cleared. Sample rows are deleted too (no SAMPLE_SET filter).
- The response reports the project's pre-deletion ORIGINAL counts (`events`, `journeys`); the admin toast reads "Project deleted (N events)".
- Requires manager role AND ownership/administration of that specific connection (403 "You cannot manage this connection." / 404 "Connection not found."). Blank inputs: "A schema name is required." / "A project id is required."
- Every deletion is logged as a warning under operation `connection` ("<user> deleted project '<id>' from connection '<name>' (<conn-id>) — ok/failed: …"). The caller's STEPS cache is dropped.
- **Warning for the manual:** deletion is permanent — there is no undo, no backup, and it also erases all notes attached to the project.

---

## 8. LLM reachability probe + SSRF guard

Each connection may carry an optional LLM section ("LLM (optional)": "Server URL" — placeholders `https://…` (SPA) / `https://api.openai.com/v1` (admin) —, "Model" (admin placeholder `gpt-4o`), "API key").

**Probe** (`isLLMReachable`, run at connect and during tests): `GET <serverURL>/models` with `Authorization: Bearer <api key>` when a key is set; **5-second timeout**. Reachable unless the request errors or returns HTTP ≥ 500 (4xx counts as reachable — the server exists). No URL configured → simply not reachable (no error). Failures log the cause under operation `llm-test`; the user-visible test message is "LLM server not reachable."

**SSRF guard** (applies to the LLM URL, which is user-supplied):
- Only `http://` and `https://` schemes ("Only http:// and https:// URLs are allowed."); a URL without a host is refused ("The URL has no host.").
- The host is resolved and **every** resolved address is checked; if any is disallowed the whole URL is refused: "The URL resolves to <reason> (<addr>); refused." Always blocked: link-local/cloud-metadata (169.254.169.254), multicast, reserved, unspecified addresses (IPv4-mapped IPv6 unwrapped first). Unresolvable host: "The host could not be resolved: <host>".
- **Loopback and private (RFC1918) targets are allowed by default** — local LLM servers (Ollama, LM Studio, internal vLLM) are a first-class use case. Hardened deployments set env `PMW_BLOCK_PRIVATE_LLM_HOSTS=1` to refuse them too ("a loopback address" / "a private address").
- The outbound connection is **pinned to the vetted IP** (DNS-rebinding cannot swap the target between check and connect; SNI/cert verification stays bound to the real hostname; IDN hostnames are canonicalized so the pin always applies) and **redirects are disabled** (a 3xx cannot bounce the client to an unvetted host).
- A guard refusal is not surfaced as an error to end users — the LLM just shows as unreachable; the reason is logged ("LLM server URL refused (SSRF guard): …", operation `llm-test`).

---

## 9. Timeouts (all of them)

| What | Value | Notes |
|---|---|---|
| Exasol connect (socket open/login) | 15 s | fixed; produces "Connection timed out. Verify the host address, port, and network connectivity." |
| Exasol socket (per statement transport) | 300 s | fixed |
| Heavy statistics queries (variants/routes, goodness) | **30 s** default, env `PMW_QUERY_TIMEOUT` | on timeout the variants query raises: "Statistics query timed out (30 s). Narrow your date range or filters and try again."; the goodness metric silently returns none. Timeouts are logged under operation `db-timeout`. |
| LLM reachability probe | 5 s | |
| Rebuild / provisioning / demo / project ops | no app-level timeout | bounded only by the 300 s socket timeout per statement; the UI warns a rebuild "may take a while". |
| Rebuild token throttle | 60 s per connection | token callers only; 429 with retry seconds. |

Row-count guards (not time): variant/route listings hard-capped at 10,000 rows (default request 500), event-ID autocomplete at 100 (default 10).

Every executed SQL statement is logged verbatim with its execution time at DEBUG level under operation `sql` — persisted only when the admin raises the log level to DEBUG. SQL errors log the friendly message plus a 300-char one-line SQL excerpt under operation `db-sql`.

---

## 10. Cross-cutting gotchas & warnings worth printing

1. **Rebuild after every data load.** With "Use pre-materialized transitions" enabled, TRANSITIONS_RAW is a snapshot: reload JOURNEYS (ETL, demo generation, sampling) and the map either shows stale pairs (table still exists) or falls back to live ("⚠ Live (not built)") — schedule the token-authenticated rebuild call as the last ETL step.
2. **Editing a connection kicks its users.** Saving any change, changing assignments, or deleting a connection immediately disconnects every user currently using it; they must reconnect.
3. **Blank password in test/provision/demo forms.** Those operations use the typed password, not the stored one — retype it when working on a saved connection.
4. **DISTRIBUTE/PARTITION on pre-existing JOURNEYS tables** must be applied manually (see §1.2) — provisioning never alters existing tables.
5. **Minimum RSA key size** is stored but not enforced by the web backend (§4).
6. **"Accept any (insecure)"** disables both certificate and hostname verification — say so plainly.
7. **Project deletion and sample deletion are irreversible** — no recycle bin; notes go with the project.
8. **Demo regeneration replaces the demo project's journeys AND its samples** but keeps customized STEPS rows.
9. **Sample sets multiply storage** — each sample physically copies its journeys' event rows inside JOURNEYS.
10. **ORIGINAL vs NULL:** anywhere counts differ from expectations, remember NULL SAMPLE_SET rows count as ORIGINAL.
11. **Default port 8563** everywhere a port field appears; schema field is optional for connecting but required for provisioning/demo/projects operations.
12. **20,000-journey cap** on demo generation is silent — a request for more yields exactly 20,000.
13. The rebuild endpoint lives on the **admin service's** port (default HTTP 8090 / HTTPS 8453; env `PMW_ADMIN_PORT` / `PMW_ADMIN_HTTPS_PORT`), not the app's.
14. Rebuild token security properties for the ops chapter: per-connection scope, hash-only storage (unrecoverable — rotate if lost), constant-time verification, 60 s rate limit, single-flight per connection, all uses logged.