# Admin Interface — Documentation Notes (Process Mining Demonstrator, Web Edition)

Source: `/Users/dirk/Work/Process_Mining_Web/admin/pages.py` (all UI markup + client logic) and `/Users/dirk/Work/Process_Mining_Web/admin/server.py` (all endpoints, auth, messages), with defaults verified in `backend/app/config.py`, `backend/app/store/logs.py`, `backend/app/store/security.py`, `backend/app/licensing.py`, `backend/app/services/backup.py`.

---

## 1. General facts about the admin interface

- Runs on its **own port**: HTTP **:8090** (env `PMW_ADMIN_PORT`), HTTPS **:8453** (env `PMW_ADMIN_HTTPS_PORT`). The main app is :8080 HTTP / :8443 HTTPS (`PMW_FRONTEND_PORT` / `PMW_FRONTEND_HTTPS_PORT`). The integration console defaults to **admin port + 10**: :8100 HTTP / :8463 HTTPS (`PMW_INTEGRATION_PORT` / `PMW_INTEGRATION_HTTPS_PORT`).
- **Admins only.** First run seeds a local administrator **Administrator / Administrator** (username configurable via `PMW_DEFAULT_ADMIN_USER`). While that default password is active, the dashboard shows a persistent warning banner: "⚠️ The **Administrator** account is still using its default password. Change it now in **👤 Profile** (top right)."
- Session cookie `pmw_admin` (HttpOnly, SameSite=Lax, Secure on HTTPS). Cookie lifetime = the **admin idle timeout** when set (sliding window, refreshed on activity), otherwise an absolute **8 h** fallback (`PMW_ADMIN_SESSION_TTL`). There is additionally an absolute session lifetime cap; sessions minted before it existed are refused (one re-login). Admin and app session cookies are **not interchangeable** (audience-bound). **Log out** invalidates every outstanding session token for that user server-side (session-epoch bump), not just the cookie.
- Per-IP sign-in throttle on the login endpoints. When throttled: HTTP 429, message **"Too many failed attempts. Try again in about N seconds."**
- Unauthenticated `GET /health` returns `{"status": "ok"}`.
- All admin actions are written to the shared structured log (see Logging). Destructive actions (deletes, restores, clearing the log, token generation/revocation) are logged at **WARN** severity by design so they stand out.

### 1.1 Admin sign-in page

Visually identical to the main app's login panel; the only difference is the two-line title "Process Mining Demonstrator / Administration". Caption under the title varies by step: "Sign in to continue" → "Enter your authentication code" (2FA step) → "Set up two-factor to continue" (forced enrolment) → "Two-factor is on" (recovery-code display).

- Fields **Username** and **Password**; the **Sign in** button stays disabled until a username is entered; it shows a spinner during the POST.
- **🔑 Sign with Passkey** button appears only when the browser supports WebAuthn **and** the page is reached by a hostname (never by bare IP / single-label host — WebAuthn rejects those as RP ID); it is disabled until a username is typed. Failure text: "Passkey sign-in failed. Check the passkey is registered and still enabled." Passkey sign-in **skips the 2FA code step**.
- **Directory-server LED**: shown only when LDAP is configured — green/red dot with "Directory server available" / "Directory server unavailable" (cached probe, 20 s TTL; never blocks the page).
- Inactivity notice (after idle auto-logout): "You were signed out due to inactivity."
- Failed sign-in error: **"Invalid credentials, or the account is not an administrator."** (or an account-lockout-specific block message when applicable). Directory accounts can sign in here only when "Also allow directory sign-in to this admin interface" is enabled *and* the account has been promoted to admin; local admin accounts always work (break-glass).
- **2FA step** (if TOTP is enrolled): field label "Authentication code", placeholder "6-digit code or a recovery code", button **Verify**; helper text "Enter the 6-digit code from your authenticator app, or one of your recovery codes." Wrong code → "Incorrect code. Try again." (password does not have to be re-entered; retry allowed). Important: a wrong 2FA code is throttled per-IP only and **never counts toward account lockout** (the password was already proven).
- **Forced 2FA enrolment** (2FA allowed for the account but not yet configured): sign-in halts after the password; the page shows a QR ("Two-factor is required for your account. Scan this with an authenticator app (Google Authenticator, 1Password…), then enter the 6-digit code."), a "6-digit code" field and **Confirm & sign in**. Wrong code: "That code didn't match. Try again." (same QR/secret preserved). Expired flow: "Your sign-in session expired. Please start again." On success the user is signed in and shown their **recovery codes once**, with "**Save your recovery codes.** Each works once if you lose your authenticator; they won't be shown again." and a "Continue to the admin panel" link.

### 1.2 Top bar (always visible on the dashboard)

- Theme segmented control (◐ System / ☀ Light / ☾ Dark) — stored per-browser (localStorage), applied before first paint.
- "Signed in as **<username>**".
- **❔ Help** — opens a help overlay with topics: Admin Interface, TLS / SSL, Users & Sign-in, Database Connections, Rebuild from a script (API), Directory (LDAP), Logging, Backup & Restore, Customize, License & Demo Mode. (Note for the manual: its "Admin Interface" topic lists the tabs but omits the Integration tab — minor drift.)
- **👤 Profile** — overlay for the signed-in admin's own account (see 1.3).
- **Log out** button.

### 1.3 Profile overlay (the admin's own account)

Intro: "Your own admin account — password, passkeys and two-factor. These protect both this admin interface and the main app."

**Password** — fields "New password" / "Confirm", button **Change password**. Client errors: "Enter a new password." / "The passwords don't match." On success, **every other session of this admin is invalidated** (session-epoch bump); the current session is re-issued so the admin is not signed out. Logged: "changed their password — other sessions invalidated".

**Passkeys** — "Sign in with Touch ID, Windows Hello, or a security key instead of your password (which always remains a fallback). Passkeys must be enabled for your account (Users tab) before you can add one; the same passkey works on both the app and this panel." States/messages:
- "Checking passkeys…" (loading), "This browser does not support passkeys.", "Passkeys need a hostname, not an IP address. Reach this panel by its name over HTTPS — e.g. its '.local' name — instead of its IP to add or use one.", "Passkeys are not enabled for your account — enable them in the Users tab first.", "Passkeys are enabled for your account.", "No passkeys registered yet."
- Add: "Passkey name" field (placeholder "e.g. MacBook Touch ID"), button **Add a passkey**; each registered passkey lists name + "Added <date>" + **Remove**. Special errors: duplicate → "A passkey for this account already exists on this device. If it isn't listed above, remove it in your device's passkey settings and try again."; IP host → "Passkeys need a hostname, not an IP address — reach this panel by its name over HTTPS."

**Two-factor authentication** — TOTP on top of the password for both the admin interface and the main app. States: "Checking two-factor…", "Two-factor is not enabled for your account — enable it in the Users tab first.", "Two-factor is off for your account.", "Two-factor is on. N recovery code(s) left."
- **Set up authenticator**: shows a QR (180 px), "Can't scan? Key: <secret>", a "6-digit code" field, **Confirm** / **Cancel**. Errors: "Setup expired. Start again." / "That code didn't match. Try again." Success shows the recovery-codes panel ("Save your recovery codes…" + Copy codes / Done).
- **Regenerate recovery codes**: issues a fresh set (shown once), invalidating the old ones.
- **Turn off**: browser prompt "Enter your current authentication code (or a recovery code) to turn off two-factor:" — the current code is required so a hijacked session can't strip 2FA; wrong code → "Enter your current authentication code to turn off two-factor." (throttled per-IP).

---

## 2. Tabs — exact UI order

Tab strip order: **App Control** (selected by default) · **TLS / SSL** · **Users** · **Database Connections** · **Directory (LDAP)** · **Logging** · **Backup** · **Customize** · **Integration**.

---

## 3. App Control tab

Four cards, in order:

### 3.1 App Control (restart)

- Caption: "Operational controls for the running servers."
- Button **↻ Restart app server** (primary; tooltip "Rebind the app + admin listeners with the current TLS settings"). Side note: "Rebinds the main application and this admin interface in place with the current TLS mode & active certificate — no terminal needed."
- Confirm dialog: "Restart now? — The app AND this admin interface rebind their HTTP/HTTPS listeners with the current TLS settings. Anyone using the app will briefly disconnect, and if you changed the TLS mode this admin page may move between :8090 (HTTP) and :8453 (HTTPS)."
- Info banner (always visible): "TLS mode and certificate changes (in the **TLS / SSL** tab) take effect on restart. This restarts **the app, the integration console and the admin interface** (they share the certificate), so this page may briefly drop — and if you changed the mode, the admin moves between HTTP :8090 and HTTPS :8453; reconnect there if it stops responding."
- Mechanics: signals (SIGHUP) the app launcher, then the integration-console launcher (best-effort — it may not be running), then the admin's own launcher (best-effort — the response may race the teardown). Success shows: "Restart signalled. Listeners rebind with the current TLS plan; reconnect on the new address if this page stops responding." and the toast "Restarting (app pid N, admin pid M)…".
- Errors (exact): 409 "The app server is not managed by the launcher (no PID file). Start it with `./run.sh`, then try again."; 409 "The app server process is not running."; 500 "Invalid PID file."; 500 "Could not signal the app server: <os error>".

### 3.2 License

- Caption: "The compute backend requires a valid license. Without one it runs for a short grace period and then stops. Upload the `license.json` you were issued to apply it."
- **Status banner** (loads as "Checking license…"), colour-coded:
  - green (valid): "Licensed to '<name>', valid until <date>." plus sub-line "Licensed to <name> · expires <date> · issued <date>";
  - orange (expired): "License for '<name>' expired on <date>.";
  - red (invalid/missing): e.g. "No license installed.", "License signature is not valid.", "License file is not valid JSON.", "License file is missing 'license' or 'signature'.", "License signature is malformed.", "License has no valid expiry date.", "License file could not be read: …".
- **Upload license**: file input (accepts `.json`), button **Upload license**. Note next to it: "The signature is verified before the license is stored." A forged/corrupt file is rejected with HTTP 400 and the specific reason; **nothing is stored** on rejection. Oversize (>100,000 base64 chars) → 413 "License file is too large."; bad base64 → "Invalid file content." Success: "License installed. The backend applies it within a few seconds." (the backend polls; no restart needed).
- **Delete license**: confirm dialog "Delete the installed license? — The compute backend drops to Demo Mode and stops after the grace period unless a new license is applied." Results: "License removed — the backend is now in Demo Mode." or "No license was installed."
- **Demo / grace semantics** (admin must know): the demo grace window is granted **once per installation** — the first unlicensed run stamps a deadline (default **30 minutes**, env `PMW_LICENSE_GRACE_SECS`; marker `data/demo_grace.json`). Deleting/uninstalling a license cannot reset it. When the grace expires the **compute backend stops**; the **admin interface keeps working** so a license can always be applied here. Uploading a valid license during the grace period cancels the shutdown. License file lives at `data/license.json`; licenses are Ed25519-signed JSON.

### 3.3 Admin session

- "Automatically sign out of **this admin interface** after a period of inactivity. This is separate from the main app's auto sign-out (set in the Users tab)."
- Control: "Auto sign-out after [N] minutes of inactivity" (number, 0–1440) + **Save**. Hint: N>0 → "You are signed out of this admin after N min idle."; 0 → "Disabled — the admin session never times out on inactivity."
- Behaviour: client-side idle timer (mouse/keyboard/scroll/touch resets it) plus a sliding server-side cookie window; on timeout the browser is sent to the login page with the "signed out due to inactivity" notice.

### 3.4 Timezone

- "The timezone used for all admin timestamps — the log viewer and exported logs, backup times and the backup schedule (e.g. 'daily at 02:00' fires at 02:00 here). Leave as *Server local* to follow the server's own clock. The main app shows each user their own browser's local time."
- Control: **Display timezone** select — "Server local (default)", "UTC", then every IANA zone — + **Save**. A live preview line shows "Current time: … ". Invalid zone → 400 "Unknown timezone: '…'". Takes effect **immediately** (no restart): log rendering, exported logs, backup file timestamps and the cron matching for scheduled backups all switch at once.

---

## 4. TLS / SSL tab

### 4.1 TLS / SSL card (mode)

- "Choose how the main application (the GUI server) accepts connections."
- Segmented control with three modes (no separate default marker in the UI; the current stored mode is highlighted): **Off (HTTP only)** · **Optional (HTTP + HTTPS)** · **Required (HTTPS only)**. Button **Save mode** → toast "TLS mode saved — restart in App Control to apply".
- Endpoint plan is displayed after save/load: "HTTP endpoint" and "HTTPS endpoint" rows, each either a clickable URL (`http://<host>:8080/`, `https://<host>:8443/`) or "disabled".
- Warning when the mode needs a certificate but none is active: **"No active certificate — HTTPS cannot start. Generate or upload one and activate it below."** Fallback behaviour (important): if a mode requires HTTPS but no certificate is active, every server **falls back to HTTP** on restart so nothing becomes unreachable.
- Footer: "Mode & certificate changes take effect after a restart — use **↻ Restart app server** in the **App Control** tab." The app, the admin interface and the integration console all follow the same mode and share the active certificate.
- Help adds: "Keep the active certificate valid — an expired certificate makes HTTPS clients refuse to connect."

### 4.2 Certificates card

- Table columns: **Name** (active one gets a green "active" pill), **Subject**, **Type** ("Self-signed" / "CA-signed"), **Expires**, and per-row actions: **Activate** (hidden on the already-active cert), **Download** (PEM as `<Name>.crt`, spaces → underscores), **Delete** (confirm: `Delete certificate "<name>"?`; logged at WARN). Empty state: "No certificates yet. Generate or upload one below."
- **Generate self-signed** (left column): Name (placeholder "e.g. Internal 2026"), Common name / host (placeholder "processmining.example.com"), Additional SANs (comma-separated DNS / IPs; placeholder "localhost, 127.0.0.1"), Valid for (days) — default **825**, min 1, max 3650 —, Key size select **2048** (default) / 3072 / 4096, checkbox **Activate after generating** (default off), button **Generate**. Toast "Certificate generated".
- **Upload certificate** (right column): Name (placeholder "e.g. Corporate CA"), Certificate (PEM) textarea, Private key (**PEM, unencrypted**) textarea, checkbox **Activate after uploading** (default off), button **Upload**. Each PEM field is capped at 200,000 characters (oversize is rejected). Toast "Certificate uploaded". Validation errors from the cert service surface as the toast text.
- Activating merely marks the cert; it is applied on the next restart. Generation/upload/activation logged at INFO with operation `tls`; deletion at WARN.

---

## 5. Users tab

Header: "Only enabled users will be allowed to sign in to the main application."

### 5.1 Global access controls (three banners)

1. **Require sign-in for the main application** (checkbox, applies instantly). Hint: on → "Users must sign in."; off → "The app is open — no sign-in required." With it off there is **no user identity** — per-user settings and filter presets share one profile.
2. **Auto sign-out after [N] minutes of inactivity** (0–1440) + **Save** — this is the **main app's** idle timeout. Hint: N>0 → "Idle sessions are signed out after N min."; 0 → "Disabled — sessions never time out on inactivity."
3. **Disable an account after [N] failed sign-in attempts** (0–100) + **Save**. Hint: N>0 → "Accounts (incl. the Administrator) are disabled after N failed sign-ins."; 0 → "Disabled — accounts are never locked on failed sign-ins." Nuance: the built-in Administrator's failures are **counted but it is never auto-locked** (it is the break-glass account). Locked accounts show a "locked" pill (tooltip "Disabled after too many failed sign-ins — Unlock to restore.") and are restored with **Unlock**. Emergency: restarting with env `PMW_RESET_LOCKOUTS=1` resets lockouts.

### 5.2 List controls

- Filter chips **All / Local / LDAP**, each with a live count. Search box "Search users by name…" matches username or display name. Empty result: "No matching users."
- **Master row** above the list: caption "Passkey and two-factor are optional alternatives/additions to the password (which always works)." Then "All users:" with two checkboxes — **Passkey** (tooltip "Allow every user to enrol and sign in with a passkey") and **2FA** (tooltip "Allow every user to set up two-factor (TOTP)"). Each is checked only when *every* user currently has that permission; toggling applies to **all users at once**. Toasts: "Passkeys allowed/disabled for all users", "Two-factor allowed/disabled for all users".

### 5.3 Per-user cards (scrollable list, two lines per user)

Line 1: username (+ smaller display name for directory users), source pill **LDAP** or **local**, role badge, access pill (**enabled** green / **disabled** red / **locked** red), and the per-user **Passkey** and **2FA** checkboxes (same tooltips as the master row).

Role badge logic: the base level is admin, else power, else user; admins always show a second segment (power or user); the **dev** segment is appended as an add-on. Multi-role users get a single animated gradient pill (e.g. `admin·power`, `admin·user·dev`); a lone role is a plain pill. Tooltip lists the roles verbatim, e.g. "Roles: administrator, power user (manages own connections), developer (integration console)" or "Regular user".

Line 2: "Last sign-in: <date or —>" plus action buttons:
- **Disable** / **Enable** / **Unlock** (Unlock is the Enable action shown when the account is lockout-disabled).
- **Make admin** / **Remove admin** — grants/revokes access to this admin interface.
- **Make power** / **Remove power** — power users manage their own connections and get the advanced-analysis views (Conformance Check, Happy Path, Simulation).
- **Make developer** / **Remove developer** — grants the dev role for the Integration console (logged: "granted/revoked the Developer role for '<user>'").
- **Reset password** — **local users only** (hidden for LDAP users); a browser prompt "New password for <user>:" collects the new password. Empty passwords rejected ("Password is required.").
- **Delete** (danger) — confirm `Delete user "<name>"?`.

**Built-in Administrator protections** (both hidden in the UI and enforced server-side): cannot be disabled ("The built-in Administrator account cannot be disabled."), cannot be demoted ("The built-in Administrator account must remain an administrator."), cannot be deleted ("The built-in Administrator account cannot be deleted."). Its card shows only the Passkey/2FA toggles, Reset password, an **Unlock** button when locked, and the note "built-in admin" (tooltip "The built-in administrator cannot be disabled, demoted or deleted.").

### 5.4 Add a user (collapsed "Add a user" section)

Fields: Username, Password, checkbox **Administrator**, button **Create user**. Errors: "Username is required.", "Password is required.", "A user named '<x>' already exists." (Power/Developer are granted afterwards from the card buttons; there is no checkbox for them at creation.)

### 5.5 Passkey / 2FA semantics an admin must know

- **Passkey allow** (per-user or all-users): permits enrolment and passkey sign-in in both the app and the admin panel; the password always remains a fallback. **Turning the permission off blocks passkey sign-in immediately.** Passkeys need a secure context (HTTPS or localhost) and a real hostname (never an IP — enrolment fails with "the effective domain is not a valid domain" and the controls are hidden when an IP is detected). For split app/admin sub-domains set `PMW_PASSKEY_RP_ID` to the shared parent domain and list origins in `PMW_PASSKEY_ORIGINS`.
- **2FA allow** (per-user or all-users): enabling makes two-factor **mandatory** for that user — if not yet configured, their next sign-in (app or admin) stops after the password and **forces enrolment**; they cannot bypass it by not enrolling. Afterwards each password sign-in asks for a current code or a recovery code; a passkey sign-in skips the code. Turning 2FA off for a user is the **reset path** when they lose their authenticator: untick 2FA so they can sign in with just their password and re-enrol. Users cannot turn their own 2FA off without their current code. The TOTP secret is stored encrypted; recovery codes only as hashes.
- LDAP users appear here after their first sign-in (auto-created as plain, enabled users) and can be granted any role and Passkey/2FA permissions like local users.

---

## 6. Database Connections tab

Header: "Define a database (and optional LLM) server, then assign it to the users who may use it. Each user sees only the connections assigned to them in the main application."

### 6.1 Connection list

Table columns: **Name** (bold, with the optional comment underneath), **Host** (`host:port`), **LLM** (green "yes" pill when an LLM URL or key is set, else "—"), **Assigned to** (comma-separated usernames or "nobody"), and **Edit**. Empty state row: "No connections defined yet." Button **+ New connection** opens the editor with defaults: Port **8563**, Certificate mode **Verify**, Minimum RSA key size **2048**.

### 6.2 Connection editor — inner tabs Database / LLM / Projects

The **Projects** tab button is disabled for an unsaved connection (tooltip "Save the connection first to list its projects").

Footer buttons (all tabs): **Save** (primary), **Test connection**, **Cancel**, and **Delete** (danger, only for saved connections; confirm `Delete connection "<name>"?`; logged at WARN). Saving with an empty name → toast "Name is required." After save the editor reloads with fresh data (the Projects tab unlocks).

#### Database sub-tab

Left column ("Database"):
- **Name** (placeholder "e.g. Production Exasol") — required.
- **Comment** (placeholder "optional").
- **Host** (placeholder "db.example.com") and **Port** (default 8563).
- **Username** and **Schema** (placeholder "optional").
- **Password** — placeholder bullets; when a password is stored the label shows "(set — leave blank to keep)". Blank keeps the stored secret; typing replaces it.
- **Use TLS** checkbox; when on, reveals: **Certificate mode** select — "Verify (system trust store)" (default) / "Pin fingerprint" / "Accept any (insecure)"; **Fingerprint (SHA-256)** (placeholder "optional"); **Minimum RSA key size** (default 2048).

Right column ("Assign to users"): a checkbox grid of every username. Empty state: "No users to assign." Only assigned users see the connection in the main app.

**Create schema & tables banner**:
- Button **Create schema & tables**; checkbox **Also build pre-materialized transitions after provisioning** (default off).
- Explanation text: "Creates the schema named above and the process-mining tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don't exist, using the credentials entered here. This requires a database account permitted to **CREATE SCHEMA** and **CREATE TABLE** — only your database administrator can grant those rights; this application cannot."
- Requires a schema name (toast "Enter a schema name first."). Progress "Creating…"; success (green): "Created: <objects>" optionally followed by "· transitions built (N pairs)" or "· transitions build failed: <error>"; failure (red) shows the error or "Could not create the schema." When built at provisioning time the TRANSITIONS_RAW table exists but is empty until JOURNEYS is loaded.

**Use pre-materialized transitions banner**:
- Checkbox **Use pre-materialized transitions** (bold). Explanation: "Reads the process map from a prebuilt `TRANSITIONS_RAW` table instead of running the windowed query live — much faster for interactive filtering on large logs. It falls back to the live query until the table is built, so **rebuild it after each load of `JOURNEYS`**."
- Button **Rebuild now** (disabled until the connection is saved; tooltip "Save the connection first"). Status text: "Not built yet — the live query is used until you rebuild." / "Last built: <date> · N pairs." / red "Last rebuild failed: <error>". While running: "Rebuilding… (this runs the pairing once and may take a while)"; result "Built N pairs." or the error.
- Rebuilds of the **same connection never overlap** — a second call gets 409 "A rebuild is already running for this connection."

**Rebuild from a script (API)** — collapsible section inside the same banner:
- Purpose: "Let a scheduler (cron / ETL) rebuild *this connection* right after loading its JOURNEYS, without an admin login. The token below is scoped to this connection only, and calls are rate-limited."
- Status text: "save the connection first" / "no token set" / "a token is set for this connection".
- **Generate / rotate token** — confirm: "Generate a new token for this connection? Any existing token stops working." The new token is shown **once**: "New token (copy it now — it is not shown again):". Only its hash is stored. Logged at WARN.
- **Revoke** (danger; only shown when a token is set) — confirm: "Revoke this connection's token? A scheduler using it will stop working." Logged at WARN.
- Copy-able curl example (📋 button, toast "curl command copied"); shows the real token while visible, otherwise `<token>`:
  ```
  curl -k -X POST \
    -H "Authorization: Bearer <token>" \
    "https://<admin-host>:8453/api/connections/<connection-id>/rebuild-transitions"
  ```
  Footnote: "The token is shown once — copy it now; only its hash is stored. … `-k` skips the self-signed TLS check."
- Token semantics: a token only ever authorises **its own connection's** rebuild endpoint; token-triggered rebuilds have a **60-second per-connection cooldown** (429 "Rebuild throttled — try again in Ns."); admin-session calls are never throttled. The endpoint uses the **stored** credentials, so the caller never handles them. Rebuild outcome (rows or error) is recorded per connection and shown as the "Last built" status.

#### LLM sub-tab ("LLM (optional)")

- **Server URL** (placeholder "https://api.openai.com/v1"), **Model** (placeholder "gpt-4o"), **API key** (bullet placeholder; hint "(set — leave blank to keep)" when stored). An OpenAI-compatible endpoint per connection.

#### Projects sub-tab

- Header "Projects in this schema" + **↻ Refresh**.
- Caption: "Projects stored in `<schema>` (or "(no schema)"), with their journey and event counts. **Deleting a project clears its rows from every table (PROJECTS, JOURNEYS, STEPS, METAS, NOTES, TRANSITIONS_RAW). This cannot be undone.**"
- States: "Save the connection first to list its projects." (unsaved) / "Open the Projects tab to load them." / "Loading projects…" / "No projects found in this schema." / a red error message ("Could not read projects." or the DB error).
- Table: **Project** (title bold; the raw project id as a sub-line when it differs), **Journeys** (right-aligned, thousands-separated), **Events** (right-aligned), **Delete** (danger).
- Delete confirm: `Delete project "<id>"?` + "This clears its rows from PROJECTS, JOURNEYS, STEPS, METAS, NOTES and TRANSITIONS_RAW in this schema. This cannot be undone." Success toast: "Project deleted (N events)". Failures surface the DB error as a toast. Uses the stored credentials; logged at WARN.

#### Test connection (footer)

Results render as banners: "Database: connection OK" or "Database: <error>"; when an LLM URL is filled in additionally "LLM: reachable — N models" / "LLM: <error>" / "LLM server not reachable." The test uses the password/key **as typed** (a blank field tests without them — it does not fall back to stored secrets). All tests are logged (operations `connection` / `llm-test`).

---

## 7. Directory (LDAP) tab

Header: "When enabled, the **main application** also accepts sign-ins from an LDAP directory (search + bind). Directory users are created here automatically on first login as plain, enabled users — grant them a role or database connections like any other user. Local accounts always keep working."

Top banner:
- Checkbox **Enable directory sign-in for the main app**.
- Checkbox **Also allow directory sign-in to this admin interface**. Note: "A directory account can only reach the admin interface once it has been promoted to **admin** in the Users tab. Local administrators always work regardless of this setting." (Admin is never granted from the directory itself.)

**Server** column: **Server URI** (placeholder "ldap://dir.example.com:389 or ldaps://dir.example.com:636"); **Use StartTLS (upgrade a plain ldap:// connection)** checkbox (default off); **Verify server certificate** checkbox (default **on**); **CA certificate (PEM, optional)** textarea. Lab note: "For a lab you can use a plain ldap:// URI with StartTLS off — the password is then sent in the clear." Button **Test server connection** → "Server reachable — service bind OK" or a warning with the error.

**Service account & search** column: **Bind DN** ("read-only service account; blank = anonymous"; placeholder "cn=readonly,dc=example,dc=com"); **Bind password** (hint "(set — leave blank to keep)" when stored — tests with a blank field reuse the stored password); **Base DN** (placeholder "ou=people,dc=example,dc=com"); **User filter** ("{username} is substituted"; default `(uid={username})`); **Login attribute** (default `uid`), **Email attribute** (default `mail`), **Name attribute** (default `cn`).

**Test a user login** banner: "resolve a directory account and verify its password (search + bind). Use *Test server connection* above to check the server alone." Fields Test username / Test password, button **Test**. Results, stacked: "Service bind: OK" or "Service bind failed: <error>"; "Search matched N entry/entries (<DN>)" (info when exactly 1, warning otherwise); "User login: OK — <username> (<dn>)" or a warning ("User login failed" / error).

**Save** button persists everything; toast "Directory settings saved". All saves and tests are logged (operation `ldap`).

---

## 8. Logging tab

### 8.1 Config banner

- **Max level logged** select (options INFO / USAGE / WARN / ERROR / DEBUG; default **ERROR**) and **New file after [N] MB** (1–1000; default **5** MB; server enforces a 50 KB floor) + **Save** (toast "Logging config saved").
- Caption: "Records this severity and everything above it in the ladder (INFO → USAGE → WARN → ERROR → DEBUG; DEBUG logs everything)."
- Severity ladder semantics (must be stated precisely): the ladder order is **INFO < USAGE < WARN < ERROR < DEBUG**, and the setting is *cumulative from the top*: choosing a level records that severity **and every level before it** in the ladder. So INFO records only INFO; USAGE records INFO+USAGE; WARN adds WARN; the default **ERROR** records INFO+USAGE+WARN+ERROR (everything except DEBUG); **DEBUG records everything** (including verbose SQL traces).

### 8.2 Filter / action row

- **Severity chips** (one per level, multi-select toggles). Display default: **INFO and USAGE selected**; WARN/ERROR/DEBUG hidden until toggled. Selecting all levels equals "show all". This is a *view* filter only — it does not change what is recorded.
- **Client IP** text filter; **All operations** dropdown (populated from the operations present in the log — includes login, logout, page, config, license, tls, connection, llm-test, ldap, backup, customize, restart, materialize, sql); **All tags** dropdown; free-text **"Search message (regex / wildcards)…"** (debounced ~300 ms). All filters span the entire log; any filter change returns to page 1.
- **↻ Refresh** · **⬇ Download** (exports the *currently filtered* view as `pmw-log.log`, up to 5000 entries) · **Clear** (danger; confirm: "Clear the live log? — This empties the current log (rotated archive files are kept)."; the clear itself is then logged at WARN).

### 8.3 Table, popup, paging

- Columns: Date, Time, Severity (colour pill: INFO blue, USAGE green, WARN orange, ERROR red, DEBUG grey), Tag (neutral pill or "—"), Client IP, User, Message. Every row is exactly one line — long messages are ellipsized; **clicking a row opens the full entry** in a "Log entry" popup (fields: Date, Time, Severity, Client IP, User, Operation, Tag, then the message). SQL trace entries (operation `sql`) are **pretty-printed** in the popup and their execution time (from the "SQL (12.3 ms):" prefix) is shown as an "Execution time" field. Esc or Close dismisses.
- Empty state: "No matching log entries."
- Pager: "Per page" 10 / **25** (default) / 50 / 100; « First / ‹ Prev / Next › / Last »; "start–end of total" and "Page X / Y"; "No entries" when the filter matches nothing.

### 8.4 Tags, archive, sources

- **Tags** are cross-cutting labels independent of operation/severity: **DATA** (data-load events), **SQL** (SQL traces), **BACKUP/RESTORE** (every backup/restore action). The tag filter dropdown lists whichever tags exist in the log.
- **Rotation/archive**: once the live log passes the configured size it is rotated out to `data/logs/pmw-<timestamp>.log`; only the **newest 10** archives are kept. "Clear" empties only the live log, never the archives.
- The log is shared — written by the app, the admin interface and the integration console alike; the display timezone (App Control → Timezone) governs all timestamps in the viewer and in downloads.

---

## 9. Backup tab

### 9.1 Backup card

Intro: "A backup captures **everything except the event data itself** — connections, filter presets, happy paths, target norms, node layouts, LLM prompt templates and app preferences — as a single JSON file (byte-compatible with the app's backup format). Download one now, or have the server write encrypted backups automatically on a schedule. The options and password below apply to both."

- Checkboxes (all default **checked**): **Include database usernames**, **Include database passwords**, **Include LLM API keys**.
- Plain-text warning (appears when secrets are included and no password is typed or stored): "⚠ Secrets will be written in plain text unless you set an encryption password."
- **Encryption password (AES-256-GCM)** field. Hint: "(set — leave blank to keep it; also reused for downloads)" when a password is stored; "(none set — required for automatic backups)" otherwise.
- Standing warning: "For automatic backups the password is stored **encrypted** on the server so they can run unattended. Keep it safe — a backup can only be restored with it."
- **⬇ Download backup** — downloads `ProcessMining-Backup-YYYY-MM-DD.json`; a blank password field silently reuses the stored automatic-backup password (so downloads are encrypted too once a schedule password exists).
- **Run backup on server now** — writes a backup to `data/backups/` immediately using the typed password (or the stored one). Toast "Backup written on server: <file>". Error without any password: "Set a backup password first."

**Automatic backups** (same card, below a divider): "Written on a schedule while the admin server is running, saved under `data/backups/`; older files are pruned beyond the retention count."
- **Enable automatic backups** checkbox. Enabling without a stored/typed password → 400 "Set a backup password before enabling automatic backups."
- **Frequency** select: Every hour / Every day / Every week / Every month / Custom (cron). Depending on the choice: **Hour** (0–23), **Minute** (0–59), **Weekday** (Sunday–Saturday), **Day of month** (**1–28 only** — valid in every month), or a **Cron expression** field ("minute hour day-of-month month weekday", placeholder `0 2 * * *`).
- Live line: "Runs: `<cron>` — <human summary>" (e.g. "Every day at 02:00", "Every Monday at 02:00", "On day 5 of each month at 02:00", "Custom schedule"). Invalid cron on save → 400 "Invalid schedule: <reason>".
- **Keep newest backups** (retention; min 1, default **30**).
- **Save schedule** → toast "Backup schedule saved". Status line: "Last backup: <when> — <file> (N KB)" (plus "· manual" for run-now), red "Last attempt failed: <error> — <when>", or "No backup has run yet."
- Mechanics an admin must know: the scheduler runs **inside the admin server process** — no backups are written while it is down. It checks every 15 s and fires at most once per minute when the cron matches the **display-timezone** wall clock (so "daily at 02:00" means 02:00 in the configured admin timezone). Files are named `pmw-backup-YYYYMMDD-HHMMSS-<microseconds>.json`; retention pruning deletes the oldest beyond the keep-count. A scheduled tick without a stored password records the failure "No backup password is set."

### 9.2 Restore card

Intro: "Load a backup file, review its contents, then choose what to restore. This overwrites the corresponding settings."

- **Backup file** input (`.json`) — choosing a file inspects it automatically. **Password (if the backup is encrypted)** field + **Inspect** button (re-inspect after typing the password).
- Errors (shown in a warning banner): "This backup is encrypted — enter its password and Inspect again."; decryption failures (wrong password); "The backup file format is invalid or corrupted."; "Backup file is too large." (cap ~18 MB decoded); "Invalid file content."; toast "Choose a backup file first".
- **Backup contents** summary: "Created: <date>", "Connections: N", "Projects with settings: N", "Includes: usernames|—, passwords|no passwords, API keys|no API keys", and — critically — "**Overwrites:** <names of the connections that will be replaced>".
- **Restore** option checkboxes (all default checked): App settings & preferences · Connections & servers · Usernames · LLM API keys · Database passwords · Saved node layouts · Target norms · Happy paths · Filter presets.
- **Restore** button (danger). Confirm: "Restore the selected items from this backup? — This overwrites the current settings." Toast "Backup restored".
- Logging (all tagged **BACKUP/RESTORE**): exports at USAGE with the include-set and whether the file was "encrypted" or "PLAINTEXT"; inspects at USAGE; restores at **WARN** listing the chosen options; every failure at WARN/ERROR with the reason.

---

## 10. Customize tab

Header: "Branding and appearance for the application and this admin interface. More options to come."

**Login Page** section — "Background for both sign-in pages (the main app and this admin interface). The default keeps the built-in theme colour, which follows light / dark mode."

- Radio options:
  - **Default theme colour** (the default).
  - **Solid colour** — reveals a colour picker plus a hex field (`#rrggbb`; the two stay in sync). Server validation: "Color must be a #rrggbb hex value".
  - **Background image** — reveals a file input. Accepted: **PNG, JPEG, GIF, WebP or SVG** — "or just **drag an image onto the preview below**". Client-side handling: files over 30 MB are rejected ("Image file is too large (max 30 MB)"); raster images are scaled to a 2560 px long edge and re-encoded (WebP, JPEG fallback) so any photo fits; **SVG is kept as-is and may be animated**. Server-side stored-image cap ~3 MB ("Image is too large (max ~3 MB)"). Other validation: "Choose a background image first" / "Choose a valid background image first". After picking: toast "Image ready — click Save to store it".
- **Preview** box (drop target; shows a mock "Sign in" panel over the chosen background).
- **Save** → result text "Saved — new sign-ins use it immediately." and toast "Login background saved". No restart needed — applies to the next render of either sign-in page.
- Behaviour note: over a background **image** the sign-in panel becomes 50 % translucent so the image shows through; a colour/default background keeps the panel solid.
- Changes are logged (operation `customize`), naming the new background ("a solid colour (#…)", "an uploaded background image", "the default theme colour").

---

## 11. Integration tab

Card **Integration console**:

- Description: "A separate surface for configuring data sources, reachable only by **power users**, **developers** and **admins**. Grant the Developer role per user in the **Users** tab." *(Caution for the manual writer: the Help overlay's Users topic instead says "Admins may enter it too; power users may not." — the two on-screen texts contradict each other on power-user access; verify against the integration server before printing.)*
- Checkbox **Enable the integration console**. Toggling toasts "Integration console enabled — restart to apply" / "Integration console disabled — restart to apply" — the change is stored immediately but **only takes effect after ↻ Restart app server** (App Control tab).
- Status area: pill "launcher running" or "launcher not detected" (best-effort, from the PID file), then the endpoints: "HTTP: `http://<host>:8100`" and "HTTPS: `https://<host>:8463` (when TLS is optional or required)" (ports = admin ports + 10 by default; env-overridable).
- Footer: "The console follows the same TLS mode & certificate as the app and this admin interface (change them in the **TLS / SSL** tab). Enabling/disabling and TLS changes take effect after **↻ Restart app server** in the **App Control** tab."
- The restart in App Control fans out to all three launchers: the app, then the integration console (best-effort — it may not be running), then the admin interface itself.

---

## 12. Cross-cutting gotchas & warnings summary (for the manual's call-out boxes)

1. **Restart fan-out**: one Restart button rebinds the app, the integration console *and* the admin interface. Users get briefly disconnected; if the TLS mode changed, the admin URL itself moves between `http://…:8090` and `https://…:8453`.
2. **TLS with no active cert**: HTTPS-requiring modes silently fall back to HTTP after restart so nothing becomes unreachable — the TLS tab warns "No active certificate — HTTPS cannot start."
3. **Project delete** wipes the project's rows from **PROJECTS, JOURNEYS, STEPS, METAS, NOTES and TRANSITIONS_RAW** — irreversible; the events count in the toast confirms scale.
4. **Materialized transitions go stale**: rebuild after every JOURNEYS load; until built (or after a failed build) the app silently uses the slower live query.
5. **Rebuild token shown once**; hash-only storage; rotation kills the old token instantly; token calls have a 60 s per-connection cooldown; `-k` in the sample curl is only for self-signed certs.
6. **2FA-allow is mandatory-2FA**: ticking the box forces enrolment at next sign-in; unticking is the recovery path for a lost authenticator. Wrong 2FA codes never lock accounts; wrong passwords can (except the built-in Administrator, which is never auto-locked).
7. **Backups exclude the event data** (the mined journeys/steps live only in the customer database) and can contain plaintext secrets unless a password is set; the automatic-backup password is stored encrypted server-side and is **required** to restore — losing it makes those backups unreadable.
8. **Restore overwrites** — the summary explicitly names which connections will be overwritten; the option checkboxes are the only granularity.
9. **Timezone setting** changes what "02:00" means for the backup schedule and how all admin timestamps render — immediately, no restart.
10. **Demo grace is one-time per installation** (default 30 min): once spent it never resets by deleting the license; the admin panel stays reachable after the backend stops so a license can always be uploaded.
11. **Log level DEBUG** records everything including full SQL traces — sizeable; the live log rotates at the configured MB and only the newest 10 archives are kept.
12. **Passkeys** require HTTPS (or localhost) *and* a real hostname; controls hide themselves when the panel is reached by IP.