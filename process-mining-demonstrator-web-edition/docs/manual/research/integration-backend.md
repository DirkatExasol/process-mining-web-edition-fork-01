# Integration Backend — Documentation Notes (verbatim behaviour from code)

Source files: `/Users/dirk/Work/Process_Mining_Web/backend/app/api/integration.py`, `/Users/dirk/Work/Process_Mining_Web/backend/app/integration/{contract,backends,layer,status,extractors,files,watchdog,compound,destinations,parsing}.py`, plus `/Users/dirk/Work/Process_Mining_Web/backend/app/config.py` and `/Users/dirk/Work/Process_Mining_Web/backend/app/store/security.py` for defaults and persistence.

---

## 1. Access control: the router-level Developer gate

- Every integration API endpoint lives under the prefix `/api/integration` on the **shared compute backend** (not on the integration console's own port). The console reaches it through its `/api` proxy; the main app also proxies `/api/*`, which is exactly why the gate exists server-side.
- The signed-in user arrives in the trusted `X-PMW-User` header injected by the proxy (header name lower-cased internally as `x-pmw-user`). Whitespace-only or absent header = "no user".
- The gate is a **router-level dependency**, so it automatically covers every endpoint in this router, including any added later.
- Gate logic, in order:
  1. **No user header present** → the whole deployment runs without sign-in (single-user/dev mode) → the surface is **open** (no restriction), matching the other routers.
  2. If the admin has switched the integration surface **off** (the admin "integration enabled" switch, stored config key; default is **on**) → HTTP **403** with detail: `The integration console is turned off.` Disabling the console therefore also disables its entire API.
  3. Otherwise the user must exist, be enabled, and hold the **Developer** or **admin** role → else HTTP **403** with detail: `You need the Developer role to use the integration features.`
- **Power users are deliberately refused** — both at console sign-in (port 8100) and here at the API. A plain or power user cannot drive the data-source surface through the main app's proxy; this endpoint-level check is the proxy-bypass protection.
- Integration console ports (context): HTTP `PMW_INTEGRATION_PORT` (default admin port + 10 → **8100**), HTTPS `PMW_INTEGRATION_HTTPS_PORT` (default **8463**), host `PMW_INTEGRATION_HOST` (defaults to the admin host, `127.0.0.1`). Follows the shared TLS plan of app + admin.

---

## 2. Sandboxed file access (File sources)

All file reads — preview, full import, delta import, watchdog polls — funnel through one resolver. There is no other path from a user-supplied string to an open file.

### 2.1 Environment variables and defaults
- `PMW_INTEGRATION_FILES_DIR` — the sandbox root. Default: `<data dir>/integration_files`, where the data dir is `PMW_DATA_DIR` or `<project root>/data`. The directory is auto-created on startup (parents included). In Docker this is a mounted volume.
- `PMW_INTEGRATION_ALLOW_ANY_PATH` — opt-out of the sandbox. Truthy values: `1`, `true`, `yes`, `on` (case-insensitive, trimmed). Default **off**. When on, **any absolute path the server process can read is accepted** (`~` is expanded). WARNING for the manual: this is for developer-trusted deployments only — it enables reading arbitrary server files.

### 2.2 Path resolution rules (sandboxed mode, the default)
- A blank/whitespace path → error `No file path given.`
- Relative paths are taken **relative to the sandbox root**.
- Absolute paths are accepted **only if they already lie inside the sandbox root**.
- The *real* path is computed with symlinks fully resolved; the result must still be inside the (also symlink-resolved) root. Path traversal (`../…`) and symlink escapes are rejected with: `That path is outside the allowed sources directory.` (On Windows, a path on a different drive is likewise rejected.)
- After resolution: missing file → `File not found.`; anything that is not a regular file (directory, device, …) → `Not a regular file.`
- These errors surface as HTTP **400** from the preview and run endpoints, and as recorded checkpoint errors from the watchdog.

### 2.3 Demo seeding
- On compute-backend startup, every `*.log` file in `<project root>/examples/` is copied into the sandbox dir **if a file of that name is not already there** (never overwrites; best-effort — failures are silently ignored). This makes the bundled demo log work out of the box.

### 2.4 Read limits (apply everywhere)
- **Per-line cap: 2000 characters.** Every line handed to preview or extraction is truncated to its first 2000 characters. Trailing `\n`/`\r` are stripped first.
- **Blank lines are always skipped** (preview, extraction, delta reads, and the line count used for the progress bar).
- **Per-read byte cap: 8 MB (8 × 1024 × 1024 bytes).** One delta read (manual run or watchdog poll) reads at most 8 MB of new bytes. A bigger backlog (e.g. the first read of a huge existing file) is drained across successive reads/polls, cap by cap — `new_offset < size` signals more is pending. GOTCHA for the manual: a single manual delta run on a very large new file imports only the first ~8 MB; run again (or let the watchdog poll again) to continue.
- **Decoding:** the source's configured `encoding` (config key `encoding`, default `utf-8`) with undecodable bytes replaced (never an error). GOTCHA: the **preview** endpoint always decodes as UTF-8 (with replacement), regardless of the source's configured encoding.

### 2.5 Preview endpoint
- `POST /api/integration/sources/preview`, body `{ "path": string (≤4000 chars), "limit": int }`.
- Returns the first `limit` **non-blank** lines (each truncated to 2000 chars) plus `truncated: true|false` — `truncated` is true only if further non-blank content exists after the returned lines.
- `limit` default **5**, clamped to **1..50**. Invalid/0 → 5.
- Sandbox errors → HTTP 400 with the exact messages from §2.2.

---

## 3. Source types (extraction definitions)

Endpoints (all Developer-gated, all scoped to the signed-in user):
- `GET /api/integration/source-types` — the user's source types, each with `{id, owner, name, sample, fields, compound, createdAt}`.
- `POST /api/integration/source-types` — create. Body: `name` (1–120 chars, required), `sample` (≤20 000 chars), `fields` (list), `compound` (list, ≤200 rules).
- `PUT /api/integration/source-types/{id}` — update; **404** `Source type not found.` if not owned/absent.
- `DELETE /api/integration/source-types/{id}` — delete; **404** `Source type not found.` if not owned/absent.

Field object: `name` (1–60 chars, required), `role` (default `meta`), `regex` (≤2000 chars, default empty), `format` (≤120 chars, optional — stored only when non-empty), `title` (≤200 chars, optional — the human/business name for a meta field, becomes `METAS.META_n_TITLE`; stored only when non-empty after trimming).

Valid roles: `timestamp`, `id`, `step`, `meta`, `aux`. **Any unknown role silently falls back to `meta` on save.** `aux` fields are extracted like any other but are written to **no column** — they exist solely so compound-step rules can match on values (an HTTP status, a result code) that don't belong in META.

Compound rules on save: a rule is stored **only when complete** — a non-blank resulting `step` (≤500 chars) *and* at least one condition naming a field. Conditions with a blank field name are dropped. Unknown condition operators silently fall back to `eq`. This guarantees a half-built rule from the wizard can never relabel events at import time. Condition limits: `field` ≤60, `value` ≤500 chars.

---

## 4. Data sources

Endpoints:
- `GET /api/integration/sources` — the user's sources: `{id, owner, name, kind, config, createdAt}`.
- `POST /api/integration/sources` — create. Body: `name` (1–120, required), `kind` (default `file`, ≤40 chars), `config` (free-form dict).
- `PUT /api/integration/sources/{id}` — update; **404** `Source not found.`
- `DELETE /api/integration/sources/{id}` — delete; **404** `Source not found.`

Validation on create/update:
- Only kind `file` is accepted today. Unknown kind → **400** `Unknown source kind '<kind>'.`
- The serialised config must be ≤ **8000** characters → else **400** `Source settings are too large.`
- If the config contains a watchdog block with `enabled: true`, its `connectionId` must be non-blank **and assigned to the saving user**, else **400** `The watchdog's destination connection is not assigned to you.` (This is a fail-fast save-time check; the same authorisation is re-checked on **every** watchdog poll — see §10.)

Recognised config keys for a file source: `path` (the file to read), `encoding` (default `utf-8`), `sourceTypeId` (link to a source type — required to run), `transactionRows` (see §7), `watchdog` (`{enabled, intervalSecs, projectId, connectionId}`), and `lastRun` (written by the backend, see §8.4).

Update semantics worth documenting:
- `lastRun` is preserved across wizard saves automatically — renaming a source does not forget where it last imported to.
- **Changing the file path deletes the source's read checkpoint**, so the next import (manual or watchdog) re-reads the new file from the start.

---

## 5. The extraction pipeline (File extractor)

The built-in extractor id is `file` (name "File", version "1.0", description: "Reads a File source line by line and writes JOURNEYS events using the linked source type's regexes."). Runs are per-source configured instances; the registry entry is a descriptor only — attempting to run the registry entry raises `The File extractor is run per source, not from the registry.`

### 5.1 Regex application per field
- Regexes are compiled once per run. **Only the first field of each single-instance role is used** (`timestamp`, `id`, `step`); **up to three** `meta` fields map to META_1..META_3 in field order (a fourth+ meta field is ignored).
- A regex that fails to compile is treated as "never matches" (no error).
- Matching uses `search` (anywhere on the line). The extracted value is **capture group 1** if the pattern has groups, else the **whole match**.
- ReDoS protection: when the third-party `regex` module is installed, each match has a **0.25-second wall-clock timeout**; a timeout counts the line as unparseable (skipped). Rationale documented in code: CPython's `re` does not release the GIL, so an unbounded match would freeze the whole backend — including the watchdog loop. Without the `regex` module the stdlib `re` is used and no timeout applies.

### 5.2 Per-line result
A line yields a JOURNEYS event **only if all three of** case id, step and timestamp were captured *and* the timestamp normalises successfully. Otherwise the line counts as **skipped** (one skipped counter covers: no id, no step, no/unparseable timestamp, regex timeout).

Row written to `JOURNEYS`:
- `PROJECT_ID` — the run's project id (from the Run dialog or the watchdog config).
- `EVENT_ID` — the **hex MD5 digest of the raw captured id**. The raw case id (which may be a login/user id) is never written in the clear — pseudonymisation is unconditional and not configurable. GOTCHA: the same raw id always hashes to the same digest, so journeys still correlate, but you cannot recover the original id from the database.
- `STEP` — the captured step value, possibly replaced by a compound rule (§6).
- `STEP_ID` — always NULL.
- `EVENT_TIME` — a real TIMESTAMP, normalised to `YYYY-MM-DD HH:MM:SS` (see §5.3).
- `META_1`, `META_2`, `META_3` — the captured meta values (NULL where the regex didn't match or fewer meta fields exist).
- `SAMPLE_SET` — always the literal string `ORIGINAL`.

Events are pushed in batches of **500** rows; progress is reported every **200** processed lines; the denominator for the progress bar is a pre-pass count of the file's non-blank lines (whole-file mode) or the delta line count.

### 5.3 Timestamp normalisation
- Every captured timestamp value is analysed and normalised to the canonical shape `YYYY-MM-DD HH:MM:SS`. Runs of whitespace inside the value are collapsed first.
- Recognised: ISO-8601 (with fractional seconds, `Z` or `±HH:MM`/`±HHMM` offsets), `YYYY/MM/DD`, `YYYY.MM.DD`, day-first (`DD.MM.YYYY`, `DD/MM/YYYY`, `DD-MM-YYYY`) and month-first US dates (`MM/DD/YYYY`, `MM-DD-YYYY`), spelled-out/abbreviated month names ("03 Aug 2026", "Aug 3, 2026", …), 12-hour clocks with AM/PM, Apache/NCSA common-log (`03/Aug/2026:14:05:09 +0000`), RFC-2822 (`Mon, 03 Aug 2026 14:05:09 +0000`), C asctime, syslog (`Aug  3 14:05:09` — yearless: the **current UTC year** is filled in), and Unix epochs of exactly 10 digits (seconds), 13 (milliseconds) or 16 (microseconds), interpreted as UTC.
- Ambiguity policy: **day-first (European) is the default** for numeric `08/03` style dates; **month-first (US) is preferred when the time uses a 12-hour AM/PM clock** (a strong US-locale signal). ISO year-first is unambiguous and always tried first. A guard rejects 2-digit years mistakenly parsed as 4-digit years.
- An unparseable timestamp ⇒ the line is skipped, not an error.

### 5.4 Auto-created companion rows (create-if-missing)
After the events are pushed, the extractor ensures, in the target schema:
- **PROJECTS**: if the project id has no row, one is created with `TITLE` = the project id and empty `DESCRIPTION`. Log line: `created project '<id>'`.
- **METAS** (only when at least one meta field has a business `title` configured): the table is defined and a row `{PROJECT_ID, META_1_TITLE, META_2_TITLE, META_3_TITLE}` is created if the project has none. Existing rows are never updated — changing meta titles later does not rewrite an existing METAS row.
- **STEPS**: every step name seen in this run that has no `(PROJECT_ID, STEP)` row gets one, with: empty `DESCRIPTION`, a background colour picked **deterministically per step name** from a fixed 10-colour palette (CRC-32 based — the same step name always gets the same colour), foreground colour `#ffffff`, `SCORE` 0 (so auto steps show but don't skew scoring), a shape picked deterministically from `stadium` / `round` / `hex` / `circle` (independent seed, so shape and colour don't correlate), `END_OF_PROCESS` false, `BELONGS_TO` NULL. Log line: `created <n> new step(s): <names>`.

### 5.5 Result summary
The run's `detail` string is: `<n> events written, <m> skipped`, optionally extended with `, <k> new step(s)` and `, project created`. Tables reported touched: JOURNEYS, PROJECTS, STEPS, METAS. `records` = events written; `skipped` = unparseable lines — surfaced as its own KPI precisely so a silently-misconfigured source type shows as "lots skipped" rather than only as a small event count.

---

## 6. Compound steps (deriving STEP from several fields)

Motivation (worth stating in the manual): a log line often encodes the real activity across two fields — e.g. in an Apache log, `"POST /shop/login…" 200` is a *successful* login and `… 500` a *failed* one, while the path alone yields "login" for both.

Semantics:
- A source type may carry an ordered list of rules; each rule = a resulting step name + one or more conditions. **All conditions of a rule must hold (AND)**; rules are evaluated in order and the **first fully-matching rule wins**; if **no** rule matches, the plain `step` field's captured value is used unchanged — rules are strictly additive.
- A rule with zero (valid) conditions **never** matches.
- Condition operators: `eq`, `ne`, `contains`, `startswith`, `endswith`, `regex`. Anything else is treated as `eq`.
- Non-regex comparisons are **case-insensitive** and both sides are trimmed before comparing (log casing is rarely dependable). `regex` is the escape hatch for exact/complex patterns; it uses `search`, is subject to the same 0.25 s timeout (timeout ⇒ condition false), and an invalid pattern simply never matches.
- Available fields: **every named field of the source type** — including `aux` helper fields — is extracted per line and offered to the rules by name. A condition on a field that produced no value on that line is **false** (it does not error and `ne` does not treat "missing" as "different").
- Compound evaluation happens **after** the id/step/timestamp gate — a line still needs a plain step captured to produce an event at all; compound rules can only relabel it.
- The derived step participates in STEPS auto-creation like any other step name.

---

## 7. Transaction brackets (commit behaviour)

- Config key per source: `transactionRows` — "rows committed together".
- **Default: 5000.** Normalisation rules: a non-numeric value → the default 5000; **0 (or any value ≤ 0) → 0, meaning ONE transaction for the whole import** (fully atomic, but the database holds the entire import open); any other value is clamped to the range **1000 … 1 000 000**. (So e.g. 200 becomes 1000.)
- During a run, the session counts rows written since the last commit and **commits as soon as the bracket is full**. Benefits stated in code: keeps the database's transaction small on a large import and makes rows visible (durable) as the run progresses.
- After the extractor finishes, a **final commit** closes the last (possibly partial) bracket. The final commit is skipped when nothing was written since the previous commit *and* at least one commit already happened; the **very first commit always runs**, even with zero rows, to close the transaction any DDL/SELECT opened.
- **On failure the current (open) bracket is rolled back — but brackets already committed stay committed.** A failed run can therefore leave the rows of earlier brackets in the database; the status/detail shows how many were written. Combined with checkpoint semantics (§9: a failed run does *not* advance the checkpoint), this means a retry after a mid-run failure **can duplicate the rows of the committed brackets**. The manual should flag this explicitly and point at `transactionRows = 0` (single transaction) as the fully-atomic alternative.
- The number of committed brackets so far is surfaced in the status as `commits` ("durable progress").
- Physical writes: INSERT statements carry at most **1000** rows each; identifiers are strictly validated (letters/digits/underscore, not starting with a digit, ≤128 chars — anything else is rejected, never escaped); values are rendered as defensively-escaped literals (NULs stripped, quotes doubled; non-finite floats rejected). Portable column types map to Exasol as: string→`VARCHAR(2000000)`, int→`DECIMAL(18,0)`, decimal→`DECIMAL(36,6)`, timestamp→`TIMESTAMP`, bool→`BOOLEAN`. Tables are created with `CREATE TABLE IF NOT EXISTS`.
- For every run the destination connection's driver **autocommit is switched off** (both for a reused live session and for a freshly-opened stored connection), so the bracket — not the driver — decides when work becomes durable.

---

## 8. Running a source manually

`POST /api/integration/sources/{source_id}/run`
Body: `projectId` (required, 1–100 chars), `connectionId` (optional, ≤100 chars — the destination picked in the Run dialog), `delta` (boolean, **default true**).

### 8.1 Preconditions (in order, each → HTTP 400 unless noted)
1. Source not found / not owned → **404** `Source not found.`
2. Source kind not `file` → `Only file sources can be run yet.`
3. No file path configured → `This source has no file path.`
4. No linked source type (config `sourceTypeId` missing or not among the user's source types) → `Link a source type to this source first.`
5. Source type has no field with role `timestamp` → `The source type has no timestamp field.`

### 8.2 Destination resolution
- If `connectionId` is given:
  - The **assignment is the gate**, re-checked server-side (never trusted from the dropdown): if the connection is not assigned to the user, or does not exist → **404** `Connection not found.` (deliberately the same message for both, so a connection id alone reveals nothing). In no-sign-in deployments the assignment check always passes.
  - The connection's stored target schema must be non-blank → else **400** `“<connection name>” has no target schema configured.`
- If `connectionId` is empty (legacy clients): the signed-in session's **active** connection is used. Not connected → **400** `Pick a destination connection first.` Active connection has no schema → **400** `The active connection has no target schema.`
- Session reuse: when the browser session is currently connected to **exactly** this connection, the live session is reused (autocommit turned off; commits/rollbacks go through it). Otherwise the backend **opens its own connection with the connection's *stored* (admin-saved) credentials** — the same way the watchdog does — and **closes it again after the run** (also on failure). A destination that cannot be opened → **400** `Could not connect to “<name>”: <error>`. Naming the connection in the request is what allows a run without any session at all (remote push / scheduler, per the code's comment).

### 8.3 What is read (delta semantics for a manual run)
- Every manual run is checkpointed. `delta: true` (default) reads only what was **appended since this source's checkpoint** — re-running a source *tops it up* rather than duplicating everything. `delta: false` is the explicit "start over": it reads from byte 0 (ignoring the stored offset/signature) and **restarts** the imported-records counter; a delta run adds to it.
- Rotation/replacement detection applies exactly as for the watchdog (§9).
- Sandbox/read errors → **400** with the file-access message; an opened run-only connection is closed first.
- An empty file, or nothing appended since the checkpoint, is a **normal outcome, not an error**: the run still executes (so it shows in the pipeline/status) and simply writes no rows.
- After a **successful** run only, the checkpoint is advanced to the end of what was read (offset, size, signature), the records counter updated (`delta` adds, full restart resets), and `lastError` cleared. **A failed run leaves the checkpoint untouched**, so the next attempt re-reads those lines instead of skipping them.

### 8.4 Response and lastRun persistence
- Response JSON: `{ "records": <events written>, "detail": <string>, "linesRead": <int> }`.
  - When no lines were read, `detail` is replaced by exactly: `Nothing new to import — the file has not grown since the last import.` (delta run with an existing checkpoint) or `Nothing to import — the file is empty.` (otherwise).
  - `linesRead` exists to separate the two ways a run writes nothing: **no new lines at all** (normal for a delta run) versus **lines read but matching no regex** (a real misconfiguration — shows as `linesRead > 0`, `records 0`, everything skipped).
- On success, `{connectionId, projectId}` is stored into the source's config as `lastRun`, so the Run dialog reopens on the same destination next time. This is best-effort bookkeeping — a failure to store it never turns a successful import into an error (it is logged as a warning instead). Wizard saves carry `lastRun` forward (§4).
- Errors during extraction are surfaced as **400** — `FileAccessError`s verbatim, anything else as `Extraction failed: <error>` — and are also recorded in the user's layer status (`state: failed`, `lastError`).

### 8.5 Run/import log entries (admin log, tag `DATA`)
- Start: `import started: '<source>' (source type '<type>') → <connection or schema>/<schema> project <id> — delta|full, <n> line(s) to read` (usage level, operation `import`).
- Success: `import finished: '<source>' → <target> project <id> — <detail>`.
- Failure: `import failed: '<source>' → <target> project <id> — <error>` (error level).
- The abstraction layer additionally logs `extractor file pushed <n> rows to <schema>` (operation `integration`) on success and `extractor file failed: <error>` (warning) on failure.
- Individual SQL statements go through the normal SQL logging with tag `SQL` (debug level, with elapsed ms) when a live session is reused.

---

## 9. Checkpoints (delta bookkeeping)

One checkpoint per source, persisted in the security store (`source_checkpoints` table), **shared by both triggers**: a manual delta run and a watchdog poll advance the same offset — that is what keeps them from importing a line twice between them.

Checkpoint fields (as returned by the API): `byteOffset`, `size` (file size at last read), `signature`, `records` (cumulative imported events), `updatedAt` (ISO timestamp), `lastError` (string or null).

Mechanics:
- **Byte offset**: reading resumes at `byteOffset`. Only **complete** lines (up to the last newline) are consumed; a partial trailing line is left for the next read and the offset stops at the newline boundary. A single "line" longer than the whole 8 MB cap is deemed unparseable log content and is **skipped past** (offset jumps over it) rather than re-read forever.
- **Signature**: the MD5 of the file's **first 64 bytes** — a fixed prefix that does not change as the file grows by appends. Files shorter than 64 bytes get an empty signature (replacement then goes undetected; rotation is caught only by the size shrinking).
- **Truncation/rotation** (file shrank below the stored offset): detected by `size < offset` → reading restarts from byte 0.
- **Replacement** (rotation that reuses the file name): the head changed (stored signature non-empty and differs) while the size did **not** shrink and the offset is > 0 → the stored offset points into unrelated content, so the file is re-read from byte 0.
- Empty file / nothing appended: yields no lines and the current size/signature — never an error.
- **Advance-on-success only**: the checkpoint moves only after the run's rows are safely in; a failed run keeps offset/signature where they were (only `lastError` is updated by the watchdog). See the §7 warning about already-committed brackets.

Endpoints:
- `GET /api/integration/sources/{id}/checkpoint` — the checkpoint, or (if the source never imported) the literal zero object `{ "byteOffset": 0, "size": 0, "signature": "", "records": 0, "updatedAt": null, "lastError": null }`. **404** `Source not found.` if not owned.
- `POST /api/integration/sources/{id}/checkpoint/reset` — forgets the checkpoint so the next import (manual **or** watchdog) starts from the top of the file. Returns `{ "ok": true }`. **Manual must warn**: nothing is deleted from the database, so re-importing after a reset **appends the file's events a second time** unless the project is cleared first.
- The checkpoint is also deleted automatically when the source's file **path** changes on save (§4).

---

## 10. The file-source watchdog

A single background asyncio loop per compute-backend process, started in the app lifespan and cancelled on shutdown.

### 10.1 Deployment switches
- `PMW_INTEGRATION_WATCHDOG` — global on/off. Default **on** (`1`); truthy values `1/true/yes/on`. When off, the loop exits immediately: a source's "enabled" watchdog still never polls. The status endpoint surfaces this as `watchdogEnabled: false` so the console can say so instead of showing a count that quietly does nothing.
- `PMW_INTEGRATION_WATCHDOG_TICK` — base loop tick in seconds. Default **10**, hard minimum **5**. Every tick the loop lists **all sources of all owners** and considers each.

### 10.2 Per-source configuration (inside the source's `watchdog` config block)
- `enabled` (boolean) — the on/off switch per source.
- `intervalSecs` — per-source poll interval. Default **30**, hard minimum **5** (values below 5, or missing, are raised to the bounds). A source is "due" when it has never run, its checkpoint has no/invalid `updatedAt`, or at least `intervalSecs` have elapsed since the checkpoint was last touched. NOTE: because *every* checkpoint write updates `updatedAt` (including "nothing new" polls and manual runs), the interval effectively measures time since the last poll/import of any kind.
- `projectId` — the destination project id for watchdog imports.
- `connectionId` — the destination connection. Required for enabling (checked at save time, §4).
- The source's `transactionRows` applies to watchdog runs exactly as to manual runs (default 5000).

### 10.3 Headless authorisation model
- The loop runs with **no signed-in user and no active session**. It acts **as the source's owner** and opens the destination with the connection's **stored credentials** (the same mechanism the manual run and the admin rebuild job use). This is why the destination (connection id + project id) is stored *with* the source.
- On **every poll** — not just at save time — the owner must still be assigned to the destination connection. **Revoking the assignment stops the watchdog immediately** (next poll fails with the message below). Without this, any developer who learned a connection id could write into it with credentials they never had.

### 10.4 Poll outcome and error recording
Every failure is caught and recorded on the checkpoint's `lastError` (the offset does **not** advance) *and* logged as a warning in the admin log (tag `DATA`, operation `import`, username = the source's owner) — a watchdog runs unattended, so a silent failure would go unnoticed. One misconfigured source never stops the others or the loop. Exact recorded messages:
- `Watchdog is missing a file path, project id or connection.`
- `The source has no source type linked.`
- `The destination connection is not assigned to you.`
- `The watchdog's destination connection no longer exists.`
- `The destination connection has no target schema.`
- The file-access messages from §2.2 verbatim (e.g. `File not found.`).
- `Could not connect: <error>` (destination unreachable).
- `Import failed: <error>` (extraction/write failure).
Admin-log line for any of these: `watchdog import failed: '<source>' — <message>`.

Successful poll:
- Nothing new → the checkpoint is refreshed with the current size/signature and **any old error is cleared**; no run is started (so no pipeline entry).
- New lines → a normal layer run with `trigger: "watchdog"`; the freshly-opened connection is always closed afterwards; the checkpoint advances (records accumulate) and `lastError` clears. Admin log (usage, tag DATA): `watchdog imported <n> new event(s) from '<source>' into <connection>/<schema> (project <id>)`.
- Loop-level failures are also logged: `watchdog: could not list sources: <error>` and `watchdog: source '<name>' poll failed: <error>`.
- The watchdog run updates the **owner's** layer status exactly like a manual run does, so the console pipeline stays live regardless of trigger — and, because there is **one concurrent run per user**, a watchdog import and a manual import for the same user cannot overlap (the later one fails with `An extraction is already running for this user.`; for the watchdog that surfaces as an `Import failed: …` checkpoint error and is retried next poll).

---

## 11. Status, KPIs and concurrency

### 11.1 `GET /api/integration/status`
Returns the signed-in user's layer status plus surface-level extras. Fields:
- `state` — `idle` (nothing has run yet), `running`, `completed`, `failed`.
- `trigger` — `manual` (a console Run) or `watchdog`; drives the console's manual-vs-watchdog KPI split.
- `extractorId` / `extractorName` — e.g. `file` / `File`.
- `sourceName`, `sourceTypeName`, `connectionId`, `connectionName`, `schema` — the run's origin/destination, recorded verbatim for the console's pipeline canvas.
- `recordsPushed` — **all** rows pushed (events **plus** project/step/meta rows), live during the run.
- `eventsWritten` / `eventsSkipped` — journey events produced vs. source lines that could not be parsed (set at completion; the skipped KPI makes a misconfigured source type visible).
- `commits` — transaction brackets committed so far (durable progress).
- `recordsDone` / `recordsTotal` — progress-bar counters (total 0 = unknown).
- `tablesTouched` — table names defined this run, in order of first touch.
- `startedAt` / `finishedAt` — UTC ISO-8601 (seconds precision); `finishedAt` null while running.
- `lastError` — the failure message of the last run (null otherwise).
- `messages` — the most recent progress log lines (at most **50** kept, older dropped). Typical lines: `reading <path> → <schema>.JOURNEYS (project <id>)`, `watchdog: <n> new line(s) from <path> → …`, `pushed <n> events, skipped <m> unparseable line(s)`, `created project '<id>'`, `created meta titles: …`, `created <n> new step(s): …`.
Extras merged in by the endpoint:
- `registeredExtractors` — count of registered extractors (currently 1: the File descriptor).
- `activeConnectionId`, `activeSchema`, `connected` — the signed-in session's active connection and its target schema (where an extraction would land by default). Best-effort probe; never errors.
- `watchdogsActive` / `watchdogsTotal` — the user's file sources with the watchdog switched on vs. all their file sources.
- `watchdogEnabled` — the deployment-wide `PMW_INTEGRATION_WATCHDOG` switch (see §10.1).

### 11.2 `GET /api/integration/extractors`
Lists registered extractors as `{id, name, version, description}`. Empty until the first ships; today it lists exactly the File extractor.

### 11.3 Concurrency
- **One concurrent extraction per user.** Starting a second while one runs raises `An extraction is already running for this user.` (manual run: HTTP 400 as `Extraction failed: …`). Different users can run concurrently.
- Status is per-user; a new run **resets all counters** of that user's status — the status always reflects the most recent (or in-flight) run only.

---

## 12. Destination projects listing

`GET /api/integration/connections/{conn_id}/projects` — the projects already stored in a destination connection's schema, so the Run dialog can offer a picker instead of asking the user to retype a project id.
- Gate: **assignment**, exactly as for running — deliberately *not* the manager-gated `/api/connections/{id}/projects` (a developer is normally only assigned a connection, never its manager, so that endpoint would refuse them). Unassigned or missing connection → **404** `Connection not found.`
- Opens the connection with its stored credentials and returns `{ "ok": bool, "error": string, "projects": [ { "projectId", "title", "journeys", "events" } ] }` — `journeys` = distinct EVENT_ID count and `events` = row count within the project's ORIGINAL data (`SAMPLE_SET`). Projects present in either PROJECTS or JOURNEYS are included, so a project shows even if one table lacks its row. A blank schema yields `ok: false`, error `A schema name is required.`

---

## 13. Wizard helper endpoints (example-log parsing)

All Developer-gated. These only *generate* patterns from built-in templates and literal text; the backend never compiles or runs a user regex here (that happens client-side), so they are not a ReDoS vector. Every generated regex has **exactly one capturing group** (= the value) and uses a syntax subset valid in both Python `re` and JavaScript `RegExp` (no named groups, no back-references), so the browser preview and the backend execute the identical pattern.

- `POST /api/integration/parse/detect` — body `{ "sample": string ≤20000 }`; returns `{ "fields": [ {name, role, regex, format?} ] }`. Suggests, in order: **timestamp** (first matching of the built-in patterns: ISO-8601, Apache/CLF, numeric slash dates, syslog, date-only, 13-digit then 10-digit epochs — plus an inferred `format` token when the matched value parses), **id** (UUID, then ≥16-char hex run, then a `id=`/`uuid:`/`guid`/`trace_id` key-value, then a standalone integer of ≥4 digits), **step** (token right after a log level TRACE/DEBUG/INFO/WARN/WARNING/ERROR/FATAL/CRITICAL; else a quoted phrase; else the first CamelCase-ish word that isn't a level), then **meta** fields from `key=value` / `key: value` pairs (quoted or unquoted values; key sanitised to lowercase `[a-z0-9_]`, ≤40 chars). Spans already claimed by an earlier field are never re-used; at most **12** fields are suggested. Best-effort — a field appears only when a confident pattern matched.
- `POST /api/integration/parse/segment` — body `{ "sample": ≤20000, "start": int, "end": int }`; generalises the highlighted span into `{ "regex", "value" }`. Generalisation: digit runs → `\d{n}` (or `\d+` for runs longer than 8), letter runs → `[A-Za-z]+`, whitespace runs → `\s+`, punctuation kept as escaped literals. When a non-space character immediately precedes the selection, up to 8 characters of that context are prepended as an escaped literal *outside* the group, anchoring the match. Errors → HTTP 400: `sample required` (null sample), `empty selection` (zero-length span after clamping).
- `POST /api/integration/parse/timestamp` — body `{ "value": string ≤200 }`; returns `{ "format", "normalized" }` — the inferred strptime token (or `epoch:s` / `epoch:ms` / `epoch:us`) and the value normalised to `YYYY-MM-DD HH:MM:SS`; **both empty strings when the value cannot be parsed**. The format is stored with the timestamp field so extraction later parses each value the same way.

---

## 14. Extractor API contract (for plug-in authors)

The stable programming surface lives in the integration package's contract module; extractors never touch the database directly.

- **ExtractorInfo** — the immutable identity: `id`, `name`, `version`, `description`. `id` must be globally unique and stable (it is the plug-in key) and must be a slug: lowercase letters, digits and single hyphens (pattern `^[a-z0-9]+(-[a-z0-9]+)*$`). Registering a non-slug id raises `Extractor id '<id>' must be a slug (a-z, 0-9, '-').`; a duplicate raises `An extractor with id '<id>' is already registered.`
- **Extractor** (protocol) — has an `info: ExtractorInfo` attribute and a `run(session) -> ExtractResult` method. `run` is **synchronous** — the layer executes it off the event loop in a worker thread — and should **push incrementally rather than buffer everything**. Raising any exception marks the run failed (recorded in the user's status, current bracket rolled back); returning an `ExtractResult` marks it completed. Extractors register with the layer at import time (plug-in style) and are selected by id; registered extractors appear in `GET /api/integration/extractors`.
- **IngestSession** — the ONLY handle an extractor gets to the target database, created per run and bound to the selected connection's target schema. Do not hold onto it after `run` returns. Methods:
  - `schema` (property) — the target schema every table is written to.
  - `define_table(table, columns, keys=())` — declare and create-if-absent the table. Idempotent, safe to call every run, and **must** be called for a table before `push` (else `Call define_table('<table>', ...) before push().`). `columns` maps column name → portable ColumnType; at least one column is required (`Table '<t>' must declare at least one column.`); `keys` names the business-key columns (informational for now). Table/column names must satisfy the strict identifier grammar (§7) or an IngestError `Invalid SQL identifier: …` is raised.
  - `push(table, rows) -> int` — append rows (each a mapping column → value) and return the count written. Missing columns become NULL; **unknown columns raise** `Unknown column(s) for <table>: <names>`. Values are coerced/escaped by the layer. Rows are streamed in internal batches of 1000, so a generator over a very large source is never fully buffered. Every push tallies into the user's live status (`recordsPushed`) and counts toward the transaction bracket.
  - `log(message)` — a progress line for the status panel (last 50 kept).
  - `progress(done, total=None)` — progress-bar counters; cheap to call frequently.
  - `existing_keys(table, key_columns) -> set of tuples` — the existing key tuples (values stringified, NULL → empty string), for create-if-missing of metadata rows (a project, step definitions). It reads **all** keys — use for small metadata tables, never fact tables.
- **ExtractResult** — returned from `run`; purely informational (the layer counts pushed rows itself): `records` (successful items — for the File extractor, journey events), `skipped` (source items that could not become a record — surfaced as the skipped KPI), `tables` (tuple of touched table names), `detail` (human-readable summary shown to the user).
- **ColumnType** — the portable types: `string`, `int`, `decimal`, `timestamp`, `bool`; the layer maps them to concrete database types (§7), keeping extractors database-agnostic.
- **IngestError** — raised by the layer for invalid ingest operations (unknown table, bad identifier, type mismatch); extractors may let it propagate — it is recorded as the run's failure.
- Two backends exist behind the session (extractors never see them): the SQL backend (production, Exasol) and an in-memory backend (dependency-free dev/test reference of the ingest semantics, which also records commits/rollbacks for tests).

---

## 15. Endpoint quick reference

| Method & path | Purpose | Notable errors |
|---|---|---|
| `GET /api/integration/status` | Layer status + KPIs + watchdog counts | — |
| `GET /api/integration/extractors` | Registered extractors | — |
| `GET/POST /api/integration/source-types`, `PUT/DELETE /api/integration/source-types/{id}` | Extraction definitions | 404 `Source type not found.` |
| `GET/POST /api/integration/sources`, `PUT/DELETE /api/integration/sources/{id}` | Data sources | 400 `Unknown source kind …` / `Source settings are too large.` / watchdog-assignment 400; 404 `Source not found.` |
| `POST /api/integration/sources/preview` | First N lines (sandboxed) | 400 sandbox messages (§2.2) |
| `GET /api/integration/sources/{id}/checkpoint` | Read checkpoint | 404 `Source not found.` |
| `POST /api/integration/sources/{id}/checkpoint/reset` | Forget checkpoint (next import from top; DB rows stay) | 404 `Source not found.` |
| `POST /api/integration/sources/{id}/run` | Manual import (delta by default) | §8.1/8.2 messages |
| `GET /api/integration/connections/{id}/projects` | Destination project picker (assignment-gated) | 404 `Connection not found.` |
| `POST /api/integration/parse/detect` / `parse/segment` / `parse/timestamp` | Wizard helpers | 400 `sample required` / `empty selection` |

All endpoints: Developer/admin only via the router gate (403 `The integration console is turned off.` / `You need the Developer role to use the integration features.`); open when the deployment runs without sign-in.

---

## 16. Gotchas & warnings checklist for the manual

1. **Retry-after-failure can duplicate rows** when `transactionRows` > 0: committed brackets stay, the checkpoint doesn't advance, the retry re-reads the same lines. Use `transactionRows: 0` for atomicity (at the cost of one long-open transaction).
2. **Checkpoint reset ≠ database cleanup** — re-import appends everything again.
3. **8 MB per read**: big backlogs import piecewise across runs/polls; `linesRead`/pending size make this visible.
4. **Lines are truncated at 2000 chars** — a regex targeting content beyond that never matches; an over-8 MB single line is skipped entirely.
5. **EVENT_ID is always MD5-hashed** — irreversible pseudonymisation, not optional.
6. **SAMPLE_SET is always `ORIGINAL`**, `STEP_ID` always NULL, only META_1..3 exist (a 4th meta field is silently unused).
7. **Files under 64 bytes cannot be fingerprinted** — in-place replacement without shrinking goes undetected there.
8. **Preview decodes UTF-8 regardless of the source's configured encoding.**
9. **Meta titles (METAS row) are create-once** — editing titles later doesn't update an existing row.
10. **Watchdog stops when the connection assignment is revoked** (per-poll re-check), and its errors land on the checkpoint's `lastError` plus the admin log (tag `DATA`).
11. **`PMW_INTEGRATION_WATCHDOG=0` overrides per-source "enabled"** — surfaced as `watchdogEnabled: false` in the status.
12. **One run per user at a time** — a manual run while the watchdog is importing (or vice versa) fails with `An extraction is already running for this user.` and, for the watchdog, is retried on the next poll.
13. **Day-first vs month-first**: numeric dates default to day-first; AM/PM flips to month-first. Users with US logs and 24-hour clocks should verify the inferred format in the wizard.
14. **Syslog timestamps get the current UTC year** — importing an old yearless log around New Year mis-years events.
15. Compound rules: first match wins, conditions AND, case-insensitive trimmed comparisons, missing field ⇒ condition false, no match ⇒ plain step; only complete rules are ever stored.