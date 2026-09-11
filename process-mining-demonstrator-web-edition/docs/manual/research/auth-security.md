# Sign-in & Authentication — Documentation Notes
Process Mining Demonstrator — Web Edition. Sources: `backend/app/web_surface.py`, `frontend/web/src/components/{LoginView,AuthFooter,PasskeysSheet,TwoFactorSheet,IdleLogout,Gates}.tsx`, `frontend/web/src/{store,api,passkey,mfa}.ts`, `frontend/web/src/{App,IntegrationApp}.tsx`, `backend/app/services/{mfa,passkey,login_throttle}.py`, `backend/app/store/security.py`, `backend/app/config.py`, `admin/server.py`, `admin/pages.py`, `frontend/server.py`, `integration/server.py`.

---

## 1. The three browser surfaces and who may sign in

| Surface | Default ports (HTTP / HTTPS) | Session cookie | Who may sign in | Sign-in ever optional? |
|---|---|---|---|---|
| Main application (GUI) | 8080 / 8443 | `pmw_session` (audience "app") | **Any enabled user** (all roles) | Yes — "Require sign-in for the main application" toggle (default **on**) |
| Integration console | 8100 / 8463 (admin port + 10; `PMW_INTEGRATION_PORT` / `PMW_INTEGRATION_HTTPS_PORT`) | `pmw_integration` (audience "integration") | **Developers and admins only** — power users are refused | No — always requires sign-in, regardless of the global toggle |
| Admin interface | 8090 / 8453 (`PMW_ADMIN_PORT` / `PMW_ADMIN_HTTPS_PORT`) | `pmw_admin` (audience "admin") | **Admins only.** Local accounts always; directory (LDAP) accounts only if "Also allow directory sign-in to this admin interface" is enabled *and* the account was locally promoted to admin | No |

- The main app and the integration console share one React sign-in component (`LoginView`) and one server-side auth factory; the **only visual difference** is the integration console adds a second title line **"Integration"** under "Process Mining Demonstrator". The admin sign-in is a server-rendered page that deliberately mirrors the app's panel pixel-for-pixel, with the second title line **"Administration"**.
- Session cookies are **audience-bound**: an app cookie is never accepted by the integration console or admin panel and vice-versa. Signing in on one surface does *not* sign you in on the others. All cookies are HttpOnly, SameSite=Lax, Secure when served over HTTPS, path=/.
- The admin can turn the whole integration console off (Admin → **Integration** tab → checkbox **"Enable the integration console"**, toasts "Integration console enabled/disabled — restart to apply"). While disabled, browser navigations to that surface get a 503 page titled **"Console unavailable"** with the text **"The integration console has been turned off by the administrator."**; API/XHR calls get the same text as JSON with status 503.
- First run seeds a built-in administrator: username **Administrator**, password **Administrator** (overridable with env vars `PMW_DEFAULT_ADMIN_USER` / `PMW_DEFAULT_ADMIN_PASSWORD`). While that default password is unchanged, the admin dashboard shows the banner: "⚠️ The **Administrator** account is still using its default password. Change it now in **👤 Profile** (top right)."

---

## 2. Password sign-in — main app & integration console (LoginView)

### Layout & controls
- Full-screen panel with the product logo, title **"Process Mining Demonstrator"** (+ optional subtitle line), and a caption that changes with the step:
  - Base step: **"Sign in to continue"**
  - TOTP code step: **"Enter your authentication code"**
  - Forced 2FA enrolment: **"Set up two-factor to continue"**
- Fields: **Username** (autofocus) and **Password**.
- Buttons: **"Sign in"** (primary; disabled until a non-empty username is typed — an empty password is allowed by the form and simply fails auth) and, when passkeys are usable in this browser (see §6), **"🔑 Sign with Passkey"** (tooltip: "Sign in with a passkey (Touch ID, Windows Hello, security key…)"; also disabled until a username is entered). A spinner shows in the button while a request is in flight.
- Optional notices above the form:
  - Orange **inactivity notice**: **"You were signed out due to inactivity."** — shown after an idle auto-logout; suppressed if an error is showing.
  - Orange **license banner** (only when no valid license): "**Demo Mode** — remaining time: N min" or "**No License installed**" (refreshed every 30 s).
  - Red **error box** — any sign-in error message (see the catalogue in §12).
- Below the form, when a directory (LDAP) server is configured: a green/red LED dot plus **"Directory server available"** / **"Directory server unavailable"** (tooltips: "The user directory server responded to a connection test." / "The user directory server did not respond to a connection test."). Nothing is shown when no directory is configured. Availability is a cached probe (~20 s cache).
- The panel background can be customised by the admin (Customize tab): theme default, a solid colour, or an uploaded image (over an image the panel becomes 50 % translucent). Applies identically to the app, integration and admin sign-in pages.

### Flow
1. User submits username + password → `POST /auth/login`.
2. Possible outcomes:
   - **Success, no 2FA** → signed in; session cookie set.
   - **`mfaRequired`** — the account has confirmed TOTP (and it is still allowed): the panel switches to the **code step** (see §5.3). No session exists yet; a short-lived signed "password ok" cookie (`pmw_mfa_pending`, 5-minute TTL) carries the state.
   - **`mfaSetupRequired`** — 2FA is *allowed* for the account but not yet configured: enabling 2FA makes it **mandatory**, so the panel switches to **forced enrolment** (see §5.4). No session is issued until enrolment completes.
   - **Error** — message shown in the red box, the password field is cleared (username kept).
3. On the integration console, the role gate runs **before** any second factor: a valid password from a non-developer/non-admin is refused with 403 **"You need the Developer role to use the integration console. Ask an administrator to grant it."** — no TOTP step is offered.
4. On success the app loads (settings, connections, projects). In the main app, the first successful entry per browser profile also shows the **Legal Disclaimer** gate (heading "Legal Disclaimer", subtitle "Please read carefully before continuing", checkbox **"I have read and accept all terms stated above"**, buttons **Decline** / **Accept & Continue**; Accept & Continue stays disabled until the checkbox is ticked; **Decline signs the user out** and returns to the login panel). Acceptance is stored in the per-user settings, so it appears once per user.

### Directory (LDAP) accounts
- The main-app (and integration) sign-in also accepts directory accounts when LDAP is configured and enabled. Local accounts are always checked **first** (break-glass); a directory identity can never take over a local account that merely shares its name.
- Directory users are provisioned on first sign-in as plain, enabled local rows (`authSource: ldap`); admin rights are **never** granted from the directory — a local admin must promote them.
- LDAP users have no local password; the failed-sign-in lockout counter does **not** apply to them, and the admin Users tab hides "Reset password" for LDAP rows.

---

## 3. Admin interface sign-in (server-rendered page)

- Same panel design; title lines "Process Mining Demonstrator" / **"Administration"**; page `<title>` is "Administration — Sign in".
- Fields **Username** / **Password**; **"Sign in"** button (disabled until a username is typed, spinner during submit); **"🔑 Sign with Passkey"** button appears only when the browser supports WebAuthn *and* the page is reached via a usable hostname (hidden entirely when reached by IP).
- Visiting `/` without a session redirects to `/login`; visiting `/login` with a valid session redirects to `/`.
- Outcomes of `POST /login`:
  - Bad credentials **or valid non-admin credentials** → 401 with **"Invalid credentials, or the account is not an administrator."** (deliberately does not reveal which).
  - Correct password but the account is disabled/locked → the specific block message (§8).
  - IP throttled → 429 with **"Too many failed attempts. Try again in about N seconds."** (includes a Retry-After header).
  - TOTP enrolled → the **code step** renders (caption "Enter your authentication code", field label **"Authentication code"**, placeholder "6-digit code or a recovery code", button **"Verify"**, helper "Enter the 6-digit code from your authenticator app, or one of your recovery codes."). This step is a plain form — no passkey button, no Back button (reload /login to restart).
  - 2FA allowed but not set up → **forced enrolment** page (caption "Set up two-factor to continue"): explanatory text "Two-factor is required for your account. Scan this with an authenticator app (Google Authenticator, 1Password…), then enter the 6-digit code.", a server-rendered QR code, field **"6-digit code"** (placeholder "123456"), button **"Confirm & sign in"**. On success the recovery-codes page renders (caption **"Two-factor is on"**, notice "**Save your recovery codes.** Each works once if you lose your authenticator; they won't be shown again.", the 10 codes in a two-column monospace grid, and a **"Continue to the admin panel"** link — the session cookie is already set at this point).
  - Success without 2FA → redirect to the dashboard.
- Code-step errors: **"Incorrect code. Try again."** (the pending cookie is kept so the user can retry without re-typing the password), **"Your sign-in session expired. Please start again."** (pending cookie expired/invalid — note the app wording differs slightly: "…Start again."), **"Too many failed attempts. Try again shortly."** (429). Enrolment-step wrong code: **"That code didn't match. Try again."** (same QR/secret re-rendered).
- Passkey failure on this page shows: **"Passkey sign-in failed. Check the passkey is registered and still enabled."** (user-cancelled ceremonies are silent).
- Admin sign-out: the **"Log out"** button (top-right, next to "👤 Profile"); redirects to /login.
- ?inactivity=1 on /login shows the same orange **"You were signed out due to inactivity."** notice.

---

## 4. Sessions: lifetime, idle logout, invalidation

### Session token mechanics (all three surfaces)
- Stateless, Fernet-signed cookies re-minted on **every authenticated request** (and on `/auth/session` / `/api/session` polls). Embedded: username, per-user **session epoch**, surface audience, and the **original sign-in time** (`iat`), which is carried through every refresh.
- **Sliding idle window**: when an idle timeout is configured, the cookie TTL equals that window and refreshes on activity. With no idle timeout, the TTL is fixed: **12 h** for the app/integration (`PMW_SESSION_TTL`, seconds), **8 h** for the admin (`PMW_ADMIN_SESSION_TTL`).
- **Absolute session lifetime**: regardless of activity, a sign-in dies **7 days** after the original sign-in (`PMW_SESSION_MAX_LIFETIME`, seconds; applies to all three surfaces). Reaching it forces a fresh sign-in. Tokens minted before this feature existed (no `iat`) are refused once.
- A session is also re-validated on every request against the live user record: account disabled/deleted → session dead; role revoked → session dead **immediately** on a role-gated surface (integration console: losing Developer mid-session drops you to an "Access denied" screen — heading **"Access denied"**, text "The integration console is available to developers and administrators only. Ask an administrator to grant you the Developer role.", plus a **"⏻ Sign out"** button).

### Idle (inactivity) auto sign-out
- **Main app**: admin-configured in Users tab — **"Auto sign-out after [N] minutes of inactivity"** (0–1440; 0 = disabled; hint text: "Idle sessions are signed out after N min." / "Disabled — sessions never time out on inactivity."). Client side, the invisible IdleLogout component watches mousemove / mousedown / keydown / touchstart / scroll / wheel; after N idle minutes it signs the user out and the login panel shows **"You were signed out due to inactivity."** While the user is active it pings `/auth/session` (throttled to at most every 15–60 s) so the server-side sliding window stays alive even without API calls. It only runs when sign-in is required, a user is signed in, and N > 0.
- **Integration console**: the **same** Users-tab idle value governs its *server-side* cookie window (the session simply expires after N idle minutes), but there is **no client-side watcher** — an idle user is not actively bounced to the login screen; their next action fails auth instead. (Gotcha worth documenting.)
- **Admin interface**: a **separate** setting — App Control tab, card **"Admin session"**: "Automatically sign out of **this admin interface** after a period of inactivity. This is separate from the main app's auto sign-out (set in the Users tab)." Control: "Auto sign-out after [N] minutes of inactivity" + **Save** (toast "Admin auto sign-out updated"); hint: "You are signed out of this admin after N min idle." / "Disabled — the admin session never times out on inactivity." Client-side watcher mirrors the app's and redirects to `/login?inactivity=1`.

### Sign-out and cross-surface invalidation (important gotchas)
- **"⏻ Sign out"** (app/integration sidebar footer) and **"Log out"** (admin) don't just delete the cookie — they bump the user's **session epoch** server-side, which invalidates **every outstanding session token for that user on all three surfaces**. Signing out of the app also kills that user's admin and integration sessions (they fail on their next request). Sign-out also releases the user's per-user database connection on the backend (best-effort).
- **Password change forces re-login everywhere**: any password set/reset bumps the session epoch, so all of the user's sessions die. Exception: an admin changing **their own** password in the Profile overlay keeps their *current* admin session alive (the cookie is re-issued in the same response) — every *other* session of theirs is invalidated. A user whose password was reset by an admin is silently signed out at their next request and must sign in again.
- Changing the bootstrap Administrator's password clears the default-password warning permanently.

### When a session dies mid-use
- API calls start returning 401 **"Authentication required."**; the SPA surfaces this as an error, and a reload lands on the sign-in panel. Other proxy errors users may see: 502 **"The compute backend is not reachable. Start it with ./run.sh or check PMW_BACKEND_URL."** and 504 **"The compute backend timed out."**

---

## 5. Two-factor authentication (TOTP)

### 5.1 Model
- TOTP is an **admin-gated, per-user** feature layered on top of the password (never a replacement). Two independent facts per user:
  - **Allowed** (admin sets it — the **"2FA"** checkbox per user, or the all-users master checkbox): the user *may/must* use 2FA.
  - **Enrolled** (user confirms a code): a confirmed secret is stored (encrypted at rest).
- Login gate = allowed **AND** enrolled. Consequences:
  - Allowed + not enrolled → **2FA is mandatory**: the next sign-in (app, integration or admin) stops after the password and **forces enrolment** — the user cannot bypass it by not enrolling.
  - Allowed + enrolled → every password sign-in requires the current 6-digit code (or a recovery code). **A passkey sign-in skips the TOTP step entirely** (it counts as strong auth on its own).
  - Allowed revoked while enrolled → the second factor is *relaxed*: password-only sign-in works again. The secret is **not** deleted — re-ticking "2FA" re-activates the same authenticator without re-enrolment.
- One secret per user protects **all three surfaces**.
- Codes: 6 digits, 30-second steps, ±1 step of clock-skew tolerance; spaces in the entered code are ignored. Authenticator-app entry is labelled with issuer **"Process Mining Demonstrator"** (override: `PMW_MFA_ISSUER`).
- Recovery codes: **10** per set, format like `a1b2c3d4-e5f6g7h8` (lower-case, no look-alike characters), each single-use, stored only as salted hashes. Entering one is accepted anywhere a TOTP code is (login step 2, and the turn-off confirmation) — dashes/spaces/case are ignored. Generating a new set (setup or "Regenerate recovery codes") **replaces** the old set entirely. They are displayed **once**; admins cannot view or recover them.
- Timing windows: after the password step the user has **5 minutes** to enter the code (pending cookie TTL); an enrolment QR is valid for **10 minutes** (setup cookie TTL). Expiry → "Your sign-in session expired. Start again." / "Setup expired. Start again."

### 5.2 Self-service management (signed in)
**Main app & integration console** — sidebar footer button **"🔒 Two-factor"** (tooltip "Manage two-factor authentication"; only visible when the admin has allowed 2FA for the account). Opens the **"Two-factor authentication"** sheet:
- Intro: "Add a one-time code from an authenticator app (Google Authenticator, 1Password, Authy…) on top of your password. Your password still signs you in — the code is an extra step."
- Not enrolled → button **"Set up authenticator"** → QR code + "Scan this with your authenticator app, then enter the 6-digit code it shows." + "Can't scan? Enter this key manually: *secret*" + input (placeholder "6-digit code") + **Confirm** / **Cancel**. Wrong code → "That code didn't match. Try again."
- Enrolled → status row "✅ Two-factor is on. N recovery code(s) left." with buttons **"Regenerate recovery codes"** and **"Turn off"**.
- **Turn off** requires re-authentication: "Enter your current code (or a recovery code) to turn two-factor off." + input (placeholder "Current code") + **"Confirm off"** / **Cancel**. Wrong code → **"Enter your current authentication code to turn off two-factor."** (this stops a hijacked session from silently stripping 2FA). Turning it off deletes the secret *and* all recovery codes.
- After setup/regenerate, the recovery block shows: heading **"Save your recovery codes"**, text "Each works once if you lose your authenticator. Store them somewhere safe — they won't be shown again.", the codes in a grid, buttons **"Copy codes"** and **"Done"**.

**Admin interface** — top-right **"👤 Profile"** overlay, section **"Two-factor authentication"**: same functionality with banner states "Two-factor is on. N recovery codes left." / "Two-factor is off for your account." / "Two-factor is not enabled for your account — enable it in the Users tab first."; buttons **"Set up authenticator"**, **"Regenerate recovery codes"**, **"Turn off"** (the last uses a browser prompt: "Enter your current authentication code (or a recovery code) to turn off two-factor:"); toasts "Two-factor enabled", "Recovery codes regenerated", "Two-factor turned off".

### 5.3 The code step at sign-in (app/integration)
- Caption "Enter your authentication code"; field label **"Authentication code"**, placeholder **"6-digit code or a recovery code"**; helper "Enter the code from your authenticator app, or one of your recovery codes."; buttons **"Verify"** and **"Back"** (Back returns to username/password and clears both code and password).
- Wrong code → **"Incorrect code. Try again."** Wrong codes are throttled per-IP but **never count toward the account lockout** — a mistyped/expired code can never disable an account.

### 5.4 Forced (mandatory) enrolment at sign-in (app/integration)
- Caption "Set up two-factor to continue"; text "Two-factor is required for your account. Scan this with an authenticator app (Google Authenticator, 1Password…), then enter the 6-digit code."; QR; "Can't scan? Key: *secret*"; field **"6-digit code"** (placeholder "123456"); buttons **"Confirm & sign in"** and **"Back"** (Back abandons enrolment — no session is issued; nothing is stored server-side until a code confirms the authenticator, so there are no half-enrolled accounts).
- On success the session is issued *and* the login panel stays up one more screen to show the recovery codes: heading **"Two-factor is on — save your recovery codes"**, text "Each works once if you lose your authenticator. They won't be shown again.", buttons **"Copy codes"** and **"Continue"** (Continue enters the app).
- While the QR is being fetched, a spinner with **"Preparing…"** shows.

### 5.5 Lost authenticator
- Use a recovery code at the code step; or an admin **unticks the user's "2FA" checkbox** in the Users tab so the password alone works again and the user can re-enrol. (Admin help text documents exactly this.) There is no admin "reset 2FA" that preserves enrolment.

---

## 6. Passkeys (WebAuthn)

### 6.1 Model & prerequisites
- Passkeys are an admin-gated **alternative** to the password (the password always remains a fallback). Per-user **"Passkey"** checkbox in the admin Users tab, plus an **all-users master checkbox**; both local and LDAP users can be allowed. Turning the permission **off blocks passkey sign-in immediately** (checked at every step) and hides the management UI.
- A passkey registered on a host works on **all surfaces of that host** — app, integration console and admin panel share the Relying-Party ID (the hostname without port).
- Requirements: a WebAuthn-capable browser, a **secure context** (HTTPS or localhost), and a **real hostname** — WebAuthn rejects bare IP addresses and single-label hosts. When reached by IP, the app shows the hint **"Passkeys need a hostname, not an IP address. Reach the server by its name over HTTPS — e.g. its ".local" name — instead of its IP, then try again."** and the sign-in button/management controls are hidden or disabled.
- Deployment env vars: `PMW_PASSKEY_RP_ID` (set to the shared parent domain for split app/admin subdomains), `PMW_PASSKEY_ORIGINS` (comma-separated allowlist of expected origins), `PMW_PASSKEY_RP_NAME` (display name, default "Process Mining Demonstrator").
- Sign-in is **username-first**: the user must type their username, then press "🔑 Sign with Passkey" (no password needed). Discoverable-credential/usernameless flow is not used.
- Anti-enumeration: asking to sign in with a passkey for an unknown/ineligible account produces an indistinguishable (decoy) challenge; the device then simply has no matching passkey, and the browser cancels — which the UI treats as a silent cancel. Server-side verification failures return the generic **"Passkey sign-in failed."**
- A passkey sign-in **satisfies 2FA by itself** — no TOTP code step even for TOTP-enrolled users.
- Replay protection via signature counters; a challenge is valid for 5 minutes ("Passkey challenge expired. Try again.").

### 6.2 Enrolment & management (app/integration)
- Sidebar footer button **"🔑 Passkeys"** (tooltip "Manage passkeys for this account"; only visible when allowed). Opens the **"Passkeys"** sheet:
  - Intro: "Passkeys let you sign in with Touch ID, Windows Hello, or a security key instead of your password. Your password still works as a fallback."
  - Unsupported browser → "This browser does not support passkeys."
  - IP-address host → the hostname hint above (orange banner).
  - Empty state → **"No passkeys registered yet."**
  - Each registered passkey lists its name (falls back to "Passkey") and "Added *date/time*", with a **"Remove"** button (tooltip "Remove this passkey"). Removing needs no confirmation.
  - Add: name input (placeholder **"Name (e.g. MacBook Touch ID)"**, name capped at 60 chars, defaults to "Passkey") + button **"Add a passkey"** → the OS/browser passkey ceremony runs. User-cancelled ceremonies are silent.
  - Error if the device already holds a passkey for this account: **"A passkey for this account already exists on this device. If it isn't shown in the list here, remove it from your device's passkey settings (iOS: Settings → Passwords) and try again."**
  - Server-side refusals: "Passkeys are not enabled for your account." (403), "Passkey challenge expired. Try again." (400), "Could not register passkey: *reason*" (400).

### 6.3 Enrolment & management (admin Profile overlay)
- **"👤 Profile"** → section **"Passkeys"**: "Sign in with Touch ID, Windows Hello, or a security key instead of your password (which always remains a fallback). Passkeys must be enabled for your account (Users tab) before you can add one; the same passkey works on both the app and this panel."
- Banner states: "Checking passkeys…" → "Passkeys are enabled for your account." / "Passkeys are not enabled for your account — enable them in the Users tab first." / "This browser does not support passkeys." / "Passkeys need a hostname, not an IP address. Reach this panel by its name over HTTPS — e.g. its ".local" name — instead of its IP to add or use one." / "Could not load passkeys: *message*".
- Controls: **"Passkey name"** field (placeholder "e.g. MacBook Touch ID"), **"Add a passkey"** button; per-item **"Remove"**. Toasts: "Passkey added", "Passkey removed". Specific errors: the already-exists text (as above, "…remove it in your device's passkey settings and try again.") and "Passkeys need a hostname, not an IP address — reach this panel by its name over HTTPS."

---

## 7. Roles and the capability matrix

Roles are **independent, additive flags** on a user: Administrator, Power, Developer (plus the implicit "plain user" base). The sidebar footer shows the signed-in identity ("👤 name (Role)") where the label is the *highest* role: **Admin** > **Power user** > **Developer** > **User**. The admin Users tab shows a combined role badge (e.g. `admin·power`, `power·dev`; tooltips: "administrator", "power user (manages own connections)", "developer (integration console)", "Regular user").

| Capability | Plain user | Power | Developer | Admin |
|---|---|---|---|---|
| Sign in to the main app (when enabled account) | ✔ | ✔ | ✔ | ✔ |
| Sign in to the integration console | ✖ (403) | ✖ (403: "You need the Developer role…") | ✔ | ✔ |
| Sign in to the admin interface | ✖ | ✖ | ✖ | ✔ |
| Use DB connections **assigned to them** | ✔ | ✔ | ✔ | ✔ |
| Create/manage **their own** DB connections (app & integration sidebars) | ✖ | ✔ | ✔ | ✔ (manages **all**) |
| Advanced-analysis views: **Conformance Check, Happy Path, Simulation** | ✖ (hidden from the view menu) | ✔ | ✖ (unless also Power) | ✔ |
| Journey **sampling** (create/delete representative subsets, A/B sources) | ✖ | ✔ | ✖ (server refuses: "Journey sampling is available to power users and administrators only.") | ✔ |
| Notes (create/comment) | ✔ | ✔ | ✔ | ✔ |
| Enrol/sign in with passkey; set up 2FA | If admin allowed it (per-user flags — role-independent) | same | same | same |
| Manage users, TLS, LDAP, backups, license, customization, integration on/off | ✖ | ✖ | ✖ | ✔ |

Notes:
- The Developer role is purely an **additional access grant** to the integration console; it does not include power features (but developers *can* manage their own connections).
- Role revocation is enforced live: the surface predicate is re-checked on every request (see §4).
- The **built-in Administrator** cannot be disabled, demoted or deleted (errors: "The built-in Administrator account cannot be disabled." / "…must remain an administrator." / "…cannot be deleted."), and any change that would leave no enabled admin is refused: **"This would leave no enabled administrator. Promote or enable another admin first."**

---

## 8. Failed-sign-in lockout, auto-expiry, and IP throttling

### Account lockout
- Admin Users tab: **"Disable an account after [N] failed sign-in attempts"** + **Save** (0–100; toast "Failed-sign-in lockout updated"). Hints: "Accounts (incl. the Administrator) are disabled after N failed sign-ins." / "Disabled — accounts are never locked on failed sign-ins." Default on fresh installs: **3**; an explicit 0 turns it off.
- Counts **consecutive wrong-password** attempts against a local account (app, integration or admin sign-in — they share the store). Not counted: TOTP-code failures, passkey failures, LDAP accounts, already-disabled accounts. A successful sign-in resets the counter.
- **Exception**: the built-in Administrator is *counted but never auto-locked* (it is the break-glass account; its protection is the IP throttle + slow password hashing). Despite the admin-UI hint's "incl. the Administrator" wording, the built-in admin will not actually lock — other admin accounts do.
- On lock the account is disabled and flagged; the Users tab shows a **"locked"** pill (tooltip "Disabled after too many failed sign-ins — Unlock to restore.") and the row's action button reads **"Unlock"**.
- **Auto-expiry**: a lockout lifts itself after **15 minutes** (store default; 0 would mean "until an administrator re-enables", but there is currently **no admin UI** for changing this value). The expiry is applied lazily — at the user's next sign-in attempt — so simply trying again after the window works.
- Unlock paths: wait out the window; admin clicks **Unlock** (or Enable) in the Users tab (also clears the counter); or restart the server with **`PMW_RESET_LOCKOUTS=1`** to clear every lockout (break-glass, e.g. the sole non-builtin admin locked out).
- **What the user sees**: to avoid revealing account existence, the specific reason is shown **only when the supplied password is correct**: **"This account has been locked after too many failed sign-in attempts. Contact an administrator."** or **"This account has been disabled. Contact an administrator."** With a wrong password they get the generic message ("Invalid username or password." on app/integration; "Invalid credentials, or the account is not an administrator." on admin).

### Per-IP throttle (all surfaces)
- Independent of the account lockout: after **3 failures within 15 minutes from one source IP**, that IP must wait a **5-minute cooldown** (measured from its last failure). In-memory per process (cleared by a restart). The socket peer address is used; X-Forwarded-For is deliberately ignored.
- Applies to: password logins, TOTP verify, forced-enrolment confirm, 2FA turn-off re-auth, and (admin) passkey sign-in completion. Cleared only by a fully successful sign-in.
- Messages: app/integration **"Too many attempts. Try again shortly."** (429); admin login **"Too many failed attempts. Try again in about N seconds."**; admin code/setup steps **"Too many failed attempts. Try again shortly."**

---

## 9. Require-login vs open single-user mode (main app only)

- Admin Users tab checkbox: **"Require sign-in for the main application"** (hint "Users must sign in." / "The app is open — no sign-in required."; toast "Access updated"). Default: **on** (multi-user default).
- **On**: every visitor sees the sign-in panel; all `/api/*` calls require a session (401 "Authentication required." otherwise; only the health probe is open).
- **Off (open mode)**: the app loads with no login panel and **no user identity** — per-user settings and filter presets share one profile; the sidebar auth footer (name, Two-factor, Passkeys, Sign out) is absent; the idle logout is inactive; power/admin-only features are hidden client-side and refused server-side (no identity → 403 for power endpoints). If the session probe itself fails, the app assumes open access so it still loads.
- The **integration console ignores this toggle** (always requires sign-in, being role-gated), as does the admin interface.

---

## 10. Admin Users tab — full control reference (auth-related)

Card **"Users"** — "Only enabled users will be allowed to sign in to the main application."
- Toggles/settings (each in its own banner): Require sign-in (§9), app idle timeout (§4), failed-sign-in threshold (§8).
- Filter chips **All / Local / LDAP** with counts; search field "Search users by name…"; empty result: "No matching users."
- Master row: "Passkey and two-factor are optional alternatives/additions to the password (which always works)." + "All users:" **Passkey** checkbox (tooltip "Allow every user to enrol and sign in with a passkey") and **2FA** checkbox (tooltip "Allow every user to set up two-factor (TOTP)"). These write the flag for **every existing user at once** (toasts "Passkeys allowed/disabled for all users", "Two-factor allowed/disabled for all users"); the checkbox reflects "every user currently allowed". Note: it does not change defaults for users created later.
- Per-user card, line 1: username (+ display name), **local**/**LDAP** pill, role badge, **enabled**/**disabled**/**locked** pill, then per-user **Passkey** and **2FA** checkboxes (tooltips "Allow this user to enrol and sign in with a passkey" / "Allow this user to set up two-factor (TOTP)").
- Line 2: "Last sign-in: …" plus buttons: **Disable** / **Enable** / **Unlock**; **Make admin** / **Remove admin**; **Make power** / **Remove power**; **Make developer** / **Remove developer**; **Reset password** (local users only; browser prompt "New password for *user*:"); **Delete** (confirm 'Delete user "*user*"?'). The built-in admin row shows only the note **"built-in admin"** (tooltip "The built-in administrator cannot be disabled, demoted or deleted.") — and an **Unlock** button if somehow flagged locked.
- "Add a user": **Username**, **Password**, **Administrator** checkbox, **Create user** (errors: "Username is required.", "Password is required.", "A user named '…' already exists.").
- Remember: enabling **2FA** here makes it **mandatory** for that user at their next sign-in on any surface; enabling **Passkey** merely permits enrolment. Disabling and re-enabling an account clears its lockout counter. Deleting a user also deletes their passkeys and recovery codes.

---

## 11. Error-message catalogue (exact strings → meaning)

**Password step (app/integration):**
- "Invalid username or password." — wrong credentials (or unknown/disabled account with a wrong password).
- "This account has been locked after too many failed sign-in attempts. Contact an administrator." — correct password, account auto-locked.
- "This account has been disabled. Contact an administrator." — correct password, account disabled by an admin.
- "Too many attempts. Try again shortly." — per-IP cooldown active (429).
- "You need the Developer role to use the integration console. Ask an administrator to grant it." — integration console only; valid password but no developer/admin role (403).
- "The server is not reachable." — network failure reaching the GUI server at all.

**Password step (admin):**
- "Invalid credentials, or the account is not an administrator."
- The same locked/disabled messages as above.
- "Too many failed attempts. Try again in about N seconds." (429, Retry-After set).

**TOTP code step:**
- "Incorrect code. Try again." — wrong/expired code or already-used recovery code.
- "Your sign-in session expired. Start again." (app/integration) / "Your sign-in session expired. Please start again." (admin) — the 5-minute password-ok window lapsed; start from username/password.

**TOTP enrolment (forced at login, or self-service):**
- "That code didn't match. Try again." — wrong confirmation code (QR/secret unchanged; rescan not needed).
- "Setup expired. Start again." — the 10-minute setup window lapsed.
- "Two-factor authentication is not enabled for your account." — admin permission missing (403).
- "Two-factor authentication isn't set up." — regenerate/disable attempted with no enrolment.
- "Enter your current authentication code to turn off two-factor." — wrong code on the turn-off confirmation.

**Passkeys:**
- "Passkey sign-in failed." — verification failed: unknown/removed credential, permission revoked, disabled account, or (integration) missing role. Admin page variant: "Passkey sign-in failed. Check the passkey is registered and still enabled."
- "Passkey challenge expired. Try again." — the 5-minute challenge window lapsed; retry.
- "Passkey sign-in is not available." / "Could not start passkey setup." — begin call failed (fallback wording).
- "Passkeys are not supported in this browser."
- "This browser does not support passkeys." (management sheets)
- "Passkeys are not enabled for your account." — admin permission missing (403). Admin-panel banner variant: "Passkeys are not enabled for your account — enable them in the Users tab first."
- "Passkeys need a hostname, not an IP address. Reach the server by its name over HTTPS — e.g. its ".local" name — instead of its IP, then try again." (app) / "…Reach this panel by its name over HTTPS…" (admin) — page reached by IP; WebAuthn cannot bind to it.
- "A passkey for this account already exists on this device. If it isn't shown in the list here, remove it from your device's passkey settings (iOS: Settings → Passwords) and try again."
- "Could not register passkey: *reason*" — verification failure during enrolment.
- "Could not load passkeys." / "Could not remove the passkey." — management fetch fallbacks.
- User-cancelled ceremonies (NotAllowedError/AbortError) are always **silent** — no error shown.

**Session/state:**
- "Not signed in." — an auth-management endpoint called without a session (401).
- "Authentication required." — gated API without a session (401).
- "You were signed out due to inactivity." — orange notice after an idle logout.
- "The compute backend is not reachable. Start it with ./run.sh or check PMW_BACKEND_URL." (502) / "The compute backend timed out." (504).
- "The integration console has been turned off by the administrator." (503, surface disabled).

**Admin user management:** "No such user.", "Username is required.", "Password is required.", "A user named '…' already exists.", "The built-in Administrator account cannot be disabled / must remain an administrator / cannot be deleted.", "This would leave no enabled administrator. Promote or enable another admin first.", "Enter a new password.", "The passwords don't match."

---

## 12. Gotchas & warnings for the manual

1. **Enabling 2FA is enabling *mandatory* 2FA** — the user cannot decline; their next sign-in forces enrolment before any session exists.
2. **Passkey sign-ins bypass TOTP** by design (documented as strong auth). If an organisation wants "always TOTP", it must not allow passkeys.
3. **Sign out anywhere = sign out everywhere** (session-epoch bump invalidates all of the user's tokens on all three surfaces); the same happens on any password change/reset (the self-changing admin's current session survives).
4. **Revoking the 2FA permission does not delete the enrolment** — re-allowing instantly re-arms the same authenticator. Turning 2FA off from the sheet (with a code) *does* delete secret + recovery codes.
5. **Recovery codes are shown exactly once**; regeneration invalidates all previous codes; admins cannot retrieve them.
6. **5- and 10-minute windows**: code entry after password (5 min), enrolment QR (10 min), passkey challenge (5 min). Expiry messages tell the user to start again.
7. **Passkeys silently unavailable over IP addresses** — the sign-in button and management controls hide; users reaching a LAN server by IP need a hostname (and HTTPS off-localhost). Split-domain deployments need `PMW_PASSKEY_RP_ID` / `PMW_PASSKEY_ORIGINS`.
8. **Wrong TOTP codes never lock the account** (per-IP throttle only); wrong passwords do (default 3, auto-unlock after 15 min; built-in Administrator never auto-locks; `PMW_RESET_LOCKOUTS=1` is the break-glass).
9. **The lockout auto-expiry (15 min) is not configurable in the UI** — only the threshold is.
10. **Integration console has no client-side idle watcher** — the session just expires server-side after the app idle window; the user notices on their next action, not via an automatic bounce to the login screen.
11. **Integration console always requires sign-in** even when the main app is in open (no-login) mode, and refuses power users at the password step with a role message — before any 2FA step. On the **passkey** path the same refusal appears only as the generic "Passkey sign-in failed."
12. **Open mode has no identity**: settings/presets are shared, notes have no author, and every power feature disappears.
13. **Absolute 7-day session cap** (`PMW_SESSION_MAX_LIFETIME`) ends even continuously-active sessions; idle window (`PMW_SESSION_TTL` 12 h app / `PMW_ADMIN_SESSION_TTL` 8 h admin when no idle timeout is set) governs the rest.
14. **Declining the Legal Disclaimer signs the user out.**
15. LDAP: admin panel stays local-only unless explicitly opened to the directory *and* the account is locally promoted; directory accounts can never merge onto local names; admin rights never come from the directory.
16. The username field is required for passkey sign-in (username-first flow) — users who expect a "one-click" discoverable passkey must still type their name.