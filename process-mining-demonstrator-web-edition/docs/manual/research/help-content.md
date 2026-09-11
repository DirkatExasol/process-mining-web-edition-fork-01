# In-App Help Content — Exhaustive Notes
Source: `/Users/dirk/Work/Process_Mining_Web/frontend/web/src/help/content.ts` (ported from the macOS `HelpView.swift`; block model: paragraph / tip / warning / bullets / definition / code / table). The help panel renders these 26 topics; TOC groups ten of them under an admin-only "Administration" sub-menu and three under a developer-only "Integration console" sub-menu (exact groupings listed at the end).

Legend used below: **TIP** = rendered as a tip callout in-app; **WARNING** = rendered as a warning callout.

---

## 1. Overview — 🏠 (audience: all users)
*Subtitle: "What Process Mining Demonstrator does and key concepts"*

### What is Process Mining Demonstrator?
- A process-mining tool that connects to an **Exasol** database and visualises how real cases flow through business processes.
- Reads a **JOURNEYS** table and renders every possible path between process steps as an interactive flow chart, with rich filtering, side-by-side comparison, and individual journey inspection.

### Workflow at a glance (steps in order)
1. Sign in, then open the sidebar **Connections** section — it lists the database connections an administrator has assigned to you.
2. Tap a connection to connect; the **Projects** section opens automatically.
3. Select a project — the **A-Chart** loads for the last 30 days of data.
4. Choose a chart view from the **☰ menu** in the top-right corner of the main area.
5. Adjust filters in the sidebar and tap **Apply** to refresh the map.
6. Each chart view remembers its own filter settings independently.

### Data model (definitions)
- **Journey / Case** — one end-to-end instance of a process, identified by `EVENT_ID`.
- **Step / Event** — a single activity within a journey, stored as a row in `JOURNEYS`.
- **Transition** — a chronologically consecutive pair of steps within the same journey.
- **Meta attributes** — up to three free-text columns (`META_1` – `META_3`) carrying case-level attributes such as department or customer segment.

### The ten views
- Open the **☰ menu** (top-right) to switch between: **A-Chart, B-Chart, A/B Comparison, Individual Journey, AI supported Documentation, Statistics, Conformance Check, Happy Path, Notes and Simulation**. A checkmark marks the active view, and the title capsule shows it on a second line so you always know your context.
- **TIP:** Conformance Check, Happy Path and Simulation are advanced-analysis views shown **only to Power users (and administrators)**. Plain users do not see them in the ☰ menu.
- **TIP (keyboard):** Press **⌘/ (or Ctrl+/)** at any time to open or close the Help panel. It floats, can be dragged by its title bar, and resized from the bottom-right corner.

---

## 2. Database Setup — 🗄 (audience: all users; practically admins/DBAs)
*Subtitle: "Table schemas and required permissions"*

### Required tables
- Reads from four tables — **PROJECTS, JOURNEYS, STEPS, METAS**. A **NOTES** table and the `JOURNEYS.SAMPLE_SET` column are created automatically on first use if the connecting user has the necessary rights. All table and column names are case-insensitive in Exasol.
- Full DDL shown in-app:

```sql
CREATE TABLE PROJECTS (
  PROJECT_ID  VARCHAR(100) NOT NULL PRIMARY KEY,
  TITLE       VARCHAR(200) NOT NULL,
  DESCRIPTION VARCHAR(500)
);

CREATE TABLE JOURNEYS (
  PROJECT_ID  VARCHAR(100) NOT NULL,
  EVENT_ID    VARCHAR(200) NOT NULL,   -- one journey = rows sharing an EVENT_ID
  STEP        VARCHAR(200) NOT NULL,   -- activity name → a node in the map
  STEP_ID     DECIMAL(18,0),           -- tie-breaker when EVENT_TIME is equal
  EVENT_TIME  TIMESTAMP    NOT NULL,   -- orders steps; drives date filters
  META_1      VARCHAR(500),
  META_2      VARCHAR(500),
  META_3      VARCHAR(500)
);

CREATE TABLE STEPS (
  PROJECT_ID     VARCHAR(100) NOT NULL,
  STEP           VARCHAR(200) NOT NULL,
  DESCRIPTION    VARCHAR(500),
  BG_COLOR       VARCHAR(50),          -- colour name or 6-digit hex (e.g. FF8000)
  FG_COLOR       VARCHAR(50),
  SCORE          DECIMAL(5,0),         -- −999…999, shown as a badge
  SHAPE          VARCHAR(20),          -- stadium | round | hex | circle
  END_OF_PROCESS DECIMAL(1,0) DEFAULT 0,
  BELONGS_TO     VARCHAR(200),         -- optional grouping label
  PRIMARY KEY (PROJECT_ID, STEP)
);

CREATE TABLE METAS (
  PROJECT_ID   VARCHAR(100) NOT NULL PRIMARY KEY,
  META_1_TITLE VARCHAR(200),
  META_2_TITLE VARCHAR(200),
  META_3_TITLE VARCHAR(200)
);
```

### Permissions & performance
- Required DB privileges:
  - **SELECT** on PROJECTS, JOURNEYS, STEPS, METAS — required for all read features.
  - **CREATE TABLE** — needed once so the NOTES table can be auto-created (Notes feature only).
  - **ALTER TABLE + INSERT on JOURNEYS** — needed for the Sampling feature (adds the `SAMPLE_SET` column and writes sample rows).
  - **UPDATE on STEPS** — needed for the in-app Step Editor.
- **TIP:** For best performance, index `JOURNEYS (PROJECT_ID, EVENT_TIME)` and `JOURNEYS (PROJECT_ID, EVENT_ID)`.
- No Exasol instance yet? The free **Community Edition** and the official **Docker image** both work. When using the Docker image or **Exasol 7.x**, set the connection's **minimum RSA key size to 1024 bits (legacy)**.

---

## 3. Connections — ⛁ (audience: all users; one section power-only)
*Subtitle: "Sign in, then pick a database connection assigned to you"*

### Signing in
- Unless an administrator has turned sign-in off, the application asks you to sign in. Use the username and password you were given — may be a **local account** or a **directory (LDAP / Active Directory)** account depending on setup.
- **Passkeys** — if the administrator enabled passkeys for your account, you can sign in with Touch ID, Windows Hello, or a hardware security key instead of a password. First sign in with your password, then open **🔑 Passkeys** (next to **Sign out**) and add a passkey for this device. After that, type your username on the login page and click **"Sign with Passkey"**. Your password always keeps working as a fallback, so you are never locked out.
- **Passkeys need a hostname** — passkeys are tied to a domain name, so they only work when you reach the app by a hostname (or "localhost" on the same machine) **over HTTPS** — not by a bare IP address. If you open the app by IP (e.g. from a tablet on the same network), the passkey buttons are hidden and enrolment is blocked; use the server's name instead, such as its ".local" name. Password sign-in works either way.
- **Two-factor (authenticator app)** — if enabled for your account, it's **required**: the first time you sign in, after your password you'll be asked to set it up right away — scan the QR with an authenticator app (Google Authenticator, 1Password, Authy…), enter the 6-digit code, and **save the recovery codes it shows** (each signs you in once if you lose your phone). After that, every sign-in asks for the current code following your password. Review your setup any time from **🔒 Two-factor** next to Sign out.
- **TIP:** App sign-in is completely separate from database credentials. You never type a database password into the app — those live only in the administrator's configuration.

### How connections work
- A connection bundles **one Exasol database server** with an **optional OpenAI-compatible LLM server**. Connections are defined by an administrator in the admin interface and assigned to individual users.
- The sidebar Connections section lists **only the connections assigned to you, as read-only cards** — you cannot change host, credentials or TLS settings here; that is the administrator's responsibility.
- Card contents:
  - **Database** — the Exasol host the connection points at, shown as "Database: host:port".
  - **LLM** — shown when a model server is attached; it enables the AI Documentation feature.
- **TIP:** Database passwords and LLM API keys are encrypted at rest and never sent to the browser — the app only receives host, port, schema and whether an LLM is attached.

### Connecting
- **Tap a connection card to connect; tap it again to disconnect.** Only one connection is active at a time. Disconnecting clears all loaded data — project, map, KPIs and filters all reset.
- Status dots on the active connection (up to two):
  - First dot = database state: **green** when connected, **orange** while connecting or after a failure.
  - Second dot (only if an LLM server is attached): **blue** when the model server is reachable, **orange** when not.
- **TIP:** Use the **↻ button** in the Connections header to refresh the list after an administrator has just granted you a new connection.

### Power users: manage your own connections (power/admin only)
- With the **power role**, a **＋ button** appears in the Connections header. Use it to create a connection — Exasol host, credentials, optional TLS and an optional LLM server — right from the app, and to tick the users it should be assigned to.
- You manage **only the connections you create**: an **✎ button** appears on those cards to edit or delete them and change assignees. Every new connection is automatically assigned to you, so you can connect immediately. Passwords/API keys are encrypted at rest and, once saved, never sent back to the browser — **leave those fields blank when editing to keep the stored secret unchanged**.
- The editor has **two tabs**:
  - **"Database / LLM Details"** — the connection fields; can also create a fresh process-mining schema: enter a schema name and the database credentials, then use **"Create schema & tables"** to build the schema and required tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don't already exist.
  - **"Demo Content"** — generates a ready-made dataset into the schema. Three offered:
    - **Retail**: 📚 "Online Bookstore" — synthetic order lifecycle with a returns flow and a flaky bank-transfer path.
    - **Finance/Insurance**: 💶 "Online Credit Application" — bank/affiliate intake, an application-check rework loop, credit assessment, and score- and sum-driven approval with agent-review loops, ending in payment or rejection.
    - **Transportation**: ✈️ "Flight Booking & Management" — Star Alliance-style login → search → select → book → pay → confirm; 50% of bookings are interline and query a partner airline; 20% only manage an existing booking.
    - For any of them: enter the schema and how many journeys, then **Generate**; creates schema/tables as needed and loads the journeys into that dataset's own project (others are left untouched).
- **WARNING:** Creating a schema or generating demo data needs a database account with **CREATE SCHEMA / CREATE TABLE** (and, for demo data, **INSERT**) rights. Only your database administrator can grant those — the application cannot authorise you.
- **TIP:** Use **Test** in the editor to check the database (and LLM, if set) before saving.

### Demo event-ID format
- In every demo dataset the stored `EVENT_ID` (the case key) is the **MD5 hash** of a synthetic reference: dataset prefix + 1-based zero-padded 6-digit sequence number. First journey = ORD-000001 / CRA-000001 / FLT-000001, second = ORD-000002 / etc.

```
Online Bookstore (BOOKSTORE):        EVENT_ID = md5("ORD-000001"), md5("ORD-000002"), …
Online Credit Application (CREDIT):  EVENT_ID = md5("CRA-000001"), md5("CRA-000002"), …
Flight Booking & Management (FLIGHTS): EVENT_ID = md5("FLT-000001"), md5("FLT-000002"), …

# reproduce a specific ID from a shell:
printf 'ORD-%06d' 1 | md5      # macOS  →  the stored 32-char hex EVENT_ID
printf 'FLT-%06d' 42 | md5sum  # Linux
```

- **TIP:** In the Individual Journey view you can type the friendly reference (e.g. `ORD-000001`) straight into the Event ID field — it is MD5-hashed for you — or paste a raw 32-character hash.

### No connections listed?
- An empty Connections list means no connection has been assigned to your account yet. Ask an administrator to grant access from the admin interface (**Database Connections** tab) — or, if you are a power user, create one with the ＋ button.

---

## 4. Users & Permissions — 🔑 (audience: all users; explains all roles)
*Subtitle: "The three roles and what each one can do"*

### The three roles
- Every signed-in account carries one of three permission levels. They build on each other (Power ⊇ Regular; Admin ⊇ Power). Roles are granted in the admin interface (Users tab); **by default a new account is a Regular user**.
- **Regular user** — explores the process: views maps and charts, applies filters and saved presets, reads and writes notes, adjusts their own KPIs, layout and personal settings. Works with the database connections an administrator (or Power user) has assigned to them.
- **Power user** — a Regular user who can also create, manage and assign their **own** database connections from within the app (manages only the connections they created), provision schemas, generate demo data, run journey sampling, and use the advanced-analysis views (Conformance Check, Happy Path, Simulation) — all without needing the separate admin interface.
- **Administrator** — full control. Everything a Power user can do over **every** connection, plus the admin interface (**:8090**): managing all users and roles, TLS certificates, the LDAP directory, licensing, logging, backups and login customization.
- **Developer (additional grant)** — an extra permission (the **Developer checkbox** in the admin Users tab), independent of the level above. Admits the account to the **Integration console** — a separate surface on the admin port + 10 (`http://…:8100`) for configuring the application's data sources. **Only developers and administrators may enter it (power users may not)**; a Regular user with only the Developer grant may enter the console but has no other elevated powers in the main app.
- **TIP:** The Integration console reuses the same sign-in (password, passkey, two-factor) and follows the same TLS mode as the app. An administrator can turn it off entirely under **Admin → Integration**.
- **TIP (important gotcha):** Roles require a signed-in identity. If an administrator turns off **"Require sign-in for the main application"** (the login gate, in the admin Users tab), the app runs with **no user identity** — so every Power/Admin-only capability is unavailable: the Sampling section and the advanced views (Conformance, Happy Path, Simulation) are hidden, and their APIs return **403**. To use those features, keep Require sign-in on and sign in with a Power or Admin account. **There is no way to have both no-login access and the power features at once.**

### Capability matrix (rendered as a table in-app)

| Capability | Regular | Power | Admin |
|---|---|---|---|
| View process maps, charts & KPIs | ✓ | ✓ | ✓ |
| Filters, saved presets & date window | ✓ | ✓ | ✓ |
| Read & write notes and comments | ✓ | ✓ | ✓ |
| Personal settings, layout & backup of preferences | ✓ | ✓ | ✓ |
| Advanced views: Conformance, Happy Path, Simulation | — | ✓ | ✓ |
| Journey sampling (create / delete samples) | — | ✓ | ✓ |
| Create, manage & assign own DB connections | — | ✓ | ✓ |
| Provision schema & generate demo data | — | ✓ | ✓ |
| Integration console (data-source configuration) | Developer only | ✓ | ✓ |
| Admin interface: all users, connections, TLS, LDAP, licensing, logging | — | — | ✓ |

- **TIP:** Journey sampling rewrites the **shared** sample sets for everyone on the connection, which is why it sits with the Power/Admin capabilities rather than being a personal, per-user action.

---

## 5. Admin Interface — ⚙︎ (audience: admin)
*Subtitle: "The separate administration interface for security and access"*

### Overview
- A separate administration interface runs on its own port (**8090 by default**), where all security and access is configured. It has its own sign-in and admits **administrators only**.
- On first run it **seeds a local administrator — username `Administrator` / password `Administrator`** — and prompts you to change the password. Local admin accounts always work as a **break-glass route**, even if a directory is later misconfigured.
- **TIP:** Admin interface tabs: **App Control** (restart the servers, manage the license), **TLS / SSL**, **Users**, **Database Connections**, **Directory (LDAP)**, **Logging**, **Backup**, **Customize**.

---

## 6. TLS / SSL — 🔒 (audience: admin)
*Subtitle: "HTTP/HTTPS mode and certificates"*

### Modes & certificates
- Three modes: **Off** (HTTP only), **Optional** (HTTP and HTTPS together), **Required** (HTTPS only). Generate a **self-signed certificate** or **upload your own PEM certificate and key**, then mark one **active**.
- Main app and admin interface both follow this **one mode** and share the **same active certificate** — app on ports **8080/8443**, admin on **8090/8453**. Changes take effect when the servers restart: the **↻ Restart app server** button in the App Control tab rebinds both in place. If a mode needs a certificate but none is active, each server **falls back to HTTP** so nothing (including the admin itself) is left unreachable.
- **WARNING:** Certificate private keys are encrypted at rest. Keep the active certificate valid — an expired certificate makes HTTPS clients refuse to connect.

---

## 7. Users & Sign-in (admin Users tab) — 👤 (audience: admin)
*Subtitle: "Accounts, roles and the login gate"*

### Accounts & roles
- The **Users tab** controls who may sign in to the main application: create local users, enable or disable access, grant or revoke the admin role, and reset local passwords. **Only enabled users can sign in.**
- **Require sign-in toggle** — turns the login gate on/off for the main app (**on by default**). With it off, the app is open to anyone who can reach it — and, since there is then no user identity, per-user settings and filter presets all fall back to **one shared profile**.
- **Failed sign-in lockout** — "Disable an account after N failed sign-in attempts" automatically disables an account once N wrong passwords are entered (**defaults to 3; set 0 to turn it off**). A locked account shows a clear message on the login panel and carries a **Locked badge** in the Users tab, where you can unlock it. The built-in Administrator is **exempt** from auto-lockout — as the sole recovery account it must not be lockable by someone who merely knows its name; it is protected by the per-IP throttle instead. (To clear all locks, restart the servers with **`PMW_RESET_LOCKOUTS=1`**.) Separately, the admin sign-in page throttles repeated failures from the same IP with a short, self-clearing cooldown (**HTTP 429**), so password guessing is slowed even when account lockout doesn't apply.
- **Power role** — **Make power / Remove power** grants the power badge. Power users can create and manage their own database connections from within the main app and assign them to other users — without needing the admin interface. They manage only the connections they create; admins still see and manage every connection. Power users (and admins) also get the advanced-analysis views — Conformance Check, Happy Path, Simulation — and journey sampling.
- **Source badge** — each user is tagged **local** or **LDAP**; the **All / Local / LDAP** filter narrows the list.

### Passkeys (WebAuthn)
- Passkeys let a user sign in with Touch ID, Windows Hello, or a hardware security key instead of a password. **An alternative, never a replacement** — the password (or directory sign-in) always remains as fallback.
- **Who may use a passkey** — the **Passkey column** in the Users tab gates this per account. The **header checkbox** is a master toggle for everyone at once. Both local and directory (LDAP) users can be allowed; a directory user enrols a local passkey that signs them in without contacting the directory.
- **Enrolling a device** — once allowed, a user adds a passkey from the main app (**🔑 Passkeys** button by Sign out) or, for administrators, from **App Control → Passkeys** in the admin. Enrolment requires being signed in first, so only the real account owner can register a device. **One passkey registered on this host works for both the main app and the admin interface.**
- **Signing in** — on the login page the user types their username and clicks **"Sign with Passkey"**. Turning off the Passkey permission blocks further passkey sign-ins immediately (existing passkeys stop working until re-enabled); deleting a user also removes their passkeys.
- **WARNING:** Passkeys need a **secure context** — HTTPS, or localhost for local testing. Off localhost, run the app with TLS set to Optional or Required. On a single host everything works out of the box; for split app/admin sub-domains, set **`PMW_PASSKEY_RP_ID`** to the shared parent domain and list the origins in **`PMW_PASSKEY_ORIGINS`**.
- **WARNING:** Passkeys also require a **real hostname**: WebAuthn rejects bare IP addresses (and single-label hosts). If users reach the app by IP (e.g. a tablet connecting to a Mac on the LAN), passkey enrolment fails with **"the effective domain is not a valid domain"**. Give the host a resolvable name (its ".local" Bonjour name, or a DNS entry) and issue the TLS certificate for that name. The app hides the passkey controls when it detects an IP.

### Two-factor authentication (TOTP)
- Adds a one-time code from an authenticator app (Google Authenticator, 1Password, Authy…) as a second step after the password. Optional and additive — the password still signs the user in — so it can't lock anyone out.
- **Who must use two-factor** — the **2FA column** in the Users tab enables it per account, with a master **"Allow two-factor for all users"** checkbox above the list. Enabling it makes 2FA **MANDATORY** for that user: if not yet configured, their next sign-in stops after the password and **forces enrolment** — they can't bypass it by simply not enrolling. Both local and directory users qualify; for a directory user it's a local second factor layered on their directory password. Turning the permission off removes the requirement.
- **Setting it up** — the user opens **🔒 Two-factor** (next to Sign out), scans the QR with their authenticator app and confirms one code. They then get **one-time recovery codes — shown once**. Administrators set up their own from **App Control → Two-factor**. The same secret protects both the app and the admin interface.
- **Signing in** — after the password, an enrolled user is asked for the current 6-digit code (or one recovery code). **A passkey sign-in skips the code step** (already strong authentication). Recovery codes can be regenerated at any time (invalidating the old set). Repeated wrong codes are rate-limited by source IP (short cooldown) but never disable the account.
- **Turning it off** — a user turning 2FA off must enter their current code (or a recovery code) first, so a stolen session can't silently remove it. If a user is locked out of both authenticator and recovery codes, an administrator **cannot read the secret** — untick 2FA for them in the Users tab so they can sign in with their password and enrol again.
- **TIP:** The secret is stored encrypted and recovery codes only as hashes; deleting a user removes both.

---

## 8. Database Connections (admin) — 🗄️ (audience: admin)
*Subtitle: "Define Exasol/LLM connections and assign them to users"*

### Defining connections
- Define each connection: Exasol **host, port, user, password, schema and TLS options**, plus an optional **OpenAI-compatible LLM server** — and assign to one or more users. Each user then sees only their assigned connections.
- **Test connection** verifies the database (and LLM) before saving. Leaving a password or API-key field blank on an existing connection keeps the stored value. **Secrets never leave the admin interface.**
- **"Create schema & tables"** provisions a fresh process-mining schema — creates the named schema and required tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if missing, using the credentials entered.
- **WARNING:** Needs a database account with **CREATE SCHEMA and CREATE TABLE** privileges — only grantable by the database administrator, not the application.

### Pre-materialized transitions (performance)
- Each connection can opt into reading the process map from a prebuilt **TRANSITIONS_RAW** table instead of computing directly-follows pairs live on every request — a large speed-up for interactive filtering on big event logs. **Off by default and fails safe**: until the table is built (or while a rebuild is in flight), the map falls back to the live query.
- Tick **"Use pre-materialized transitions"** on the connection (takes effect on the next chart reload — no reconnect needed), then rebuild the table after each load of JOURNEYS. Three rebuild routes:
  1. The **Rebuild now** button (shows last-built time and pair count).
  2. A scheduler calling **`POST /api/connections/<id>/rebuild-transitions`** with an `Authorization: Bearer` token (generate under **"Rebuild from a script (API)"** — shows a ready-to-copy curl example; token scoped to that connection, shown once, stored only as a hash).
  3. Ticking **"Also build …"** when you Create schema & tables.
- The active mode shows as a **pill on the process map**: **⚡ Pre-materialized** (reading the table), **↻ Live query** (not enabled), or **⚠ Live (not built)** — enabled but the table isn't ready, running live meanwhile; rebuild it. If a rebuild-enabled connection keeps showing "Live (not built)", the admin **Logging** tab records the exact cause under the **"materialize"** operation.
- **TIP:** Pays off when JOURNEYS changes in batches that are then explored heavily; less so for continuously-updated data (the table is stale until the next rebuild).

---

## 9. Rebuild from a script (API) — 🔌 (audience: admin / ops)
*Subtitle: "Trigger a per-connection rebuild from a scheduler"*

### Per-connection rebuild token
- Each connection can issue **its own bearer token** so an external caller — cron job or ETL step — can trigger that connection's pre-materialized transitions rebuild **without an admin login**. Open the connection in Database Connections, expand **"Rebuild from a script (API)"**, and **Generate / rotate** or **Revoke** the token there. Shown **once**, right after generation (copy it then); only its hash is stored; rotating or revoking invalidates the previous token immediately.
- **TIP:** The token is **scoped to its own connection** — cannot rebuild any other connection.

### Triggering the rebuild
- Call **`POST /api/connections/<id>/rebuild-transitions`** on the **admin server** with header **`Authorization: Bearer <token>`**. The admin section shows a ready-to-copy curl example (with copy button), pre-filled with the real token while still visible, and using the **`-k`** flag to skip the TLS certificate check for a self-signed admin certificate.
- Response: on success **`{"ok": true, "rows": N, "built_at": …}`**; on failure **`ok:false`** with an error string.
- Token-triggered rebuilds are **rate-limited per connection**, and a connection never runs two rebuilds at once — a leaked token cannot hammer the database. An admin using the **Rebuild now** button is not throttled.
- **TIP:** Run it right after each JOURNEYS load. The connection must have "Use pre-materialized transitions" enabled to benefit.

---

## 10. Directory (LDAP) — 📇 (audience: admin)
*Subtitle: "Directory sign-in via search + bind"*

### Directory sign-in
- When enabled, the main-app login also accepts directory accounts via **search + bind**: a read-only service account searches the base DN for the login name, then the app re-binds as that user with the supplied password.
- Configuration:
  - Server URI (**ldap:// or ldaps://**, with optional **StartTLS**), the service-account **bind DN and password**, the **base DN**, and the **user filter and attributes**.
  - **Test server connection** checks the server and service bind alone; **Test a user login** also resolves and signs in a directory account.
  - On first successful sign-in a directory user is created locally as a **plain, enabled account**, so you can assign connections and, if you wish, the admin role.
- While a directory is configured, the app's sign-in panel shows a small **status light** — **green** when the directory server answers a connection test, **red** when it does not. Hidden entirely when no directory is configured.
- By default the **admin interface stays local-only**. Tick **"Also allow directory sign-in to this admin interface"** to let directory accounts sign in there too — but only after one has been **promoted to admin in the Users tab**. Local administrators always work regardless (break-glass).
- **TIP:** Admin is never granted from the directory — a directory user stays a normal user until a local admin promotes them.

---

## 11. Logging — 🧾 (audience: admin)
*Subtitle: "The shared, structured application log"*

### The application log
- The Logging tab is a shared, structured application log written by **all three servers** (main app, admin interface, compute backend). Each entry records: **timestamp, severity, client IP, user, operation, optional tag, message**.
- **Severity is a cumulative ladder — INFO, USAGE, WARN, ERROR, DEBUG.** Pick the maximum level to record (cheaper levels always kept; **DEBUG only when explicitly selected**). Filter by severity, client IP, operation or tag; narrow with a **regular-expression search**; page through results; **Download** the current log or **Clear** it.
- **Tags** — where the operation says which code path wrote an entry, a tag groups an entire activity across operations and severities. Three tags ship today:
  - **SQL** — every entry quoting an executed database statement: the per-statement DEBUG trace plus error and timeout entries. Picking SQL in the tag filter gives the database traffic on its own, at whatever severity it occurred.
  - **BACKUP/RESTORE** — every export, inspect and restore, scheduled or manual, including failures — the whole custody trail of a backup file in one filter.
  - **DATA** — data imports: start and result of every import, whether triggered by hand in the integration console or by a file-source watchdog. Successful imports recorded at **USAGE**; a failure at **WARN or ERROR** with the reason.
- **Audited actions** — security/config-relevant actions carry a dedicated operation tag: sign-in/sign-out (**login / logout**), LDAP tests and config changes (**ldap**), certificate generate/upload/activate/delete (**tls**), database-connection create/edit/assign/delete plus connection and LLM-server tests (**connection / llm-test**), backup export/inspect/restore (**backup**), login-page customization (**customize**). **Deletions are recorded as warnings.**
- **TIP:** A fresh log file starts automatically once the live log passes the configured size (**"New file after N MB"**); rotated files are saved under **`data/logs/`**.

---

## 12. Customize — 🎨 (audience: admin)
*Subtitle: "Appearance — the login-page background"*

### Login page
- The Customize tab sets the **login-page background for both sign-in pages** — main app and admin interface. Options: keep the **default theme colour** (follows light/dark mode), choose a **solid colour**, or **upload a background image** (**PNG, JPEG, GIF, WebP or SVG, up to ~3 MB, scaled to cover**). A **live preview** shows the result before saving.
- Over a background image the login panel turns **semi-transparent** so the image shows through, while title, fields and buttons stay fully legible. The choice applies to new sign-ins immediately.
- **TIP:** More appearance options will appear here over time; for now it covers the login page.

---

## 13. License & Demo Mode — 🔑 (audience: admin)
*Subtitle: "Applying a license and the demo grace period"*

### Licensing
- The application **requires a valid license**. Upload the issued license file in **App Control → License**; the panel shows **who it is licensed to and when it expires**, and lets you remove it again.
- With no valid license the app runs in **Demo Mode** for a **one-time grace period** — the sign-in panel shows **"Demo Mode — remaining time"**, or **"No License installed"** once that period is spent — after which the **compute backend stops** until a license is applied. Uploading a valid license during the grace period **cancels the shutdown**.
- **TIP:** The demo period is granted **once per installation; restarting does not renew it**. The admin interface itself keeps working even when the backend has stopped, so you can always apply a license there.

---

## 14. Chart Views — 📊 (audience: all users)
*Subtitle: "Process map, A/B comparison, individual journey and statistics"*

### A-Chart
- The primary process map. Shows all journeys matching the current filter set as an aggregated **directly-follows graph**; arrow thickness reflects the selected transition metric. When a project is first selected, A-Chart loads automatically using the **last N days** of data — **N defaults to 30** and is set in **Configuration → Default date window** (**0 shows the full range**).
- **TIP (date slider):** A date slider sits above the map, in the **Date & Metrics** card. In **Range** mode it has two independently draggable thumbs — drag either to move the window start or end; in **Day** mode a single thumb selects one calendar day. Both thumbs also respond to the **arrow keys** once focused. Switch modes with the **Range / Day** control at the right of the metric row, just below the slider.

### B-Chart
- An independent second process map with **its own filter set** — for exploring a different segment (date window, step selection, or meta value). **B-Chart starts empty**: apply filters and tap **Apply**, or use the **Load** button on its empty state.

### A/B Comparison
- Splits the main area vertically: **A-Chart left, B-Chart right**, both visible at once. The sidebar filters operate on the **active side** — switch by tapping a panel header or the **A/B segmented control** at the top of the Filters section. The active panel shows a **pencil icon and an "editing" label**.
- **Valve (⇄ on the divider)** — Open: both panels share one viewport; pan, zoom, reset and node drags mirror instantly. Closed: each panel moves independently; closing **snapshots A's current view into B** so they start aligned before diverging. **A is always the master.**
- **Copy layout (⧉ in A's header)** — transfers A's complete viewport — zoom, pan and every node position — to B in one tap.
- A **Process Similarity badge** floats between the panels, showing the Q score coloured green/blue/red. It refreshes automatically whenever you apply filters or move a date slider in either panel.

### Individual Journey
- Shows the complete step sequence for a single journey identified by `EVENT_ID`. The Filters section becomes an **Event ID field**: type a source identifier (e.g. `ORD-000001`) or a raw 32-character hash and press Return. Any input that is not already a hash is **MD5-hashed automatically** before querying.
- **TIP:** A **live suggestion dropdown** appears as you type. Each EVENT_ID keeps its **own saved node layout**.
- **TIP:** Transitions are labelled with the **average transition time**. The sidebar metric picker is hidden in this view (a single journey visits each step once — Count would carry no information).
- **TIP:** A **moving dot replays the journey** — travelling the transitions in chronological order, then looping.

### Statistics
- Analyses all journey routes matching the current filters — **always inherited from Chart A**. A **Routes / Analytics** toggle switches between:
  - a searchable, sortable, paginated table of distinct journey variants (with a journeys-over-time chart), and
  - a set of visualisations: the duration histogram, step traffic, and a transition heat map.
- **TIP:** If you change a filter after loading, an **orange "Filters changed since last load" banner** appears with a one-tap **Reload** button. Journeys-over-time granularity is automatic: **≤14 days → daily, ≤90 days → weekly, otherwise monthly**.

---

## 15. Filters — ⛃ (audience: all users)
*Subtitle: "Metrics, date range, steps, score and meta filters"*

### Transition metrics
- The **Metrics** section controls which value drives the thickness, opacity, colour and label of each transition arrow:
  - **Count** — number of times this transition occurred. **The default, always available.**
  - **Avg Time** — average elapsed time between the two steps, shown as a readable duration (4m, 1.2h, 3.5d).
  - **Min / Max Time** — shortest / longest observed elapsed time for this transition.
  - **Std Dev** — standard deviation of elapsed times — higher values indicate inconsistent transition durations.
- **TIP:** Each chart view stores its **own metric selection**. Each metric has its own colour scale — click the colour legend at the bottom-right of the map to configure them.

### Journey-level filters
- **Every filter works at journey (case) level** — a journey either qualifies in full or not at all.
  - **Date range** — journeys with at least one event inside the window. Adjustable from the slider above the map.
  - **Include Steps** — show only journeys that pass through **any** selected step.
  - **Exclude Steps** — remove every journey that passes through any selected step. A step chosen for Include is automatically disabled for Exclude, and vice versa.
  - **Num Steps** — keep journeys whose total step count is within the range.
  - **Journey Time** — keep journeys whose first-to-last span is within the range.
  - **Journey Score** — keep journeys whose summed step scores are within the range. **Negative scores are supported** — drag the right handle below zero to isolate problem paths.
  - **Meta 1–3** — case-level, **case-insensitive contains search**. Each is a searchable dropdown: focus the field (or tap the ▾) to see the distinct values from the database, then click one or type to narrow the list. The **⊗** clears the selection.

### Applying, resetting and saving
- **Filters are not applied automatically.** Three buttons at the bottom of the section:
  - **Reset** — restores all filters to the project defaults.
  - **Save Preset…** — captures the current filter state as a named preset.
  - **Apply** — reloads the map with the current settings. **In A/B Comparison only the active side reloads.**
- **Filtered Journeys** shows matches for the active filters; **Total Journeys** always reflects the unfiltered project count.

---

## 16. Filter Presets — 🔖 (audience: all users)
*Subtitle: "Save and reapply named filter configurations"*

### What is a preset?
- A preset captures a **complete snapshot of every filter dimension** — date range, included/excluded steps, meta values, step-count, journey-time and score bounds — under a chosen name. Presets are **stored per project, persist between sessions, and are included in Backup & Restore**.

### Saving, applying, managing
- Configure the filters, then tap **"Save Preset…"** (between the Reset and Apply buttons) and give it a name. **The state is captured at that moment — later filter changes do not update the preset.**
- Every chart header shows a **Presets picker**. Choosing a preset restores all its settings instantly; the chart reloads and the date slider updates to the preset's window. **In A/B Comparison each panel has its own independent Presets picker**, so different presets can be applied to A and B at once.
- **TIP:** Rename and delete a preset from the small **✎ / 🗑** buttons next to it in the sidebar Presets list.

---

## 17. Process Map — 🗺 (audience: all users)
*Subtitle: "Navigation, nodes, groups and context actions"*

### Reading the map
- Each node = a distinct process step. Arrows show transitions; **thickness and opacity** reflect the selected transition metric **relative to the highest value on the map**. The label shows the value for the active metric — a plain number for Count, a readable duration for time-based metrics.

### Connection colouring
- When **"Colorise edges by weight"** is on, each arrow is tinted using the colour scale configured for the active metric — from the low-end colour (few / short) to the high-end colour (many / long). **Thickness always encodes the value independently of colour.**
- **Per-metric scales** — each of the five metrics has its own scale. **Defaults: Count → green, Avg Time → orange, Min Time → blue, Max Time → red, Std Dev → purple.**
- **TIP:** Click the **colour legend in the bottom-right corner** of the map to open the wizard and pick a scale for each metric, with a live preview. **"Reset to defaults"** restores the built-in scales.

### Start and end markers
- **Green arrow (entry)** — appears above every start node (a step with no incoming transitions).
- **Orange arrow (exit)** — appears below every end node (a step with no outgoing transitions).
- When a step belongs to a group, both markers are drawn **outside the group's dashed border** so they stay visible.

### Navigating & moving nodes
- Scroll / pinch to **zoom**; drag the background to **pan**; **double-click to fit** the graph to the window.
- Drag a node to reposition — **saved per project and per chart view; positions snap to a 20 pt grid**.
- Drag a group box to move all its members at once.
- **↺** discards custom positions and reverts to the automatic layout.
- **⤢** fits the graph; the **±** buttons zoom precisely.
- **TIP:** Automatic layout quality depends on the **"Optimise layout"** toggle in Configuration — when on, crossing minimisation produces a cleaner arrangement on complex graphs.

### Node context menu (click a node → small action card)
- **Require in journeys** — adds the step to Include Steps and reloads.
- **Exclude from journeys** — adds the step to Exclude Steps and reloads.
- **Show Notes (n)** — opens the notes for this node; the count in parentheses is how many it already has. With none, opens the editor to create one; with one or more, opens the list to read them and add another (a node or edge can hold several notes).
- **Show description** — displays the full `DESCRIPTION` text for the step, when it differs from the name.

### Node appearance & groups
- Colours and shapes (**stadium / round / hex / circle**) come from the STEPS table and are editable in **Configuration → Steps**. An **orange dot** marks an end-of-process step; a **score badge** in the top-left is **green** for positive, **red** for negative, **blue** for zero. A **yellow ✎ badge** marks a node with a note.
- Steps sharing a `BELONGS_TO` value are wrapped in a **dashed, coloured group box with a name pill**. The box tint/border are tuned per theme for visibility in light and dark mode. The **+/− badge** on the box collapses or expands it — **collapsed groups sum connection counts and weight-average the times**. **"Groups start"** in Configuration controls whether groups load **Expanded, Collapsed, or in their last Persisted state**.

---

## 18. KPI Panel — 📇 (audience: all users)
*Subtitle: "Journey counts, durations and score tiles"*

### The tiles
- **Total Journeys** — distinct journeys in the project with **no filters applied**; does not change when you adjust filters.
- **Filtered Journeys** — distinct journeys matching all current filters — the population the map visualises.
- **Shortest / Avg / Longest Journey** — fastest, mean and slowest journey duration in the filtered set, first event to last.
- **Std Dev** — standard deviation of journey durations. Low = most journeys take a similar time; high = durations vary widely.
- **Graph Value** — sum of (step score × visit count) for every scored node on the map. **Visit count is the larger of a node's incoming and outgoing transition occurrences**, so start and end nodes are handled correctly. Higher value = high-scoring steps visited frequently.
- **Process Goodness** — composite quality score for the whole process. Rewards paths where high-scoring steps are reached efficiently, penalises slow or low-scoring routes, with a coverage factor. (See Process Goodness chapter.)
- **Process Similarity** — **A/B mode only** — floats between the panels; compares the two filtered processes.

### Behaviour
- The strip and the date slider appear **only once a chart has loaded data**; hidden on launch, after disconnecting, and on any view not yet loaded. Tap the **chevron handle** to collapse the strip — the journey counts then appear inline in the handle bar. **Reorder tiles and toggle their visibility in Configuration → KPIs.**
- **TIP:** In A/B Comparison, each panel has its own KPI strip. The Process Goodness tile is **green** when this panel's value beats the other, **red** when lower, **blue** when equal within **0.005**.

---

## 19. Process Goodness — ◔ (audience: all users)
*Subtitle: "How the quality score is calculated"*

### What it measures
- A single number summarising how well the process performs across all journeys matching the current filters. Combines three ideas:
  - **Quality** — do journeys pass through high-scoring steps?
  - **Efficiency** — are journeys short, or do they take a long time?
  - **Coverage** — how large a fraction of total journeys do the current filters capture?
- Higher = better. Positive = the process delivers net value relative to its time cost. Negative = slow, low-scoring routes drag quality down.
- **TIP:** Only shown when **at least one step has a SCORE value** configured in STEPS. If no scores are set, **the tile is hidden**.

### The formula
- Computed in two stages. Raw goodness across all distinct path patterns:

```
raw = Σ (freq / total) × (sum_of_scores / √n − 0.01 × avg_duration)
```

- Then a coverage factor:

```
Process Goodness = raw × (filtered_journeys / total_journeys)^0.5
```

### Inside the formula — each term
- **freq / total** — relative frequency of the path pattern. A path taken by 80 of 100 journeys has freq/total = 0.80. More common paths influence the score more (weighted average, not simple average).
- **sum_of_scores** — sum of SCORE values (STEPS table) for every step in the path. No score → contributes zero. Negative scores can produce a negative sum.
- **√n (alpha = 0.5)** — square root of the number of steps in the path. Longer paths must earn proportionally more total score, but the penalty grows slowly (square root, not linear). A 4-step path divides by 2; 9-step by 3. Discourages detours without harshly punishing complex processes.
- **0.01 × avg_duration** — time penalty. avg_duration is the average total journey time **in seconds** for this path pattern. **Every 100 seconds of journey time costs 1.0 point.**
- **(filtered / total)^0.5 (gamma = 0.5)** — coverage factor. Filters capturing half of all journeys give √0.5 ≈ 0.71, reducing the score ~29%. With no filters, coverage = 1.0, no effect.
- **TIP:** Fixed constants — **alpha=0.5, time_penalty=0.01, gamma=0.5** — are embedded and **not adjustable** in the current version.

### Example 1 — two paths, short vs. long
A digital checkout with 100 orders; 85 direct, 15 via a coupon step.

```
Path A  (85 journeys): Browse → Cart → Pay → Confirm
  Scores: 2 + 3 + 10 + 10 = 25    Steps: 4    Avg duration: 30 s

Path B  (15 journeys): Browse → Cart → Coupon → Pay → Confirm
  Scores: 2 + 3 + 1 + 10 + 10 = 26    Steps: 5    Avg duration: 60 s
```

Path A:
```
quality   = 25 / √4 = 25 / 2     = 12.50
time cost = 0.01 × 30            =  0.30
path score = 12.50 − 0.30        = 12.20
weighted   = 0.85 × 12.20        = 10.37
```

Path B:
```
quality   = 26 / √5 ≈ 26 / 2.24  = 11.61
time cost = 0.01 × 60            =  0.60
path score = 11.61 − 0.60        = 11.01
weighted   = 0.15 × 11.01        =  1.65
```

Combined (all 100 journeys in filter, 100 total):
```
raw = 10.37 + 1.65 = 12.02
coverage = 100 / 100 = 1.0    →  factor = √1.0 = 1.00

Process Goodness = 12.02 × 1.00 = +12.02
```

- **TIP:** Path B contributes slightly less per journey (11.01 vs 12.20) even though it collects one extra score point — the longer path and slower duration partially offset the extra point; the formula captures this tradeoff automatically.

### Example 2 — a failed-payment path with negative scores
Same process; 10 orders hit a payment failure and are refunded. Step scores: **Pay Failed = −10, Refund = −5**.

```
Path A  (80 journeys): Browse → Cart → Pay → Confirm
  Scores: 25    Steps: 4    Avg duration: 30 s    (same as before)

Path B  (10 journeys): Browse → Cart → Coupon → Pay → Confirm
  Scores: 26    Steps: 5    Avg duration: 60 s    (same as before)

Path C  (10 journeys): Browse → Cart → Pay → Pay Failed → Refund
  Scores: 2 + 3 + 10 + (−10) + (−5) = 0    Steps: 5    Avg duration: 90 s
```

Path C:
```
quality   = 0 / √5 = 0
time cost = 0.01 × 90 = 0.90
path score = 0 − 0.90        = −0.90
weighted   = 0.10 × (−0.90)  = −0.09
```

Combined:
```
Path A weighted: 0.80 × 12.20 =  9.76
Path B weighted: 0.10 × 11.01 =  1.10
Path C weighted:              = −0.09

raw = 9.76 + 1.10 − 0.09 = 10.77
coverage = 1.0

Process Goodness = +10.77   (was +12.02 before failures appeared)
```

- The failed-payment path drops the score by 1.25 points even though it affects only 10% of journeys — zero quality score plus extra time makes it a net negative contributor.
- **TIP:** Use this pattern to detect problem paths. On a sudden drop between two date periods, filter to isolate paths through specific problem steps — the score confirms whether those paths are responsible.

### Example 3 — the coverage penalty when filtering
A "Europe only" region filter matches only 40 of 100 orders; within those there are no failures, so raw goodness is the same clean +12.02.

```
coverage = 40 / 100 = 0.40
factor   = √0.40 ≈ 0.632

Process Goodness = 12.02 × 0.632 ≈ +7.60
```

- The filtered result (+7.60) looks worse than the global (+12.02) not because Europe performs worse but because the filter captures a smaller proportion — the score reflects both quality **and representativeness**.
- **TIP:** To compare two segments fairly, use **A/B Comparison**: set A to one segment, B to the other. Each panel's Process Goodness tile applies the same formula independently, so scores are directly comparable even with different journey counts.

### Requirements and limitations
- At least one step must have a **non-zero SCORE** in STEPS. Without scores the tile is hidden.
- The query groups journeys by path pattern — on very large, heavily filtered datasets it may take several seconds. **A 30-second timeout applies; if it expires the tile shows "—".**
- Average duration per path pattern is used as the time component; individual journeys may differ.
- Steps with no SCORE contribute 0 — neither help nor hurt.
- The score **can be negative** when slow, low-scoring paths dominate.
- **WARNING:** Process Goodness is a **relative indicator, not an absolute benchmark**. Use it to spot trends over time, compare segments in A/B mode, or monitor the impact of process changes — not as a standalone pass/fail threshold.

---

## 20. Process Similarity — ⇄ (audience: all users; shown in A/B mode)
*Subtitle: "How Q(T₁, T₂) compares two filtered processes"*

### What it measures
- Q(T₁, T₂) is a single number **between 0 and 1** answering: how behaviourally alike are the two process views in A-Chart and B-Chart?
- **1.0** = identical — every variant explained equally well by both graphs, same scored steps visited in the same proportion. **0.0** = share almost nothing. In between = partial overlap.
- Unlike Process Goodness (how good a single process is), this is a **comparison metric** — use it to confirm two filter segments really behave differently, or verify a process change had measurable effect.
- **TIP:** Only appears in **A/B Comparison** mode, as a floating badge between the panels. Refreshes automatically whenever you apply filters or move a date slider in either panel.

### The formula
```
Q(T₁, T₂) = 0.4 · Q_var  +  0.4 · Q_nodes  +  0.2 · Q_cov
```
- **Q_var (40%)** — variant alignment agreement: how consistently both graphs explain the same journey variants. Both handle a variant equally (both replay perfectly, or both fail equally) → high; one handles it much better → low.
- **Q_nodes (40%)** — node agreement weighted by importance: a Jaccard-style ratio comparing which **scored** steps are actually visited — under each graph — per variant. Steps with higher absolute score count more.
- **Q_cov (20%)** — joint coverage: the fraction of variant frequency explained **perfectly (zero missing edges) by both graphs simultaneously**.
- **TIP:** The 40/40/20 weights reflect that structural similarity (Q_var) and scored-step agreement (Q_nodes) are equally important; coverage is a useful but secondary signal.

### Alignment cost — the key building block
```
cost_T(v) = missing_edges / total_edges_in_variant
```
- A "missing edge" = a consecutive step pair in the variant that does not appear as a transition in the graph. All transitions exist → cost 0 (perfect fit); half missing → 0.5. A one-step variant (no edges) is **skipped**.
- A practical approximation of formal process-mining alignment — linear time per variant, no external solver, fast enough to run automatically on every panel reload.
- **TIP:** The variant set is **capped at 500 per side (1 000 combined)**. When the cap is exceeded the badge is **hidden** rather than showing a misleading score from a biased sample.

### Example 1 — nearly identical segments (EU vs North America)
```
Variant A  (90 % of journeys, both sides):
  Browse → Cart → Pay → Confirm
  Edges exist in both graphs → cost_A = 0,  cost_B = 0

Variant B  (10 % of journeys, EU only):
  Browse → Cart → Coupon → Pay → Confirm
  All edges in A-graph; Coupon→Pay missing in B-graph
  cost_A = 0,  cost_B = 1/4 = 0.25
```
```
Weighted Q_var ≈ 0.90 × 1.0 + 0.10 × 0.0 = 0.90

Assume scored steps: Pay = +10, Confirm = +10 (both graphs)
Q_nodes ≈ 0.95  (Coupon step has no score, so its absence barely matters)
Q_cov   = 0.90  (90 % of frequency fits both perfectly)

Q = 0.4 × 0.90 + 0.4 × 0.95 + 0.2 × 0.90
  = 0.36 + 0.38 + 0.18 = 0.92  → green
```
- **TIP:** 0.92 correctly reflects very similar processes — only the coupon path distinguishes them.

### Example 2 — same period, different quality paths
A = standard process (no failures); B = same date range filtered to orders including a "Pay Failed" step.
```
Variant A  (100 % of A-side): Browse → Cart → Pay → Confirm
  All edges in A-graph (cost_A = 0)
  'Pay → Confirm' missing from B-graph  (cost_B = 1/3 ≈ 0.33)

Variant B  (100 % of B-side): Browse → Cart → Pay → Pay Failed → Refund
  'Pay → Confirm' missing from A-graph  (cost_A = 1/3 ≈ 0.33)
  All edges in B-graph  (cost_B = 0)

Scored steps: Pay = +5, Confirm = +10, Pay Failed = −10, Refund = −5
```
```
Q_var   = 0.00   (each side fits only its own variant)
Q_nodes ≈ 0.45   (high-value steps differ between the two populations)
Q_cov   = 0.00   (neither variant fits both graphs perfectly)

Q = 0.4×0.00 + 0.4×0.45 + 0.2×0.00 = 0.18  → red
```
- 0.18 correctly signals strong divergence — happy-path and failure-path populations are fundamentally different processes.

### Example 3 — before and after a process change
A = January (before a redesign); B = February (after — two slow approval steps merged into one).
```
Shared variant (70 %): Browse → Submit → Approve → Complete
  Both graphs contain these edges → cost_A = 0, cost_B = 0

Old variant (30 %, Jan only): Browse → Submit → Review → Approve → Complete
  cost_A = 0  (all edges in Jan graph)
  'Submit→Review' and 'Review→Approve' missing from Feb graph
  cost_B = 2/4 = 0.50

Scored steps: Approve = +8, Complete = +10
```
```
Weighted Q_var = 0.70×1.0 + 0.30×0.0 = 0.70
Q_nodes ≈ 0.82   (Review step has no score, so its absence barely hurts)
Q_cov   = 0.70   (70 % of frequency fits both graphs perfectly)

Q = 0.4×0.70 + 0.4×0.82 + 0.2×0.70
  = 0.28 + 0.33 + 0.14 = 0.75  → green
```
- 0.75 = broadly similar (core path unchanged), while a value below 0.90 confirms the redesign introduced a structural difference.
- **TIP:** Use this pattern to validate process changes: Q near 1 after a change = little behavioural effect; Q dropping toward 0.5 or below = a meaningful structural shift.

### Colour thresholds and limitations
- **Green: Q ≥ 0.70** — behaviourally similar.
- **Blue: 0.30 ≤ Q < 0.70** — moderate similarity; some paths shared, others differ.
- **Red: Q < 0.30** — strong divergence; fundamentally different behaviour.
- **WARNING:** A relative indicator, not an absolute benchmark. Depends on which steps have SCORE values — **if none do, Q_nodes defaults to 1.0** and only Q_var and Q_cov contribute. Also sensitive to the route limit.
- The practical guard caps input at 500 variants per side (1 000 combined); when hit, the badge is hidden.
- Alignment cost is an edge-coverage approximation, not a formal Petri-net alignment — may slightly **overestimate** similarity for processes with loops or repeated steps.
- **Q is symmetric: Q(A, B) = Q(B, A)** — the same value appears for both panels.

---

## 21. Simulation — 🎲 (audience: power/admin only)
*Subtitle: "Synthetic process data from a calibrated Markov model"*

### What is simulation?
- Generates synthetic event logs that statistically resemble the real process. Builds a **first-order Markov chain** from the currently loaded process graph, then walks it to produce journeys with the same three fields the database contains: journey identifier, step name, timestamp.
- Every synthetic journey follows the routing probabilities and timing distributions observed in the actual data — useful for load-testing, what-if analysis, training-data generation, or exploring "what would 10 000 more journeys look like?"
- **TIP:** Uses the process graph currently loaded in **Chart A**, including any date-range and step filters. Apply desired filters before running to calibrate on a specific slice.

### How the model is calibrated
- Reads three things from the displayed graph:
  - **Transition probabilities** — occurrence counts of each step's outgoing transitions normalised to probabilities (600 to "Approve" + 400 to "Reject" → 60% / 40%).
  - **Duration distributions** — each directed edge carries average duration and standard deviation from real data; a **lognormal** distribution is fitted and sampled to advance the clock per transition. Lognormal = correct shape for process durations: strictly positive, right-skewed, matching the long tail of slow cases.
  - **Start steps** — steps whose **incoming frequency is less than 20% of their outgoing frequency** are identified as likely entry points; their relative frequency as first steps samples the opening step of each journey.
- If an edge has timing data in only one direction (average without std dev, or vice versa), the available value only is used. **No timing data → a one-hour lognormal default.** Start steps are always identified from the **original** graph before exclusions, so removing a step never creates a false entry point.

### Arrival process
- New journeys are born by a **Poisson process**: the gap between consecutive journey start times is drawn from an exponential distribution parameterised by **"Average inter-arrival (hours)"** — the standard queueing-theory arrivals model.
- Poisson is memoryless — correctly models independently-initiated cases (order placements, patient admissions, support tickets).
- **Average inter-arrival (hours)** — the mean hours between consecutive journey start times. 1.0 = one new journey per hour on average. Controls the spread of timestamps in the exported CSV; **does not affect routing or cycle times**.
- **TIP:** To estimate the correct rate, check the "Journeys over time" chart in Statistics: divide journey count by time span in hours.

### Simulation parameters
- **Journey Count** — how many complete journeys to generate. Higher = more stable variant distributions and smoother histograms but slower. **For a first run, 200–500 is usually enough** to see the dominant shape.
- **Start Date** — the date assigned to the first simulated journey's opening event; subsequent events are timestamped relative to this anchor.
- **Max Steps per Journey** — hard cap preventing rework loops running forever. A journey hitting the cap is included as-is, potentially incomplete. **Default 60.**
- **TIP:** Many journeys with exactly 60 steps in the Variants table = the cap is being hit. Increase it for genuinely long rework loops, or add the looping step to Excluded Steps.

### Excluded and required steps
- **Excluded steps** — removed from the Markov model **entirely before simulation**; all transitions to/from them discarded. Models a process improvement (e.g. removing a manual approval). **Steps that become unreachable as a result are automatically excluded too, transitively.**
- **Required steps** — a **post-simulation filter**: only journeys visiting every required step at least once are kept. The engine generates the full configured count then discards non-qualifiers, so **reported total can be lower than the configured Journey Count** if required steps are rare.
- The two lists are **mutually exclusive** — an excluded step cannot also be required.

### Worked example — a fork process
Observed A-Chart graph: after Start, 70% go through Fast, 30% through Slow, both rejoin at End.
```
Observed transitions (calibration input):
  Start → Fast   occurrences 700   avg 2 min,  sd 30 s
  Start → Slow   occurrences 300   avg 2 min,  sd 30 s
  Fast  → End    occurrences 700   avg 5 min,  sd 1 min
  Slow  → End    occurrences 300   avg 40 min, sd 8 min
```
Derived Markov model:
```
Start step   : Start   (in/out ratio < 0.2 → entry point)
P(Fast | Start) = 700 / 1000 = 0.70
P(Slow | Start) = 300 / 1000 = 0.30
Fast → End, Slow → End are the only continuations (probability 1.0)

Edge durations → fitted lognormal(μ, σ) per edge, floor 60 s
```
Running 1 000 journeys converges to roughly:
```
Variant "Start → Fast → End"   ≈ 700 journeys (70 %)   avg ≈ 7 min
Variant "Start → Slow → End"   ≈ 300 journeys (30 %)   avg ≈ 42 min

Cycle-time histogram: a tall early peak (the Fast branch) and a
smaller, wider hump further right (the Slow branch) — bimodal,
exactly as the two-branch structure predicts.
```
- **TIP:** Sampling is random — counts vary slightly run to run (around 700/300, not exactly). Raise Journey Count for a tighter match; watch the Variants-tab percentages converge as you increase it.

### What-if example — automating the slow branch
Add "Slow" to Excluded steps and run again — engine removes Start→Slow and Slow→End, re-normalises:
```
After excluding "Slow":
  P(Fast | Start) = 700 / 700 = 1.00

Result: one variant "Start → Fast → End", ~1000 journeys,
avg ≈ 7 min, and a single-peaked (unimodal) cycle-time histogram.
```
- Comparing the two runs quantifies the improvement — bimodal collapses to a single fast peak, average cycle time cut dramatically — without touching the database.
- **TIP:** Store each run in a slot (**Sim-A / Sim-B**), then select them as A and B data sources in the **Sampling** section to compare the two synthetic processes side-by-side in A/B Comparison — including a Process Similarity score between them.

### Reading the results
- After a run, **six KPI tiles**: Journeys, Avg cycle time, Shortest, Longest, Std dev, Variants — above **four tabs**:
  - **Flow** — the directly-follows graph of the simulated log, same interactive flow chart as everywhere else. Because simulation is probabilistic, it resembles but is not identical to the real graph — with a small Journey Count, **rare edges may not be sampled at all**.
  - **Variants** — a ranked table of every distinct path, ordered by frequency, with count, share and average cycle time.
  - **Charts** — a cycle-time distribution histogram and a top-variants bar chart. Unimodal right-skewed = typical well-behaved process; **bimodal often signals two fundamentally different paths** — check the Variants tab for the split.
  - **Event log** — the raw event rows (JOURNEY_ID, STEP, EVENT_TIME). **Export** the full log as CSV.

### Exporting the event log
- **Export CSV** saves the full event log — one row per event, three columns:
```
JOURNEY_ID,STEP,EVENT_TIME
```
- Structurally identical to a JOURNEYS export from Exasol — importable into another process-mining tool, Excel or pandas, loadable back into an Exasol JOURNEYS table as a test sample set, or usable as labelled ML training data.

### Limitations and assumptions
- First-order Markov model: each routing decision depends only on the current step. Strong history-dependent routing (e.g. once-rejected cases behaving differently on retry) is not captured.
- Long-range dependencies and case attributes (META_1–3) are not modelled — no concept of customer segment or region influencing routing.
- Resource constraints and queues are not modelled; cycle times sampled independently per event; doubling volume does not increase waiting time.
- The model calibrates from the **visible graph only** — active filters mean the model reflects only that subset.
- Very rare transitions may have unreliable duration estimates (std dev from two or three observations is noisy).
- **WARNING:** Do not use simulation results as a substitute for real data analysis when making production decisions — the simulation reproduces statistical structure, not individual journey behaviour, seasonal effects, or emergent properties from resource contention.

---

## 22. Conformance Check — 🛡️ (audience: power/admin only)
*Subtitle: "Compare the actual process against target norms"*

### What it does
- Overlays target values (**"norms"**) on any transition metric and shows, edge by edge, whether the actual process meets them. **Switch metrics with the chips at the top** — norms are stored **per project and per metric**.
- **For Count** — norms are **percentages of the total traffic leaving the same source node**. A norm of 50% on A→B means "at most half of everything leaving A should go to B".
- **For time metrics** — norms are **absolute values (seconds)**, compared directly against the edge's Avg/Min/Max/Std-Dev time.

### Setting and reading norms
- Click **"Edit norms"**, then click an edge and type its target. In view mode each edge turns **green or red** depending on whether the actual value meets the norm; the **"Norm is a minimum"** toggle flips the comparison so the actual must be **≥** the norm instead of ≤.
- **TIP:** For the Count metric the editor shows a live **"remaining %"** as you type — how much is already assigned to the source node's other outgoing edges and how much is left to reach 100% — and **warns in red** if your value would push the node's outgoing norms over 100%.
- **"Show gaps"** opens the full gap-analysis table — **from, to, actual, norm, delta and status** — sorted with violations first. The gap analysis is also appended to the AI Documentation report.
- **TIP:** Norms round-trip through Backup & Restore, so a target model built once can be shared or moved between installations.

---

## 23. Happy Path — 🪧 (audience: power/admin only)
*Subtitle: "Define ideal step sequences and measure real conformance"*

### Defining an ideal path
- A Happy Path is the ideal sequence a process should follow. Create one, then add steps in order. **Left panel** = the actual process map; **right panel** = your ideal definition — toggle **Edit mode** to add (＋), reorder (▲ ▼) or remove (⊖) steps.
- **⑂ Split** — add a split where the process may legitimately take one of several alternatives — each is a branch you fill with its own steps, so legitimate variations are scored fairly. Give the split a name with its **✎** button.
- **Rejoin & continue** — a split's branches reconverge: steps added after a split are the shared continuation all branches lead into. When a split has a continuation you can name the rejoin point too (the **✎ Rejoin** button on the split, shown as **⑃** in the diagram). If a split is the last thing on the path, its branches are simply alternative endings — no rejoin to name.
- **Nesting** — a branch can itself contain a split; the editor and diagram nest accordingly.
- **TIP:** Drag the divider between the two panels to widen the ideal-path editor (handy for deeply nested splits); **double-click it to reset. The width is remembered.**

### The conformance score
- A **journey-count-weighted average of edge coverage**: for each real journey variant, the fraction of the ideal path's transitions that the variant actually contains, weighted by how many journeys followed it.
- **1.00** — every journey follows the ideal path perfectly.
- **0.00** — no journey shares a single transition with the ideal sequence.
- **Every start-to-end route through the splits is considered, and each journey is scored against the route it matches best** — a case taking a legitimate alternative is not unfairly penalised.
- **TIP:** Steps in the ideal path absent from the currently filtered process are shown **dimmed**, so you immediately see which ideal steps never actually occur under the current filters.

---

## 24. Journey Sampling — ▤ (audience: power/admin only)
*Subtitle: "Representative subsets for fast, meaningful analysis"*

### Why sample?
- Because samples are **shared by everyone on the connection**, the Sampling section is available to **Power users and administrators only** — Regular users don't see it.
- On very large event logs, a representative subset keeps exploration interactive while preserving the process's shape. Create **up to three named sample sets** from the original data; the A and B chart slots can each select their own sample independently.
- Samples are written to a **SAMPLE_SET** column on JOURNEYS (added automatically on first use). **Original rows are never modified; deleting a sample removes only its rows.**
- Because sample sets live in the project database, they are shared by everyone connected to that project — unlike personal settings and filter presets, which are per user. **Creating or deleting a sample changes it for all users of the project.**

### The three strategies
- **Random** — uniform random journey selection. Simplest baseline — fast and unbiased, but rare variants may be under-represented.
- **Temporal Stratified** — proportional selection across equal calendar-month buckets, preserving the time distribution — useful when volume varies seasonally.
- **Path Diversity** — coverage-maximising selection across distinct journey variants, so rare paths are more likely to appear — useful when you care about the full variety of behaviour, not just common cases.

### Using samples & simulations as A/B sources
- In the Sampling section, each of the **A and B slots** has a picker selecting **Original data**, one of the **three sample sets**, or a **stored Simulation result (Sim-A / Sim-B)**. This is how simulated processes are fed into A/B Comparison to compare against real data — or against each other.

---

## 25. AI supported Documentation — 🧠 (audience: all users; needs an LLM-attached connection)
*Subtitle: "AI-powered process analysis and a structured report"*

### How it works
- Sends the **current A-Chart transition table** together with your **prompt template** to the OpenAI-compatible endpoint configured on the active connection, and renders the answer as a structured **Markdown report**.
- The report also includes sections **computed locally and never sent to the model**: the journey-paths table, happy-path conformance, the conformance gap analysis, and your notes. Before running, **notice cards** summarise the A-Chart filter context plus how many happy paths and norms will be included.
- **TIP:** Edit the prompt under **Configuration → LLM Prompt**; templates are stored **per project**. Use the browser's **Print / PDF** to export the finished report.

### Requirements
- The active connection must have an **LLM server attached** (base URL, model, optional API key).
- The **second status dot** on the connection card must be **blue** — the model server is reachable.
- **Any OpenAI-compatible endpoint works**: local servers (Ollama, llama.cpp, vLLM, LM Studio) or cloud APIs.
- **WARNING:** AI models can produce results that are incorrect, incomplete or misleading. **Independently verify every finding before acting on it.**

---

## 26. Process Notes — 🗒 (audience: all users)
*Subtitle: "Annotate nodes and edges with sticky notes"*

### Creating and finding notes
- Click a node or an edge and choose **"Show Notes"** to add an annotation. A **yellow ✎ badge** marks any node or edge carrying a note. The **Notes view** lists every note for the project — **newest first — independent of the current filters**.
- Each note records its **author, who last contributed, and the complete filter context at creation time**, so the observation stays interpretable later. The author is the signed-in application user — shown by **real name (the directory "cn") for LDAP accounts** — not the shared database login.
- **A note is a thread.** Opening it shows all comments so far on top (read-only) and an **"Add a comment"** box below: anyone who can see the note — the author, and other users for a shared note — can add a comment, placed at the top of the thread and recorded with their name and time. Give the note (at creation) and each comment a **short title**; the most recent title is shown as the note's heading, separately from the body, in both the list and the node's note panel. **Only the author can change the note's importance or sharing, or delete the whole thread.**
- **Importance levels**: **NORMAL (default), INFO, IMPORTANT, URGENT** — shown as a coloured badge in the list. Mark a note as **"shared"** to make it visible to other users of the same database, and tick **"resolved"** once the issue is closed — a **green ✓ Resolved badge** then appears.
- Notes view filtering: **text search, type (node / edge), importance, status (unresolved / resolved), author, time window (any time, or last 7 / 30 / 90 days)**; the counter shows how many of the project's notes match. Sortable by **date (newest or oldest first)**, optionally **grouped by importance (on by default)**, and **paged — 5, 10 or 20 notes per page** with **Prev / Next**. A **KPI strip** across the top shows the note count per importance level, least on the left through most urgent on the right, coloured to match the badges.

### Storage
- Notes are stored in a **NOTES table in your Exasol database**, created automatically on first use if the connecting user has CREATE TABLE permission. Notes travel with the data and are visible to every user of that database (subject to the shared flag), not just on the machine that wrote them.

---

## 27. Backup & Restore — 💾 (audience: manual backup — all users; scheduled backups — admin; grouped under Administration in the TOC)
*Subtitle: "Export and import your settings and annotations"*

### What is included
- A backup exports **everything except the event data itself**: connections and servers, filter presets, happy paths, target norms, saved node layouts, LLM prompt templates and app preferences — as a **single JSON file**. **Passwords and API keys are included only if you tick the corresponding boxes.**
- **TIP:** The format is **interchangeable with the macOS version** of the app — a backup taken there restores here and vice-versa.

### Encryption
- Set an encryption password to protect the file with **AES-256-GCM (PBKDF2-HMAC-SHA256, 100 000 iterations, random 16-byte salt, 12-byte nonce)**. Restore **inspects the file first and shows a summary** — connection count, projects, whether layouts/norms/happy-paths/presets are present — before you commit, and lets you **choose exactly which categories to restore**.
- **WARNING:** If you include passwords or API keys **without** an encryption password, they are written in **plain text** in the JSON file. Set a password whenever the backup contains secrets.

### Scheduled (automatic) backups (admin)
- The Backup tab can write an **encrypted backup automatically on a schedule**, as long as the admin server is running. Enable it, choose the frequency, and set an encryption password — the password is **stored encrypted on the server** so unattended backups can run, and is **never shown again** (leave it blank on a later save to keep it).
- Schedule built like a crontab: pick a frequency (**hourly, daily, weekly or monthly**) and the time, or switch to **Custom** for a raw five-field cron expression (minute hour day-of-month month weekday). The panel shows the resulting cron string and a **plain-English summary**; a **"Run backup now"** button tests the configuration immediately.
- **Where they go** — scheduled backups are written on the server under **`data/backups/`** as encrypted `.json` files, **named by timestamp**. **"Keep newest N"** prunes older files so the directory can't grow without bound. The **last run (success or failure)** is shown under the controls.
- **WARNING:** Automatic backups need the encryption password stored to run unattended — treat the server as a secret store. A scheduled backup can only be restored with that password — **keep a copy somewhere safe. Enabling automatic backups requires a password to be set.**

---

## 28. Configuration — ⚙️ (audience: all users)
*Subtitle: "Display options, KPIs, step colours, shapes, scores and groups"*

### Display options
- **Show step groups** — toggles the dashed BELONGS_TO group boxes. When on, **"Groups start"** chooses whether groups load **Expanded, Collapsed, or in their last Persisted state**.
- **Show node notes** — shows the shortened DESCRIPTION under the step name on each node, and the yellow note badges.
- **Optimise layout** — enables barycenter crossing-minimisation for a cleaner arrangement on complex graphs.
- **Colorise edges by weight** — turns on the per-metric colour scales (configured from the map's colour legend).
- **Default date window** — how many days back the map shows when a project first loads — the window ends at the latest event date and spans the last N days. **Defaults to 30; set 0 to load the project's full range. Takes effect on the next project load; does not move the slider on the current map.**
- **Flowchart Font Sizes** — scale the process-map text — separate **S / M / L / XL** settings for **Nodes, Edges and Group titles**. A node's box grows with its font so the label always stays inside; the edge setting enlarges transition labels; the group-title setting sizes the pill on each step-group box.
- **Date slider** — switches the map's date control between **Range (two thumbs)** and **Day (single day)** mode.

### KPIs, steps and preferences
- **KPIs sub-section** — drag to reorder the KPI tiles and toggle each on/off.
- **Steps sub-section** — the in-app **Step Editor**: pick a step, then set its background/foreground colour, shape, score, group and description — **changes are written straight to the STEPS table** and the map redraws.
- **Backup & Restore** and the **LLM prompt template editor** also live in this section. **Theme (System / Light / Dark)** is chosen from the bar at the **bottom of the sidebar**. (Sign-in is managed centrally in the admin interface — there is no per-client authentication toggle here.)

---

## 29. Troubleshooting — 🛟 (audience: all users)
*Subtitle: "Common problems and their fixes"*

### Common issues (Q&A definitions)
- **No connections listed** — no connection has been assigned to your account. Ask an administrator to grant one in the admin interface (Database Connections tab).
- **Cannot connect to Exasol** — connection settings (host, port, credentials, TLS, RSA key size) are managed by an administrator. Ask them to check with Test connection in the admin interface — for **Exasol 7.x or the Docker image the minimum RSA key size must be 1024 bits**, and the account needs SELECT on the required tables.
- **Cannot sign in** — confirm your account is **enabled** (administrator checks the Users tab). Directory (LDAP) accounts must exist in the directory and, for the admin interface, be tagged Admin locally.
- **Statistics / goodness query times out** — narrow the date range or add filters — a **30-second limit** applies. The affected tile shows **"—"**.
- **Simulation returns no journeys** — the graph needs at least one start step (**in-degree / out-degree < 0.2**); exclusions may have removed all entry points. Required steps that never occur also drop every journey.
- **AI Documentation stays blank** — confirm the active connection has an LLM server attached and its status dot is **blue** (reachable); the LLM URL, model and API key are set by an administrator.
- **Notes are not saved** — the connecting user needs **CREATE TABLE** (first use) and **INSERT / DELETE on NOTES**.
- **Sample cannot be created** — the user needs **ALTER TABLE and INSERT on JOURNEYS**.

---

## 30. Integration Console — 🧩 (audience: developer/admin only)
*Subtitle: "Import event data into a connection from files"*

### What it is
- A **separate surface** for loading event data into a database connection. Runs on its own port (**the admin port + 10 — 8100 for HTTP, 8463 for HTTPS by default**) and reuses the same sign-in as the main app. Reachable by **developers and administrators only (power users may not enter it)**.
- At its heart is an **abstraction layer**: pluggable **extractors** read a source (today, a file) and push parsed records into the schema of the connection you are connected to — creating the process-mining tables as needed. You define two things and then run an import:
  - **Source type** — a reusable recipe for parsing one log format: an example line plus the regular expressions that pull out the timestamp, case id, step and up to three meta fields.
  - **Source** — a concrete thing to import — currently a **File** (a path + encoding) linked to a source type.

### Getting there
- Open the console URL and sign in. The left panel holds three collapsible sections — **Connections, Sources and Source types** — plus the theme selector and account footer, mirroring the main app. Clicking a connection connects to it, as in the main app, **but an import does not depend on that: the Run dialog picks its own destination**.
- Connections can be **created and edited here** — no need to switch to the main app. Use **＋** on the Connections header for a new one, or **✎** on a connection you own to edit it — host, port, credentials, TLS, target schema, optional LLM server, and assigned users.
- **WARNING:** ✎ appears **only on connections you own** — the ones you created. A connection an administrator created and assigned to you can be **used for imports but not edited**; ask an administrator to change it.

---

## 31. Source Types & Sources — 🗂️ (audience: developer/admin only)
*Subtitle: "Define how to parse a log, then import a file"*

### Building a source type
- Open **Source types** section, click **＋**. Paste one example log line, then map each field on the tabbed step: pick a **role tab**, then either **highlight a piece of the line and press 🎯 Use selection** to generate a regex, or press **＋ Add field** and type the regex yourself. **Every field is defined manually — no auto-detection, by design**, so the extraction is always exactly what you intend.
- Field roles:
  - **EVENT_TIME** — the timestamp. Analysed and normalised to **YEAR-MONTH-DAY HOUR:MINUTE:SECOND**.
  - **EVENT_ID** — the case/journey key. **Stored MD5-hashed**, so a raw login or user id never lands in the clear.
  - **STEP** — the activity name for the event.
  - **Metas** — up to three extra attributes; give each a business name shown in the app.
  - **Helper** — a value used only by compound-step rules. Extracted from the line but **written to no column**.
- A field's regex should have **exactly one capturing group** — that group is the value. Without a group the whole match is used. **Each row shows live what it captured from your sample**, so a wrong pattern is obvious immediately.
- **TIP:** Name Metas and Helpers deliberately — the name is the label a compound rule uses to reference the field, and META names become the business titles shown in the app.
- A live **"Example JOURNEYS record"** shows the row the spec would produce from the sample (with the original id, labelled **"stored as MD5"**), so you can confirm the mapping before saving.

### Adding a File source
- Open **Sources** section, click **＋**. Choose the **File** kind, enter the **file path and encoding**, **preview the first few lines**, and link the source type that parses it.
- **WARNING:** File reads are **sandboxed**: by default only files under the server's integration files directory can be read. Paths that escape it (via ".." or symlinks) are rejected. An operator can opt out with **`PMW_INTEGRATION_ALLOW_ANY_PATH=1`** for trusted deployments.

### Running an import
- Press **▷** on a File source, pick the **destination connection and the project**. The extractor reads the file line by line, applies the source type's regexes, normalises the timestamp, MD5-hashes the id, and writes **one JOURNEYS row per event** into that connection's schema. A **progress bar** counts records as they load.
- **TIP:** The connection dropdown lists every connection assigned to you and **defaults to the one the main app is connected to**. You do not have to connect first — the import opens the connection itself with its saved credentials, exactly as the watchdog does. The line under the dropdown shows **the host and the schema the rows will land in**.
- The **project dropdown** is filled from projects already in that schema — pick an existing one instead of retyping its id. Choose **＋ New project…** to start a new one and type its id — the PROJECTS row is created for you. Changing the connection reloads the list.
- **TIP (remembered choices):** Both choices are remembered on the source — the next ▷ reopens on the connection and project that source last imported into, so repeating an import is a single click. If the connection is no longer assigned to you it falls back to the one the main app is connected to; a project deleted in the meantime is offered again as a new project id.
- **Delta upload is on by default.** A checkpoint records how far the file has been read; pressing ▷ again imports only lines added since — running the same source twice **tops the project up** instead of storing everything a second time. The panel shows the checkpoint: **records imported, how far into the file it has read, when it last ran**. An empty log file, or one that has not grown, simply reports **"nothing new"** — it is not an error.
- Switch delta upload **off** to read the whole file from the top again; use **↺ Reset checkpoint** to forget the position so the next import starts over. Both are the same from the database's point of view: **events are never de-duplicated** — a full re-read stores the file's events a second time. **To genuinely reload a project, delete it first (Connections → Projects) and import again.**
- **WARNING:** The checkpoint is **shared with the watchdog** — there is one per source. A manual delta import and a watchdog poll advance the same position, which keeps them from importing the same line twice between them. **Resetting it also makes the watchdog re-read the file from the start.**
- The import also **creates anything missing**: the PROJECTS row, a STEPS definition for every distinct step (a shape, a colour, a zero score), and the META business-name titles — **existing rows are never overwritten**.

### Compound steps — build a step from several fields
- Sometimes the real activity is split across fields — the log records the action in one place and its outcome in another. In an Apache log, "POST /shop/login … 200" is a successful login and "… 500" a failed one — but the path alone yields "login" for both, so the process map cannot tell them apart.
- A compound rule names the step to produce and the conditions that must **all** hold. Example line:
```
10.185.248.71 - - [09/Jan/2015:19:12:06 +0000] 4213
"POST /shop/login?userId=20253471 HTTP/1.1" 200 512 "-" "Mozilla/5.0 …"
```
- With step mapped to the path segment and HTTP status mapped as a **Helper**, two rules split one activity into two:

| Rule | Conditions (all must hold) | STEP written |
|---|---|---|
| 1 | step is "login" · status is "200" | login successful |
| 2 | step is "login" · status is "500" | login failed |

- Anything the rules do not cover is untouched — a "basket" line still writes "basket".

### Writing the rules
- Compound steps live in the **STEP tab** of the mapping screen, under the step field — they only ever produce a STEP value.
- Each rule is a **badge** showing the step it produces and its conditions; **three badges visible, list scrolls beyond**. A **✓ on a badge** means that rule matches your sample line. Click **＋ Add rule**, or click a badge, to open its panel:
  - **Step becomes** — the name written to STEP, e.g. "login successful".
  - **when / and** — a field, a comparison, and a value. Add as many conditions as needed; every one must hold.
  - **Add a helper field** — extract a new value on the spot without leaving the panel.
- The panel shows what each referenced field captures from your sample ("= 200") and whether the rule as a whole matches, so a rule can be confirmed before closing.
- Comparison operators:

| Comparison | True when the captured value… |
|---|---|
| is | equals the value |
| is not | differs from the value |
| contains | contains the value anywhere |
| starts with | begins with the value |
| ends with | ends with the value |
| matches regex | matches the pattern (case-sensitive, exact control) |

- **WARNING:** All comparisons except "matches regex" **ignore case and surrounding spaces** — log casing is rarely dependable. Use "matches regex" when you need an exact pattern.

### How rules are applied
- Rules are checked **in the order listed** — the badge number is that order — and **the FIRST rule whose conditions all hold wins**. Put specific rules above general ones.
- If no rule matches, the plain STEP field's value is used unchanged. Compound steps are **purely additive** — adding them to an existing source type cannot break it.
- A rule with no resulting step, or no conditions, is **ignored** rather than applied to every event — a half-built rule can never relabel your data.
- The same rules apply to a manual ▷ run and a watchdog import — a live feed is labelled identically.
- Derived names are real step names: the import creates a STEPS definition — shape, colour, zero score — for "login successful" and "login failed" just as for any other step, so both appear as **separate nodes** in the process map with their own paths.
- **Locked fields** — a field referenced by a compound rule shows a **🔒 instead of its remove button**, and the row names the rules using it. Deleting it would leave those rules pointing at a missing field (they would quietly stop matching) — remove it from the rules first, then delete. **Renaming needs no such care: the rules follow the new name automatically.**
- **WARNING:** Changed rules only affect **FUTURE imports**; rows already written keep their step names. Importing the same file again **APPENDS** its events rather than replacing them — to re-apply changed rules to existing data, **delete the project first** (in the app's connection editor, Projects tab) and import again.
- **TIP:** A misconfigured rule usually shows up as a surprise in the console's **"Events skipped" KPI** or as unexpected nodes on the map. The Example JOURNEYS record in the wizard marks a compound-derived step with **"compound"** — check it before importing.

### Helper fields
- A value needed only for matching — an HTTP status, a result code, a queue name — does not belong in META. Map it on the **Helper tab**, or add one directly from a rule panel.
- Helper fields are extracted from every line and available to compound rules.
- **Written to NO database column** — all three META columns stay free for business attributes.
- Named like Metas; the name is what a rule references. Give each a distinct, meaningful name.
- **TIP:** Adding a helper from inside the rule panel also **wires it into the rule's first empty condition** — from "I need the status" straight to "status is 200" without switching tabs.

### Transaction bracket
- Rows are inserted inside a real database transaction, committed in **brackets**: commit once the configured number of rows has been written, then a final commit for the remainder. Set the bracket **per source** in the wizard (**Transaction bracket, default 5000 rows**). Applies to both manual runs and the watchdog.
- Larger bracket = more atomic, but the database holds more of the import open at once.
- Smaller bracket = commits steadily; if the import fails part-way, already-committed brackets stay in the database.
- **0 = one single transaction for the whole import** — all of it lands, or none of it.
- **TIP:** If a run fails, the bracket still open is rolled back; whatever was committed before remains. **The result message tells you how many events were written.**

### Watchdog — auto-import new lines
- A File source can run a **watchdog** (turn on in the source wizard, under the file path). It picks a **destination connection, project id and poll interval**. A background job watches the file and, whenever it grows, imports **only the newly-appended lines** — never the whole file again — so a continuously-written log streams into the database on its own.
- A **checkpoint per source file** (how far read + imported record count) means nothing is imported twice — **even across server restarts**. If the file is **truncated or replaced (rotated)**, the watchdog notices and re-reads from the start.
- **TIP:** The wizard shows the checkpoint status (records imported, last check, any error) and a **Reset checkpoint** button to force a full re-read. A source with the watchdog on is marked with a **👁** in the Sources list; its imports appear in the live pipeline like any other run.
- **WARNING:** The watchdog runs **headless** (no signed-in session), so its destination is stored with the source rather than picked each time. It uses that connection's saved credentials, so pick one you are assigned to and that points at the right schema — **the assignment is re-checked on every poll, and revoking it stops the watchdog**.

---

## 32. Pipeline Monitoring — 🔀 (audience: developer/admin only)
*Subtitle: "The live import flowchart and run history"*

### Ingestion KPIs
- The **Abstraction layer card** at the top summarises ingestion with the same KPI tiles the main app uses. They cover the **whole recorded history**, not just the last run:
  - **Manual imports** — runs you started with ▷ Run.
  - **Watchdog imports** — runs the background file watchdog started on its own.
  - **Last import** — how long ago the most recent run finished (or **"running…"** while one is in flight).
  - **Events pushed** — journey events written to the database.
  - **Events skipped** — source lines that could not be parsed into an event.
- **WARNING:** A non-zero "Events skipped" is **highlighted in orange**: usually the linked source type's regexes do not fit that log. Edit the source type and test it against a real line.
- **TIP:** The card also shows the **target schema, the run state**, and — behind the **Run log** button — the log lines of the most recent run. **The counts reset when you clear the run history.**

### The flowchart
- Below the KPIs the imports are drawn as one flowchart: **Source type → Source → Abstraction layer → Connection**. Nodes are **reused across runs** — every distinct source type, source and destination is a single node, with the Abstraction layer as the hub. The Source and Destination nodes show the **total number of rows imported**.
- Stage tinting (pastel): **source types violet, sources blue, the layer by its state, destinations teal**; the stage currently running gets a deeper wash.

### Live activity & colours
- While an import runs, a **dot travels the active path node-to-node** (like the individual-journey animation in the main app). Connections are coloured by their most recent run:
  - **Blue** — idle or completed.
  - **Green** — currently running.
  - **Red** — the last run on that path failed.

### History & layout
- The console keeps a **per-user history of every run** and folds it into the one growing flowchart, showing ingestion behaviour over time. It survives reloads and server restarts and is kept until you press **↺ Clear**.
- Nodes can be dragged to arrange freely; drag the **grip on the bottom edge of the canvas** to make the working area taller. Both the arrangement and the canvas height are **saved per user** and restored automatically; **⤢ Reset layout** returns to the automatic arrangement and default size.
- **TIP:** The run history, manual layout and canvas height are **stored in your browser, so they are per-device**.

---

## TOC structure & topic order (as exported)

Order in `HELP_TOPICS`: Overview, Database Setup, Connections, Users & Permissions, [Administration group], Chart Views, Filters, Filter Presets, Process Map, KPI Panel, Process Goodness, Process Similarity, Simulation, Conformance Check, Happy Path, Journey Sampling, AI supported Documentation, Process Notes, [Integration group], Configuration, Troubleshooting.

- **Admin-only "Administration" TOC sub-menu** (`ADMIN_TOPIC_IDS`): admin-interface, admin-tls, admin-users, admin-connections, admin-api, admin-directory, admin-logging, **backup**, admin-customize, admin-license. (Note: the Backup & Restore chapter is grouped under Administration even though the manual export/restore itself is a user-facing settings feature.)
- **Developer-only "Integration console" TOC sub-menu** (`INTEGRATION_TOPIC_IDS`): integration-console, integration-sources, integration-monitoring.

## Cross-cutting facts worth preserving in the manual
- Ports: main app **8080 (HTTP) / 8443 (HTTPS)**; admin **8090 / 8453**; Integration console = admin port + 10 → **8100 / 8463**.
- Environment variables mentioned in help: `PMW_RESET_LOCKOUTS=1` (clear all account lockouts on restart), `PMW_PASSKEY_RP_ID` + `PMW_PASSKEY_ORIGINS` (split-domain passkeys), `PMW_INTEGRATION_ALLOW_ANY_PATH=1` (disable file-import sandbox).
- Server-side directories: rotated logs `data/logs/`; scheduled backups `data/backups/`.
- Keyboard: **⌘/ or Ctrl+/** toggles Help; date-slider thumbs respond to arrow keys; Return submits the Event ID field.
- Timeouts/limits: 30 s query timeout (Statistics / Process Goodness → tile shows "—"); Process Similarity cap 500 variants/side (badge hidden past cap); login-page image ≤ ~3 MB; lockout default 3 attempts (0 = off); Max Steps per Journey default 60; transaction bracket default 5000 rows (0 = single transaction); default date window 30 days (0 = full range); notes pages of 5/10/20.