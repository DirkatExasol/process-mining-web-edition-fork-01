# Integration Console — Documentation Notes (UI end to end)

Source: `frontend/web/src/IntegrationApp.tsx`, `components/IntegrationConsole.tsx`, `IntegrationSidebar.tsx`, `IntegrationStatusPanel.tsx`, `IntegrationKpis.tsx`, `IntegrationPipeline.tsx`, `SourcesSection.tsx`, `SourceTypesSection.tsx`, `SourceWizard.tsx`, `SourceTypeWizard.tsx`, `RunSourceDialog.tsx`, `integration/sourceKinds.ts`, `integration/runHistory.ts`, `integration/useIntegrationStatus.ts`, `integration/regexHighlight.ts`; supporting behaviour verified in `backend/app/api/integration.py`, `backend/app/integration/{files,watchdog,extractors,backends}.py`, `components/{ConnectionEditor,AuthFooter,SectionHeader}.tsx`.

---

## 1. Access, sign-in, and roles

- The integration console is a **separate surface** ("fourth surface") served on its own port: by convention **admin port + 10** — HTTP **8100** / HTTPS **8463** with default ports (Docker maps +2000). Started by `run.sh` via `integration/launch.py`.
- **Sign-in is always required** on this surface, even if the deployment's global "require login" setting is off for the main app. The login screen is the shared `LoginView` with the subtitle **"Integration"** shown under the product logo. Forced two-factor enrolment (if the deployment mandates it) keeps the login screen up until enrolment completes, exactly like the main app.
- **Who may sign in / use it:** only users with the **Developer** role or the **Admin** role. Power users and plain users are refused (the server refuses the login and drops the session). Defence in depth:
  - The console server itself guards sign-in on port 8100.
  - Every `/api/integration/*` endpoint is additionally gated server-side (router-level dependency), because the main app proxies `/api/*` for any enabled user. Errors returned: HTTP 403 `"The integration console is turned off."` when the admin has disabled the integration surface, and HTTP 403 `"You need the Developer role to use the integration features."` for a user without Developer/Admin.
  - When sign-in is disabled deployment-wide (single-user/dev mode, no user header), the surface is open.
- **Mid-session role revocation**: if the role is revoked while signed in, the console shows a full-screen **"Access denied"** page: logo, heading "Access denied", text *"The integration console is available to developers and administrators only. Ask an administrator to grant you the Developer role."*, and a **"⏻ Sign out"** button.
- While the session check runs at startup the console shows a large spinner with the text **"Starting…"**.
- **Theme**: follows the shared per-user `app.theme` setting (light / dark / system). "System" tracks the OS scheme live. Until settings hydrate after sign-in, the OS scheme is used.
- After sign-in the console loads the per-user settings and the user's **assigned data-source connections**.

## 2. Overall layout

- Left: a **sidebar** (same visual language as the main app) containing, top to bottom:
  1. Brand header — logo, title **"Integration"**, caption **"Data-source configuration"**.
  2. Three collapsible **accordion sections** (at most one open at a time; clicking an open section's header closes it): **Connections**, **Sources**, **Source types**. Each header shows a chevron, the title, a count in parentheses when > 0, and trailing icon buttons.
  3. Pinned at the bottom: the shared **identity/auth footer** — row 1 "👤 <display name> (<role>)" where role is one of Admin / Power user / Developer / User; row 2 buttons **"🔒 Two-factor"** (if allowed), **"🔑 Passkeys"** (if allowed), and **"⏻ Sign out"**. Below it, the **theme bar** (light/dark/system switcher).
- Right (main pane), top to bottom:
  1. A toolbar with a single **"？"** Help button (top right; opens the same Help panel as the main app).
  2. The **Abstraction layer** status card (status pill, target line, KPI tiles, run log).
  3. The **"Ingestion pipeline"** header row.
  4. The live **pipeline flowchart** canvas.
- The main column is centred, max width 900 px.

## 3. Sidebar — Connections section

- Header: **"Connections"** + count. Trailing buttons:
  - **＋** (tooltip "New connection") — shown only to users who may manage connections: Power, Admin, or Developer role (on this surface that means Developers and Admins, since only they can sign in; the predicate is deliberately identical to the main app's). Opens the **New Connection** editor.
  - **↻** (tooltip "Refresh connections") — reloads the assigned-connections list.
- Body: the user's **assigned connections as clickable badges** (cards), sorted alphabetically by name. At most ~3 badges visible (each min-height 64 px, list max-height 216 px); scrolls beyond that.
  - Card contents: a **⛁** icon (green when connected, accent-blue otherwise), the connection **name** (or "(unnamed)"), the optional **comment**, a line **"Database: <host>:<port>"** ("(no host)" if empty), and, when an LLM is configured, **"LLM: <url>"** (or "(configured)").
  - **Clicking a badge connects** to that connection; clicking the active one **disconnects**. Selecting a different one disconnects the current first.
  - The active badge shows a **status dot**: green = "Connected", orange = "Not connected".
  - A **✎** "Edit connection" pencil appears on a badge **only if the signed-in user owns that connection** (it is in their *manageable* list). Being *assigned* a connection is not owning it — e.g. an admin-owned connection assigned to a developer stays **read-only** for the developer (no pencil). The pencil's click does not connect/disconnect (it stops event propagation) — it opens the Edit Connection editor.
- Empty state: for managers, *"No connections yet. Use ＋ above to create one and assign users."*; for non-managers, *"No connections assigned to you. Ask an administrator to grant access."* Any last connection error shows in red under the list.
- **Connection editor** (shared `ConnectionEditor` sheet, titled **"New Connection"** / **"Edit Connection"**, icon ⛁, wide):
  - Tabs: **"Database / LLM Details"**, **"Demo Content"**, and (editing only) **"Projects"**.
  - Details tab fields: Name (required — error "Name is required."), Comment, Host, Port (default 8563), Username, Schema, Password (write-only; placeholder "•••••• (unchanged)" when one is stored — leave blank to keep it), a **"Create schema & tables"** button (disabled until a Schema is entered; creates schema + PROJECTS/JOURNEYS/STEPS/METAS/NOTES tables; the helper text notes it needs a DB account with CREATE SCHEMA/CREATE TABLE rights, which only the DBA can grant), **"Use TLS"** checkbox with (when on) **Certificate mode** (options: "Verify (system trust store)" — default, "Pin fingerprint", "Accept any (insecure)"), **Fingerprint (SHA-256)** (placeholder "optional"), **Minimum RSA key size** (default 2048); **LLM (optional)**: Server URL (placeholder "https://…"), Model, API key (write-only, "•••••• (unchanged)" placeholder); **Assigned users**: checkbox list of assignable usernames (empty state "No users available.").
  - Footer: **Test** (result inline: green all OK / orange one component failed / red all failed; text like "Database OK · LLM OK (n models)" or the error messages), **Delete** (edit only; confirm sheet *"Delete connection?" — "“<name>” will be removed for all assigned users. This cannot be undone."*), **Cancel**, **Save**.
  - Demo Content tab: three generators (Retail "📚 Online Bookstore", Finance/Insurance "💶🪙 Online Credit Application", Transportation "✈️ Flight Booking & Management"), each with Schema + Journeys (default 500, 1–20000) + **Generate**.
  - Projects tab: lists projects in the connection's schema with journey/event counts, **↻ Refresh**, and per-project red **Delete** (confirm sheet: *"Delete project?" — "“<title>” (<n> journeys, <n> events) will be cleared from PROJECTS, JOURNEYS, STEPS, METAS, NOTES and TRANSITIONS_RAW in this schema. This cannot be undone."*).

## 4. Sidebar — Sources section

- Header: **"Sources"** + count; trailing **＋** "Add a source" opens the Source wizard.
- Body: source badges, at most ~3 visible (min-height 52 px each, list max-height 190 px, scrolls). Each badge:
  - Kind icon (📄 for File; fallback 🗂️), the source **name**; a **👁** eye after the name when the watchdog is enabled (tooltip "Watchdog on — auto-imports new lines").
  - Sub-line: kind label + " · " + config summary (for File: the path; "(no path)" if unset).
  - **▷ Run button** (File sources only; tooltip "Run extraction", or "Watchdog active — run an import now as well" when the watchdog is on; the ▷ is **green while a watchdog watches** the source — it is importing on its own — and accent-blue otherwise). Opens the Run dialog.
  - **✕ Delete button** (tooltip "Delete source") → confirm dialog: title "Delete source", message *"Delete the source “<name>”? This can’t be undone."*, confirm label "Delete source".
  - **Clicking anywhere else on the badge opens the edit wizard** (tooltip "Edit source").
- Empty state: *"No sources yet. Use ＋ to add one."* Errors from listing/deleting show in red above the list.

## 5. Sidebar — Source types section

- Header: **"Source types"** + count; trailing **＋** "Add a source type".
- Body: badges (max ~3 visible, scrolls; min-height 52 px, list max-height 190 px): 🧩 icon, the **name**, sub-line "<n> field(s)" or "no fields yet". Click = edit (tooltip "Edit source type"). **✕** delete → confirm dialog: title "Delete source type", message *"Delete the source type “<name>”? Sources that reference it will need a new one."*, confirm label "Delete source type".
- Empty state: *"No source types yet. Use ＋ to define one."*
- A source type = a name + a pasted sample line + an extraction spec (fields with regexes) + optional compound-step rules. Owned per user.

## 6. Source type wizard (sheet "New source type" / "Edit source type", icon 🧩)

3 steps; footer always shows **"Step N of 3"**, **Cancel**, **Back** (from step 2), **Next** (disabled on step 1 until a name is entered), and on step 3 **"Create source type"** / **"Save changes"** ("Saving…" while busy). Save re-validates the name (error "A name is required." returns you to step 1).

### Step 1 — Basics
- **Name** input (placeholder "e.g. Apache access log, App JSON log", autofocused).
- **"Paste an example log entry"** — a 7-row monospace textarea (placeholder `2026-08-03T14:05:09Z INFO OrderReceived case_id=abc-123 …`). One representative line is enough; the sample is stored with the source type.
- Hint text: *"On the next step you'll map each field yourself — highlight a segment and assign it, or type its regex. Every field is defined manually."* (There is no auto-detection in the flow; mapping is fully manual.)

### Step 2 — Field mapping
- **"Select a segment below, pick a tab, then map it"**: the sample line rendered in a monospace, selectable box with **live role-coloured highlights** — each field's regex matches are painted in that role's colour (as `<mark>` tint at 32 % alpha). Overlaps resolve first-come: fields earlier in the list claim their span first. If the sample is empty: *"Paste a sample on the previous step."*
- **Role tabs** (order): **Timestamp · Step · Id · Metas · Helper** — internally roles `timestamp, step, id, meta, aux`. Each tab shows a coloured dot and, when fields exist, a count "(n)". Role colours: Timestamp = accent blue, Id = purple (#bf5af2), Step = green, Meta = orange, Helper = teal. Role labels used elsewhere: `EVENT_TIME`, `EVENT_ID`, `STEP`, `Meta`, `Helper`.
- Buttons under the tabs:
  - **"🎯 Use selection"** (tinted in the active role's colour): takes the current text selection inside the sample box, asks the backend to derive a regex for that segment (`POST /api/integration/parse/segment`), and adds a field of the **active tab's role** with that regex. Error if nothing is selected: **"Select a piece of the sample above first."**
  - **"＋ Add field"**: adds a blank field of the active role (regex typed by hand).
- Empty tab state: *"No <role> yet — select a segment above and map it, or add a field."* (For Metas: "No meta fields yet …").
- **Field rows** (one per field of the active role, on a grey chip):
  - For **timestamp / step / id**: a fixed coloured role label (`EVENT_TIME`, `STEP`, `EVENT_ID`). For **meta / aux**: an editable **name** input (placeholder "field name" / "helper name"; helper names are teal; tooltip on helper names: "Compound rules reference a helper by this name").
  - A monospace **regex input** (placeholder "regex (one capture group = the value)"). Convention: capture group 1 is the value; without a group the whole match is the value.
  - Live match feedback line: green **"✓ matches: <value>"**, red **"⚠ invalid regex"**, grey **"• no match in the sample"**, or **"• enter a regex"** when empty. (Regex testing runs entirely client-side against the sample.)
  - **Timestamp analysis** (timestamp fields that match): the captured value is sent to `POST /api/integration/parse/timestamp`; the row shows green **"🕒 <YYYY-MM-DD HH:MM:SS>  ·  format <fmt>"** when recognised (the parse format is auto-stored on the field), or orange **"⚠ couldn’t recognise the date — stored as extracted"**.
  - **META business title** (meta fields only): a second input, placeholder *"Business name (e.g. Book ID) — shown in the app"* — becomes METAS.META_n_TITLE and is shown as the column note in the record preview.
  - **Remove**: a **✕** button — **replaced by a 🔒 lock** when the field is referenced by any compound rule. The lock is non-clickable (cursor not-allowed, orange) with tooltip: *"Used by N compound step rule(s) (<rule steps>). Remove the field from those rules first — deleting it now would stop them matching. Renaming is safe: the rules follow the new name."* An orange caption repeats: *"🔒 Used by N compound rule(s): <steps> — remove it there before deleting this field. Renaming is safe."* Deletion is also guarded in code so no path can orphan a rule.
  - **Cascade rename**: renaming a field that compound rules reference automatically rewrites every rule condition to the new name (rules reference fields **by name**), so nothing silently stops matching.
- Default field names: timestamp/step/id fields are named after their role; meta fields default to `meta_1`, `meta_2`, … and helper fields to `helper_1`, `helper_2`, … (skipping taken names).

### Compound steps (inside the **Step** tab only — they always produce a STEP value)
- Section header: **"Compound steps"** + "optional" (with count when > 0) + **"＋ Add rule"**.
- Explainer (when no rules): *"Build the step from more than one field when the log splits it — e.g. step “login” plus status “200” becomes “login successful”. Values needed only for matching can be extracted as helper fields, which are never written to the database, so your META columns stay free for business attributes."*
- Rules render as **badges** in a scrolling list — **about 3 visible** (min-height 52 px each, max-height 190 px), then scroll. Each badge shows:
  - Its **order number** (tooltip "Rule N — checked in this order" — order matters: **first fully-matching rule wins**).
  - The resulting **step** in green (or "(no step yet)").
  - The conditions summary: `field <op label> “value”` joined with " · " (or "no conditions yet").
  - A green **✓** when the rule matches the pasted sample line (tooltip "Matches the sample line").
  - **✕** "Remove rule".
  - Clicking the badge opens the **rule editor** sheet.
- Under the list, live evaluation against the sample: green *"✓ For the sample line the step becomes “<step>”."* or grey *"• No rule matches the sample line — the plain STEP value would be used."* Rules are additive: when none match, the plain step field's value is used.
- **"＋ Add rule"** creates a rule pre-seeded with **two** conditions (a compound step combines at least two fields); the first condition's field defaults to the plain step field's name.
- **Rule editor** (nested sheet "Compound step rule", icon ⚗️; footer shows live *"✓ matches the sample line"* / *"• does not match the sample line"* plus a **Done** button — edits apply immediately, Done just closes):
  - **"Step becomes"** input (green bold; placeholder "e.g. login successful").
  - **"Conditions — all must hold"**: each condition = a row labelled "when" (first) / "and" (rest), a **field dropdown** listing every named field (helper fields suffixed " (helper)"; empty option "(field)"), a **−** remove button (only when > 1 condition), then an **operator dropdown** and a **value** input (placeholder "value"). Next to the value, a live hint **"= <captured value>"** shows what that field captures from the sample (tooltip "What this field captures from the sample line").
  - **Operators** (stored id → on-screen label): `eq` → **is**, `ne` → **is not**, `contains` → **contains**, `startswith` → **starts with**, `endswith` → **ends with**, `regex` → **matches regex**. String comparisons are **case-insensitive** (and trimmed); `regex` uses the value as a pattern (an invalid pattern simply doesn't match). The frontend preview mirrors the backend evaluator exactly.
  - **"＋ Add condition"** appends another empty condition.
  - **"Add a helper field"** panel (in the rule editor): explainer *"Extract a value only needed for matching (an HTTP status, a result code). Helper fields are never written to the database, so your three META columns stay free for business attributes."* Inputs: name (placeholder "name, e.g. status"), regex (placeholder "regex with one capture group"), **Add** button (disabled until both are filled). Live regex feedback: green *"✓ captures “<value>” from the sample"*, orange *"⚠ invalid regex"* or *"• no match in the sample line"*. Adding a helper creates an `aux` field and automatically points the first empty condition at it (or appends a new condition).
- On save, only **complete** rules (a step text plus ≥1 condition with a field) are stored; incomplete ones are dropped (the backend drops them anyway).

### Example JOURNEYS record preview (steps 2 and 3, whenever ≥1 field exists)
- A one-row table labelled **"Example JOURNEYS record"** showing exactly what the current spec would write for the sample line. Columns:
  - `PROJECT_ID` — "(set when the source runs)" (muted).
  - `EVENT_ID` — the extracted id value; column note **"original — stored as MD5"** (the id is MD5-hashed in JOURNEYS).
  - `STEP` — a matching compound rule's step **wins over** the plain step field (column note "compound" when it does).
  - `STEP_ID` — empty (muted; filled at load time).
  - `EVENT_TIME` — the **normalised** timestamp (backend-parsed) or, if unrecognised, the raw extracted value.
  - `META_1..META_3` — the first three meta fields in order; column note = the meta's business title (or name). Meta fields beyond three are not written.
  - `SAMPLE_SET` — "ORIGINAL" (muted).
  - Empty values render as "—".

### Step 3 — Review
- The highlighted sample ("Preview"), the name, a list of every field (role dot, role label, name, regex, and for timestamps "→ <format>"), a **"Compound steps"** summary (`<step> ← field is "value" and …`), and the Example JOURNEYS record again. Empty state: "No extraction fields defined."

## 7. Source wizard (sheet "New source" / "Edit source")

3 steps; footer "Step N of 3", Cancel, Back, Next (disabled on step 2 until a Name is entered), and on step 3 **"Create source"** / **"Save changes"**. Editing an existing source opens directly at step 2.

### Step 1 — "Choose a source kind"
- Cards for each kind; only **File** (📄, "A log or data file the extractor reads at run time.") is selectable today. Placeholders shown greyed with "· coming soon": **Database** (🗄️ "Rows from a database table or query."), **REST API** (🌐 "Records fetched from an HTTP endpoint."), **Object storage** (☁️ "Objects from an S3-compatible bucket."). The selected available kind shows a green dot.

### Step 2 — Configuration (File kind)
- **Name** (required; placeholder "e.g. File — access log"). A "Change kind" button appears only when more than one kind is available (currently never).
- Kind fields (required fields are starred `*` on their label):
  - **"File path or glob" \*** — text, placeholder `/var/log/app/access.log  or  /data/logs/*.log`, help *"Path (or glob) the extractor reads when the source runs."* ⚠️ Gotcha: despite the label, the backend currently resolves the path to a **single regular file** (errors: "No file path given.", "File not found.", "Not a regular file."); globs are not expanded. Also note the **sandbox**: by default paths are confined to `INTEGRATION_FILES_DIR` (a mounted volume in Docker) — an absolute path outside it is rejected with *"That path is outside the allowed sources directory."*; relative paths are taken relative to that directory. Setting `INTEGRATION_ALLOW_ANY_PATH` opts the deployment into any absolute path. Bundled example `.log` files are seeded into the sandbox on first use.
  - **"Encoding"** — select: `utf-8` (default), `latin-1`, `utf-16`.
  - **"Source type"** — dropdown of the user's source types, first option "— none —" (default). Help: *"The parser applied to each line when this source runs."* If none exist yet: *"No source types yet — define one in the Source types section first."*
- **Preview**: row "Preview first [N] lines" — N is a number input, default **5**, clamped 1–50. A live monospace preview of the file's first N **non-blank** lines (each truncated to 2000 chars), refreshed ~350 ms after the path or N changes; "…" is appended when more lines follow. States: *"Enter a file path to preview it."* (no path), *"No lines."* (empty file), or the backend error in red (e.g. "File not found.").
- **"⇄ Transaction bracket"** panel: a number input (default **5000**, min 0, step 1000) labelled **"rows per transaction"** — with **"(one transaction for the whole import)"** appended when 0. Explainer: *"Rows are inserted inside a transaction and committed once this many have been written. A larger bracket means fewer, bigger transactions — more atomic, but the database holds more open at once. A smaller one commits steadily, so a failure part-way leaves the already-committed rows in place. 0 imports everything in a single transaction: all-or-nothing. Applies to a manual run and to the watchdog."* (Backend clamps: invalid → 5000; ≤0 → 0; else between the batch size and 1,000,000.)
- **"👁 Watchdog — auto-import new lines when the file grows"** panel: a checkbox (default **off**) plus explainer: *"A background job watches this file and imports only the newly-appended lines into the destination below. A checkpoint is kept per file, so nothing is imported twice — even across restarts."* When enabled:
  - **"Destination connection \*"** — dropdown of the user's assigned connections ("— pick a connection —" default). If none: *"No connections are assigned to you — ask an administrator, or create one in the main app."*
  - **"Project id \*"** — text (placeholder "e.g. LIVE-LOG").
  - **"Every (seconds)"** — number, default **30**, minimum **5** (clamped in UI and backend).
  - **Checkpoint status** (editing an existing source only): red **"⚠ <last error>"**, or **"✓ <n> records imported · last checked <local date/time>"**, or *"Not run yet — the watchdog will pick it up shortly."* Beside it, **"↺ Reset checkpoint"** re-reads from the start on the next poll.
  - Save-time validation: **"The watchdog needs a destination connection and a project id."** (returns to step 2). Missing name → "A name is required."; missing required field → "<Label> is required."
  - Watchdog behaviour worth documenting: one background loop wakes every `INTEGRATION_WATCHDOG_TICK_SECS`; each enabled File source is polled when its interval has elapsed; only newly-appended **complete** lines beyond the checkpoint are read (max 8 MB per poll — a large backlog drains over successive polls); **rotation/truncation is detected** (size shrink, or head-signature change) and re-reads from byte 0; failures are recorded on the checkpoint (visible in the wizard and the Run dialog) and in the admin log, and the offset stays put so the next poll retries; the watchdog runs **as the source's owner** — the owner must (still) be assigned to the destination connection, checked on **every** poll, so revoking the assignment stops it immediately (error "The destination connection is not assigned to you."); other checkpoint errors include "The source has no source type linked.", "The watchdog's destination connection no longer exists.", "The destination connection has no target schema.", "Watchdog is missing a file path, project id or connection." A deployment-wide switch (`INTEGRATION_WATCHDOG_ENABLED`) can disable the whole loop — see the KPI tile behaviour below.

### Step 3 — Review
- Kind icon, the name (or "(unnamed)"), kind label, and each config field as label → value (monospace; passwords masked "••••••"; a linked source type shows its **name**, or "(unknown)"; empty values "—").

## 8. Run dialog (sheet "Run “<source name>”", icon ▷)

Opened by the ▷ button on a File source badge. The backend opens the chosen destination **itself with its stored credentials** — you do **not** need to be connected to it in the main app first.

- **"Destination connection"** dropdown ("— pick a connection —" + every assigned connection). Preselection order: the connection this source **last imported to** (remembered server-side per source; dropped if the assignment was revoked) → the main app's currently active connection → the first assigned connection. Below it, the target summary: **"<host>:<port> — writes into schema <schema>"** ("(none set)" if the connection has no schema).
- If no connections are assigned: warning banner *"No connections are assigned to you — ask an administrator, or create one in the main app."*
- If the source has **no source type linked**: warning banner *"This source has no source type linked — edit it and pick one so the lines can be parsed."* — and **"▷ Run extraction" is disabled**.
- **"Project"** dropdown: first option **"＋ New project…"**, then the projects already in the destination schema, rendered as `<projectId> — <title>` (title only when different). Loading the list opens the database on demand; while loading: *"Reading the projects in that schema…"*. On failure: orange *"Could not list existing projects (<error>) — you can still type a new project id below."* If the schema has none: *"That schema has no projects yet — this import creates the first one."* (A reachable schema without a PROJECTS table is treated as an empty list, not an error.)
  - The remembered last project is preselected **only** on the same connection it was imported into; if it no longer exists there, its id is kept in the New-project field rather than silently dropped.
- **"New project id"** input (shown when "＋ New project…" is selected; placeholder "e.g. RETAIL-DEMO"; help *"Written into JOURNEYS.PROJECT_ID for every event. The PROJECTS row is created for you."*).
- Selecting an **existing** project shows a warning banner: *"Events are **appended** to “<id>” (<n> already stored)"* followed by — delta on: *"— with delta upload on, only lines added since the last import are read, so nothing is stored twice."*; delta off: *"— the whole file is read again, so everything already imported is stored a second time. To reload from scratch, delete the project first."*
- **"⏩ Delta upload — import only what was appended since the last import"** checkbox, **default ON**. Help text — on: *"A checkpoint records how far this file has been read, so running again picks up only the new lines — no duplicates. Switch off to read the whole file from the top again."*; off: *"The whole file will be read from the top. Everything already imported into this project is stored a second time."*
- **Checkpoint panel** (always shown): red **"⚠ <last error>"**, or **"✓ <n> records imported · read to <bytes> of <bytes> bytes · last <local date/time>"**, or *"No checkpoint yet — this is the first import of this file."* Plus **"↺ Reset checkpoint"** (disabled while running or when no checkpoint exists; tooltip "Forget how far the file has been read, so the next import starts from the top").
  - One checkpoint per source, **shared** by manual delta runs and the watchdog. The checkpoint advances only after rows are safely committed — a failed run leaves it in place so the next attempt re-reads those lines. A full (non-delta) run resets the record counter; a delta run adds to it.
- Validation errors on Run: **"Pick a destination connection."**, **"A project id is required."**
- **Progress**: while running, a progress bar (determinate once totals are known, otherwise an animated indeterminate bar) with **"Importing <done> / <total> log records…"** or **"Reading the file…"**. Progress is polled from the live status every 350 ms. The same progress also appears on the pipeline's Abstraction-layer node.
- Footer: **Cancel** (becomes **Close** after a result), **"▷ Run extraction"** ("Running…" while busy; disabled without a connection or a linked source type).
- **Result states** (the Run button disappears; Close remains):
  - **Success** (records > 0): green **"✓ <detail>"** — detail is backend-built, e.g. `"12,340 events written, 3 skipped, 5 new step(s), project created"`.
  - **Nothing new** (0 records because **no lines were read**): neutral grey **"— <detail>"** where detail is *"Nothing new to import — the file has not grown since the last import."* (delta with an existing checkpoint) or *"Nothing to import — the file is empty."* This is the **expected** outcome of a delta run with no new data — deliberately not styled as a problem.
  - **No line matched** (lines were read but 0 events written): warning banner **"⚠ <detail>. No line matched — check the linked source type's regexes fit this file's format (edit the source type and test against a sample line)."** — a real misconfiguration signal. (The `linesRead` field distinguishes the two zero-record cases.)
  - Failures (bad path, bad connection — e.g. "Could not connect to “<name>”: …", "Extraction failed: …") show as red error text.
- Gotchas: unparseable lines are **skipped and counted** (shown in the detail and the "Events skipped" KPI); regexes are run with a timeout server-side, and a catastrophically-backtracking regex simply causes lines to be skipped; blank lines are always ignored; each line is capped at 2000 characters.

## 9. Status panel ("Abstraction layer" card)

Driven by a single poll of `/api/integration/status` every **1.5 s** (re-polls immediately when the active connection changes).

- Title **"Abstraction layer"** with a **state pill** at the right: ● **Idle** (grey), **Running** (accent blue), **Completed** (green), **Failed** (red).
- Target line under the title (where an import would land): **"Target `<schema>` · <connection name>"**; or *"The active connection has no target schema"* (connected, schema missing); or *"Pick a connection on the left to choose the target"* (not connected).
- Warning banners: the poll error (if the status endpoint is unreachable) and **"Last run failed: <error>"** when the most recent run failed.
- The **KPI strip** (see §10).
- **Run log**: when the latest run produced log messages, a toggle button **"▸/▾ Run log (<n>)"** expands a scrollable monospace list of the run's messages (e.g. "reading /path → SCHEMA.JOURNEYS (project X)", "pushed 500 events, skipped 2 unparseable line(s)", "created project 'X'", "watchdog: 14 new line(s) from …").

## 10. Ingestion KPIs (six tiles)

Same visual tiles as the main app's KPI strip; they wrap on narrow windows. **All counts except the watchdog tile are computed from the persisted run history** ("behaviour over time") and therefore reset with the ↺ Clear button — not with a backend restart.

1. **"Manual imports"** (▷) — number of recorded runs triggered manually.
2. **"Watchdog imports"** (👁) — number of recorded runs triggered by the watchdog.
3. **"Watchdogs active"** (🐕) — live "<active> / <total>": file sources with the watchdog switched on, out of all file sources. Green when ≥1 is active. When the deployment-wide watchdog loop is disabled the label changes to **"Watchdogs (off)"** and the tile turns orange — an "on" watchdog then never actually polls. "—" while no status has loaded.
4. **"Last import"** (🕒) — relative age of the newest run ("just now" <45 s, "Nm ago", "Nh ago", "Nd ago"; "—" when none); shows **"running…"** in accent colour while a run is in flight.
5. **"Events pushed"** (▦, green) — total journey events written across the recorded history.
6. **"Events skipped"** (⊘) — total unparseable source lines across the history; **orange when > 0** (skipped events usually mean the source type's regexes don't fit the log).

Missing fields from an older backend are tolerated as 0 rather than crashing the console.

## 11. Run history (feeds the pipeline + KPIs)

- The live status only reflects the most recent run, so the console **accumulates each run** into a persisted list: stored in browser localStorage **per user** (`pmw.integration.runHistory.<user>`), surviving reloads and even backend restarts. Capped at **50 runs** (oldest dropped; the header then shows "50+ runs").
- Any run that has actually started is recorded — **manual, watchdog, or API-push** — and the in-flight entry updates in place as the poll progresses.
- Header row above the canvas: **"Ingestion pipeline"** + caption *"no imports yet"* or *"<n>[+] run(s) · behaviour over time"* + (when runs exist) an **"↺ Clear"** button (tooltip "Clear the ingestion history") → confirm dialog: title **"Clear ingestion history"**, message *"Reset the pipeline flowchart, removing all <n> recorded run(s)? This only clears the console view — nothing already imported is affected."*, confirm label **"Clear history"**.

## 12. Live pipeline flowchart

One ReactFlow canvas showing the whole ingestion behaviour as a single accumulating graph:

```
[Source type] ──▶ [Source] ──▶ [Abstraction layer] ──▶ [Connection]
```

- **Nodes are reused across runs**: one node per distinct source-type name, source name, and destination connection name; the **Abstraction layer** is the single hub. Edges connect whatever combinations have actually run — many sources/types/destinations fan in and out.
- **Node cards** (210×112 px, four columns): a kicker line (SOURCE TYPE / SOURCE / ABSTRACTION LAYER / CONNECTION), an icon (🧩 / 🗂️ / ⚙️ / 🛢️), the name, and a subtitle — "extraction spec" on type nodes, "imported & extracted" on source nodes, "schema <schema>" (or "destination database") on connection nodes.
- **Pastel styling**: each node is tinted with a semi-transparent wash of its own accent colour (source type = purple, source = accent blue, layer = phase colour, connection = teal) — 14 % alpha in light mode, 20 % in dark, so the canvas dot-grid shows through; the running stage deepens to 24 %/30 % with an accent ring; completed nodes get a green-tinted border; failed nodes a red border; idle nodes render at reduced opacity.
- **Row counts**: Source and Connection nodes show **"▦ <n> rows imported"** — the cumulative total across all recorded runs touching that node.
- **Abstraction layer hub**: shows a progress bar + state label — "Running" with real progress (or an indeterminate animation before totals are known) while a run is live; otherwise **"<total> rows over <n> run(s)"**, or "Idle" when the history is empty.
- **Edge colours** reflect each edge's most recent run: green while running, red after a failure, blue otherwise. While a run is active, a **single animated dot travels the run's path** node-to-node in order (type → source → layer → connection, ~0.9 s per edge, looping).
- **Empty history**: a dim idle skeleton (generic "Source type" → "Source" → layer → the currently active connection or "(no connection)") keeps the pipeline's shape visible.
- **Interaction**:
  - Nodes are **draggable**; dragged positions are persisted per user (`pmw.integration.pipelineLayout.<user>`) and survive polls, reloads, and restarts. Panning by dragging the background; zoom limited 0.3–1.5 (scroll-zoom off); nodes are not connectable/selectable.
  - **Canvas resize**: a grip strip along the bottom edge (tooltip "Drag to resize the canvas") drags the canvas height between **520 px and 1400 px**; persisted per user (`pmw.integration.pipelineHeight.<user>`). The canvas also auto-grows with the number of node rows; a dragged height never shrinks below what the rows need.
  - **"⤢ Reset layout"** button (top-right, appears only once a manual layout or height exists; tooltip "Reset the node layout and canvas size to the automatic arrangement") clears both persisted layout and height.
  - **"↺ Clear"** (in the header, see §11) resets the graph itself.
- Note for admins/writers: because history, layout, and height live in the browser's localStorage per user, they are **per browser/profile** — a different machine shows its own history; disabled storage simply means nothing persists.

## 13. General gotchas & cross-references

- **Ownership vs assignment**: assigned connections can be *used* (connect, run into, watchdog destination); only **owned** connections can be *edited* (✎). Admin-owned connections assigned to a developer are read-only for them.
- **EVENT_ID hashing**: the extracted id is stored MD5-hashed in JOURNEYS (the wizard preview shows the original with the note "original — stored as MD5").
- Only the **first three meta fields** map to META_1..3; helper (aux) fields are never written to any column.
- The **plain STEP field remains the fallback** whenever no compound rule matches; rule order is significant (first match wins).
- Timestamp normalisation target is `YYYY-MM-DD HH:MM:SS`; unrecognised formats are stored as extracted.
- The transaction bracket applies to **both** manual runs and watchdog imports; the watchdog and manual delta runs share the **same checkpoint** per source.
- Deleting a source type does **not** cascade: sources referencing it keep a dangling link and their runs fail with the "no source type linked" warning until a new one is picked.
- The Run dialog and status panel reflect the same live status; a run started in the dialog also lights up the pipeline and updates the KPIs in real time.