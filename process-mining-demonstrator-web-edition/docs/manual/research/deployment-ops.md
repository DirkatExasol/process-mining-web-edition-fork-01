# Installation & Operations — Documentation Notes
Source: `/Users/dirk/Work/Process_Mining_Web` (README.md, run.sh, Dockerfile, docker-compose.yml, backend/app/config.py, requirements.txt, .dockerignore, requirements-dev.txt, backend/app/services/net_guard.py). All defaults verified against code, not just README.

---

## 1. Product identity & scope disclaimer

- Product name: **Process Mining Demonstrator — Web-Edition**.
- Explicit disclaimer that belongs in the manual (README, verbatim intent): the application is *intended for demonstration and educational purposes only and is not a production-ready process mining solution*.
- Software license: MIT (repo `LICENSE`). This is **separate** from the runtime *app* license (Ed25519-signed `license.json`, see §11) — the manual must not conflate the two.

## 2. System requirements

| Item | Requirement | Notes |
|---|---|---|
| Python | **3.13 or 3.14** (README says it "falls back gracefully to 3.11+") | The Docker image pins **python:3.13-slim** |
| Node.js | **20+** | Needed **only to build** the React SPA locally; the Docker image builds it in a `node:22-slim` stage, so the runtime container never needs Node |
| Exasol | Any reachable instance | The only supported analytics database; accessed via `pyexasol` |
| LLM (optional) | Any **OpenAI-compatible** endpoint | Used for AI Documentation; configured per database connection |
| Docker (optional) | Docker Compose; **Compose ≥ 2.22** if you want `docker compose watch` auto-rebuild | |

Backend Python dependencies (pinned in `requirements.txt`): fastapi 0.139.2, uvicorn[standard] 0.51.0, pyexasol 2.3.0, openai 2.46.0, pydantic 2.13.4, pydantic-settings 2.14.2, cryptography 49.0.0, ldap3 2.9.1, httpx 0.28.1, orjson 3.11.9, python-multipart 0.0.20, regex 2026.7.19 (ReDoS-safe engine for admin log search), **tzdata 2026.3** (IANA zone database — required because the slim container has no system zoneinfo; the admin display-timezone setting depends on it), webauthn 3.0.0 (passkeys), pyotp 2.10.0 + qrcode 8.2 (TOTP QR enrolment, SVG factory so no PIL needed).

Dev/test dependencies (`requirements-dev.txt`, installed *on top of* requirements.txt): pytest 9.1.1, pytest-asyncio 1.4.0, httpx2 2.9.1 (test-only; production code still uses httpx).

## 3. Local setup (bare-metal)

```bash
# 1. Python environment + backend dependencies (python3.14 works too)
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
# (optional) test dependencies:
.venv/bin/pip install -r requirements-dev.txt

# 2. Build the frontend (installs npm deps automatically on first run)
./run.sh --build
```

- The venv **must** live at `./.venv` in the repo root — `run.sh` hard-codes `./.venv/bin/python`. If it is missing, `run.sh` exits with:
  - `error: virtualenv missing — create it with:`
  - `  python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- `./run.sh --build` runs `npm install` inside `frontend/web` **only if** `frontend/web/node_modules` is absent (message: `→ installing frontend dependencies`), then always runs `npm run build` (message: `→ building the SPA`), and exits.

## 4. Running — `run.sh` flags and behaviour

`run.sh` is the single launcher for all four Python processes. It `cd`s to its own directory, uses `set -euo pipefail`, traps EXIT/INT/TERM and kills all child PIDs on shutdown (Ctrl-C stops everything cleanly).

| Invocation | What runs |
|---|---|
| `./run.sh` | Compute backend (:8000) + admin interface (:8090/:8453) + GUI server (:8080/:8443) + integration console (:8100/:8463). If `frontend/web/dist/index.html` is missing, it builds the SPA first automatically. |
| `./run.sh --dev` | Compute backend + admin interface + **Vite dev server on http://localhost:5173** (hot reload, HTTP only). No GUI server and **no integration console** in dev mode. Runs `npm install` first if `node_modules` is absent. Sets `PMW_REQUIRE_PROXY_AUTH=0` automatically, because Vite proxies straight to the backend with no GUI proxy in between (everything is loopback in dev). |
| `./run.sh --build` | Rebuild the SPA and exit (no servers started). |

Console messages printed at start (useful for the manual's "what you should see"):
- `→ compute backend on https://127.0.0.1:8000 (TLS, internal cert)`
- `→ admin interface (HTTP 8090 / HTTPS 8453, per TLS mode)`
- `→ GUI server (HTTP 8080 / HTTPS 8443, per TLS mode)`
- `→ integration console (HTTP 8100 / HTTPS 8463, per TLS mode)`
- Dev mode instead: `→ Vite dev server on http://localhost:5173`

After start, open:
- Main app: http://127.0.0.1:8080
- Admin interface: http://127.0.0.1:8090
- Integration console (power users / developers / admins only): http://127.0.0.1:8100

## 5. The four processes and their ports

| Process | Directory | HTTP | HTTPS | Purpose |
|---|---|---|---|---|
| **Compute Backend** | `backend/` | — | **8000** (always TLS, internal self-signed cert, loopback-only by default) | Exasol access, analytics, simulation, sampling, LLM proxy, settings store, licensing watchdog, integration abstraction layer + file watchdog |
| **GUI Server** | `frontend/` | **8080** | **8443** | Serves the React SPA, proxies `/api/*` to the backend, enforces sign-in |
| **Admin Interface** | `admin/` | **8090** | **8453** | TLS/cert management, users, per-user DB connections, LDAP, logging, backups, license upload, customize, restart |
| **Integration Console** | `integration/` | **8100** | **8463** | Data-source configuration; sign-in restricted to power users, developers and admins (everyone else refused with a clear message) |

Key operational facts:
- The **browser only ever talks to the GUI server**; the compute backend can therefore run on a separate host close to the database (`PMW_BACKEND_URL` points the GUI proxy at it).
- The GUI→backend hop is **always TLS-encrypted**, even on loopback: the backend mints an internal self-signed cert on start (`data/certs/internal.crt` / `internal.key`), independent of the user-facing TLS mode. The GUI proxy verifies the backend against this pinned cert by default (`PMW_BACKEND_CA`).
- Integration console ports are derived **by convention as admin port + 10** (8090+10 → 8100; 8453+10 → 8463) unless overridden explicitly.
- All three user-facing surfaces (GUI, admin, integration) share **one sign-in stack** (password, TOTP 2FA, WebAuthn passkey) and **one TLS mode + active certificate**.
- The backend refuses `/api/*` calls that do not carry the GUI proxy-auth secret (so a local process cannot forge the `X-PMW-User` header) — disabled only in `--dev`.

## 6. Docker deployment

### 6.1 Quick start

```bash
docker compose up -d --build
```

One **single image** (`process-mining-web:latest`, container name `process-mining-web`) runs all four services via `run.sh` as CMD.

### 6.2 Host port mapping — **+2000 offset**

Host ports are offset by **+2000** from container ports so they don't clash with other local services (the compose file comment specifically cites phpldapadmin on host 8080):

| Host port | Container port | Surface |
|---|---|---|
| **10080** | 8080 | Main application (HTTP) |
| **10443** | 8443 | Main application (HTTPS — active once TLS is enabled in admin) |
| **10090** | 8090 | Admin interface (HTTP) |
| **10453** | 8453 | Admin interface (HTTPS — active once TLS is enabled in admin) |
| **10100** | 8100 | Integration console (HTTP) |
| **10463** | 8463 | Integration console (HTTPS — active once TLS is enabled in admin) |

(NOTE: the README's "Running with Docker" section says "App → http://localhost:8080, admin → http://localhost:8090" — that text predates the +2000 offset in the current compose file; with the shipped compose file the correct URLs are **http://localhost:10080** and **http://localhost:10090**. Flag this discrepancy to the manual writer; the compose file is authoritative.)

- Port **8000** (compute backend) is **deliberately not published** — it stays internal to the container (`PMW_BACKEND_HOST=127.0.0.1` inside the image). `EXPOSE` lists only 8080 8443 8090 8453 8100 8463.
- The HTTPS host ports do nothing until TLS is switched to *Optional* or *Required* in the admin UI.

### 6.3 Image internals (Dockerfile)

- Stage 1 (`node:22-slim`): `npm ci` against the lockfile (cached until the lockfile changes), then `npm run build` of the SPA.
- Stage 2 (`python:3.13-slim`): creates `/app/.venv` and pip-installs `requirements.txt` there so `run.sh`'s `./.venv/bin/*` paths work unchanged; copies `backend/`, `admin/`, `integration/`, `frontend/`, `examples/` (bundled demo logs — seeded into the integration files sandbox on first run), and `run.sh`; drops the built SPA into `frontend/web/dist` so the runtime never needs Node.
- Env baked into the image: `PYTHONUNBUFFERED=1`, `PIP_NO_CACHE_DIR=1`, `PMW_DATA_DIR=/app/data`, `PMW_BACKEND_HOST=127.0.0.1` (backend private), `PMW_FRONTEND_HOST=0.0.0.0`, `PMW_ADMIN_HOST=0.0.0.0`, `PMW_INTEGRATION_HOST=0.0.0.0` (so the published ports are reachable from the host).
- **HEALTHCHECK**: every 30 s (timeout 5 s, start period 25 s, 3 retries) it fetches `https://127.0.0.1:8000/api/health` with certificate verification disabled (the backend serves the internal self-signed cert; loopback liveness doesn't need verification).
- `init: true` in compose → **tini as PID 1** for clean signal handling / no zombie processes; `restart: unless-stopped`.
- `.dockerignore` keeps local state and secrets out of the build context: `.git`, `.venv`, `node_modules`, `frontend/web/dist`, the whole `data` directory, `**/*.sqlite3`, `**/secret.key`, `**/certs`, plus caches — so a locally-populated data dir or key can never be baked into an image.

### 6.4 Persistence (volume)

- Single bind mount: `./data` (relative to the compose file) → `/app/data` (`PMW_DATA_DIR`).
- Everything the app must keep lives there: `settings.sqlite3`, `security.sqlite3`, `logs.sqlite3` + `logs/` rotated segments, the Fernet `secret.key`, `certs/` (active + internal TLS certificates), `backups/`, `license.json`, `demo_grace.json`, PID files, and `integration_files/` (the File-source sandbox; the bundled `examples/*.log` are seeded into it on first run). **Back up `./data` to preserve users, connections, certificates and settings.**
- There is **no separate integration_files mount** in the shipped compose file — it lives inside the `./data` volume at `data/integration_files` by default; a separate mount is only needed if you point `PMW_INTEGRATION_FILES_DIR` elsewhere.

### 6.5 First-run admin bootstrap (Docker)

- Set `PMW_DEFAULT_ADMIN_PASSWORD` (and optionally `PMW_DEFAULT_ADMIN_USER`) in `docker-compose.yml`'s `environment:` block **before the first `up`** — the values only apply while the security database is empty (they seed the first admin; afterwards they are ignored). The compose file ships with these lines present but commented out (`Administrator` / `"change-me"` placeholders).
- Without an override, the seeded admin is **Administrator / Administrator**, and the admin UI forces a password change on first sign-in.

### 6.6 Auto-rebuild during development (Compose Watch)

- `docker compose watch` (or `docker compose up --watch`) — requires Docker Compose ≥ 2.22 — watches `./backend`, `./admin`, `./integration`, `./frontend` (ignoring `node_modules/` and `dist/`), `./requirements.txt`, `./run.sh` and `./Dockerfile`; any change triggers `action: rebuild` of the image. Docker's layer cache keeps this cheap — untouched layers are reused.

## 7. Complete PMW_* environment variable reference

All defaults verified in `backend/app/config.py` (shared by all four processes) unless noted. Boolean-style vars accept `1/true/yes/on` (case-insensitive) as true; `PMW_REQUIRE_PROXY_AUTH` treats `0/false/no/off` as false.

### Hosts & ports

| Variable | Default | Effect |
|---|---|---|
| `PMW_BACKEND_HOST` | `127.0.0.1` | Bind address of the compute backend. Keep loopback unless the backend runs on a separate host. |
| `PMW_BACKEND_PORT` | `8000` | Compute-backend port (HTTPS with the internal cert). |
| `PMW_FRONTEND_HOST` | `127.0.0.1` (Docker image: `0.0.0.0`) | Bind address of the GUI server. |
| `PMW_FRONTEND_PORT` | `8080` | GUI HTTP port. |
| `PMW_FRONTEND_HTTPS_PORT` | `8443` | GUI HTTPS port (used when TLS mode is Optional/Required). |
| `PMW_ADMIN_HOST` | `127.0.0.1` (Docker image: `0.0.0.0`) | Bind address of the admin interface. |
| `PMW_ADMIN_PORT` | `8090` | Admin HTTP port. |
| `PMW_ADMIN_HTTPS_PORT` | `8453` | Admin HTTPS port. |
| `PMW_INTEGRATION_HOST` | = `PMW_ADMIN_HOST` (Docker image: `0.0.0.0`) | Bind address of the integration console. |
| `PMW_INTEGRATION_PORT` | admin port + 10 → `8100` | Integration console HTTP port. |
| `PMW_INTEGRATION_HTTPS_PORT` | admin HTTPS port + 10 → `8463` | Integration console HTTPS port. |

### Backend reachability & internal TLS

| Variable | Default | Effect |
|---|---|---|
| `PMW_BACKEND_URL` | `https://{PMW_BACKEND_HOST}:{PMW_BACKEND_PORT}` (i.e. `https://127.0.0.1:8000`) | URL the GUI proxy uses to reach the compute backend. HTTPS by default (internal cert). Set this when the backend runs on another host. |
| `PMW_BACKEND_CA` | `{data}/certs/internal.crt` | CA bundle the GUI proxy verifies the backend against — defaults to the pinned internal self-signed cert. Point it at a real CA when the backend is fronted by one, or set it **empty** to fall back to the system trust store. |
| `PMW_REQUIRE_PROXY_AUTH` | `1` (on) | The backend requires a proxy-auth secret on `/api/*` so only the GUI proxy (which validated the session) can reach it — blocks a local process forging `X-PMW-User`. `run.sh --dev` sets it to `0` automatically (Vite talks directly to the backend). Do not disable in production. |

### Data & storage

| Variable | Default | Effect |
|---|---|---|
| `PMW_DATA_DIR` | `<repo>/data` (Docker: `/app/data`) | Root of all persisted state (created on start, incl. subdirs `logs/`, `certs/`, `backups/`, `integration_files/`). Git-ignored; back it up. |

### Sessions & sign-in

| Variable | Default | Effect |
|---|---|---|
| `PMW_SESSION_TTL` | `43200` (12 h) | Main-app sign-in session lifetime (sliding idle window — the cookie is re-minted on every authenticated request). |
| `PMW_SESSION_MAX_LIFETIME` | `604800` (7 days) | Hard cap on one sign-in regardless of activity, measured from the original sign-in; reaching it forces a fresh sign-in (defeats a captured cookie kept alive by periodic requests). |
| `PMW_ADMIN_SESSION_TTL` | `28800` (8 h) | Admin-interface session lifetime. |
| `PMW_DEFAULT_ADMIN_USER` | `Administrator` | Username of the bootstrap admin, created on first run **only if no users exist**. |
| `PMW_DEFAULT_ADMIN_PASSWORD` | `Administrator` | Password of the bootstrap admin (same first-run-only rule). Override before first start, especially in Docker. |
| `PMW_RESET_LOCKOUTS` | unset | Break-glass valve: set to `1` and restart to clear **all** failed-sign-in lockouts (accounts auto-disabled after N wrong passwords; N configurable in admin Users tab, default 3, 0 = off). Logs a warning: `PMW_RESET_LOCKOUTS set — cleared all failed-sign-in lockouts.` |

### Passkeys (WebAuthn) & TOTP

| Variable | Default | Effect |
|---|---|---|
| `PMW_PASSKEY_RP_ID` | unset (derived from request Host header) | Relying-Party ID = registrable domain **without port**, so app (:8443) and admin (:8453) on one host share one passkey. Set only for split app/admin sub-domains — use the shared parent domain. |
| `PMW_PASSKEY_RP_NAME` | `Process Mining Demonstrator` | Human-readable RP name shown by the authenticator. |
| `PMW_PASSKEY_ORIGINS` | empty (accept the request's own origin) | Comma-separated allowlist of expected origins (`scheme://host[:port]`). Single-host deployments need neither this nor RP_ID. |
| `PMW_MFA_ISSUER` | `Process Mining Demonstrator` | Issuer label shown in authenticator apps for TOTP enrolments. |

WebAuthn gotchas for the manual: requires a **secure context** (HTTPS, or `localhost`), and a **real hostname** — a bare IP address fails with the browser error *"the effective domain … is not a valid domain."*; the UI hides passkey controls (with a hint) when reached by IP; password sign-in always still works.

### Licensing / demo mode

| Variable | Default | Effect |
|---|---|---|
| `PMW_LICENSE_GRACE_SECS` | `1800` (30 min) | Grace period the backend keeps running without a valid license before stopping itself — time to upload a license via the admin panel. |
| `PMW_LICENSE_POLL_SECS` | `15` | How often the backend re-reads the license during grace — short enough that an admin upload cancels a pending shutdown within seconds. |
| `PMW_RESET_DEMO` | unset | Set to `1` to clear the one-time demo marker (`data/demo_grace.json`) on backend start, granting a fresh demo window; logs `PMW_RESET_DEMO set — cleared the one-time demo marker.` Deleting the marker file has the same effect. |

### Queries & LLM

| Variable | Default | Effect |
|---|---|---|
| `PMW_QUERY_TIMEOUT` | `30` (seconds) | Wall-clock limit for the heavy statistics queries (matches the original Swift app's 30 s). |
| `PMW_BLOCK_PRIVATE_LLM_HOSTS` | unset (off) | SSRF hardening for the user-configurable LLM endpoint. By default loopback/private LLM hosts are **allowed** (Ollama/LM Studio/internal vLLM are primary use cases) while link-local/cloud-metadata (169.254.169.254), multicast, reserved and unspecified addresses and non-HTTP(S) schemes are always refused. Set `1` in hardened/cloud deployments to also refuse loopback/private targets. Connections are pinned to the vetted IP to defeat DNS-rebind. |

### Integration console

| Variable | Default | Effect |
|---|---|---|
| `PMW_INTEGRATION_FILES_DIR` | `{data}/integration_files` | Sandbox directory File sources may read from — nothing outside it can be opened (path traversal and symlink escapes rejected). Bundled `examples/*.log` demo logs are seeded here on first run. |
| `PMW_INTEGRATION_ALLOW_ANY_PATH` | unset (off) | Set `1` to allow File sources to read **any absolute path the server can read**. Developer-trusted deployments only — it enables reading arbitrary server files. |
| `PMW_INTEGRATION_WATCHDOG` | `1` (on) | Globally enables/disables the file-source watchdog (background loop auto-importing newly-appended lines when a watched file grows). `0` disables. |
| `PMW_INTEGRATION_WATCHDOG_TICK` | `10` (seconds; floor of 5 enforced) | Base wake interval of the watchdog loop; each source additionally has its own configured poll interval. |

## 8. TLS configuration

- Managed entirely in the admin interface, tab **TLS / SSL**: generate a self-signed certificate (common name + SANs, validity, key size) **or** upload a PEM cert + key; mark exactly one certificate *active*; choose the mode.
- One mode + one active certificate is shared by **GUI server, admin interface and integration console**:

| Mode | GUI binds | Admin binds | Integration binds |
|---|---|---|---|
| **Off** | HTTP only (:8080) | HTTP only (:8090) | HTTP only (:8100) |
| **Optional** | HTTP + HTTPS (:8080 + :8443) | HTTP + HTTPS (:8090 + :8453) | HTTP + HTTPS (:8100 + :8463) |
| **Required** | HTTPS only (:8443) | HTTPS only (:8453) | HTTPS only (:8463) |

- Changes take effect **on restart** — the **↻ Restart app server** button in the admin (App Control) rebinds all launchers' listeners in place, no terminal needed. Mechanism: each TLS-aware launcher writes a PID file (`data/gui.pid`, `data/admin.pid`, `data/integration.pid`) and the admin service sends SIGHUP → rebind with the current TLS plan.
- **Fail-safe**: if a mode needs a certificate but none is active, each server falls back to HTTP so nothing is left unreachable — including the admin itself, so a bad certificate can never lock you out.
- The active certificate is materialised to disk (`data/certs/active.crt` / `active.key`) so uvicorn's TLS listener can read it; certificate **private keys are encrypted at rest** (Fernet) in the security store, and key files are written mode `0600` from birth.
- Separate from all this: the backend's always-on **internal** self-signed cert (`data/certs/internal.crt`/`internal.key`) encrypts the GUI→backend hop regardless of the user-facing mode.
- Security headers sent by admin + app servers: `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, plus HSTS when TLS is on.
- **Reverse-proxy warning** (manual-worthy): the per-source-IP sign-in throttle keys on the **socket peer address** and never trusts `X-Forwarded-For`. Behind a reverse proxy every client shares one throttle bucket — terminate TLS at the app itself (as `run.sh` does) or add trusted-proxy handling before fronting it.

## 9. The `data/` directory — full layout

Default `<repo>/data`, overridable with `PMW_DATA_DIR`, bind-mounted to `./data` in Docker. Entirely git-ignored. **This directory is the backup unit.**

| Path | Contents |
|---|---|
| `settings.sqlite3` | App preferences: filter presets, happy paths, target norms, node layouts (per user) |
| `security.sqlite3` | Users (scrypt-hashed passwords), roles, admin-defined DB connections + ownership + assignments, TLS certificates & mode, LDAP config, passkey credentials, TOTP secrets (encrypted) & recovery-code hashes, lockouts, backup schedule |
| `logs.sqlite3` | Live structured log shared by all servers |
| `logs/` | Rotated log segments exported as `.log` files (line format: `DATE -- TIME -- SEVERITY -- CLIENT-IP -- USER -- TAG -- text`) |
| `secret.key` | Fernet key encrypting all secrets at rest (DB passwords, LLM API keys, LDAP service password, cert private keys, backup password). Created atomically on first run with mode `0600`; never overwritten. Losing it orphans every stored secret. |
| `certs/` | `active.crt`/`active.key` (user-facing TLS), `internal.crt`/`internal.key` (backend loopback TLS), plus stored certificates |
| `backups/` | Scheduled/on-demand encrypted backups: timestamped AES-256-GCM `.json` envelopes, pruned beyond the configured retention count |
| `license.json` | The uploaded Ed25519-signed runtime license |
| `demo_grace.json` | One-time demo-grace marker (delete or `PMW_RESET_DEMO=1` to reset) |
| `gui.pid`, `admin.pid`, `integration.pid` | PID files enabling the admin's in-place restart (SIGHUP) |
| `integration_files/` | Sandbox for integration File sources; `examples/*.log` seeded here on first run |

## 10. Backups

- Admin tab **Backup**: enable scheduled encrypted backups (in-process scheduler — no external cron). Build the schedule via dropdowns (hourly/daily/weekly/monthly + time) or a raw five-field cron expression, with a live cron string and plain-English preview. Set the retention count and the AES-256-GCM password, then save.
- The backup password is stored **Fernet-encrypted at rest** (so unattended runs work) and is **never returned to the client** — the API exposes only a *set*/`hasPassword` flag.
- Files land in `data/backups/` as timestamped encrypted `.json` envelopes; files beyond the retention count are pruned automatically.
- **Run backup now** button tests the configuration; the last run's outcome is displayed.
- Endpoints (admin only): `GET|POST /api/backup/schedule`, `POST /api/backup/run-now`.
- Schedule times follow the admin **display-timezone** setting (App Control) — "daily at 02:00" fires at 02:00 in the chosen zone, DST-aware; default is *Server local*.
- Manual/exported backups are JSON, optionally AES-256-GCM-encrypted.
- Independent of these in-app backups: for full disaster recovery, back up the whole `data/` directory (includes `secret.key`, without which encrypted secrets are unrecoverable).

## 11. Licensing & Demo Mode (operations view)

- The compute backend requires a signed license: upload the issued `license.json` in **App Control → License** (panel shows licensee + expiry, and has a remove option). Verification is Ed25519 against a public key embedded in the app.
- No valid license → **Demo Mode**: the sign-in panel shows a *Demo Mode — remaining time* banner during a **one-time** grace period (default 30 min, `PMW_LICENSE_GRACE_SECS`), then *No License installed* once spent, after which the backend **stops itself** until a license is applied.
- Applying a license during the grace window cancels the shutdown (poll interval `PMW_LICENSE_POLL_SECS`, default 15 s). The **admin interface keeps running after the backend stops**, so a license can always be uploaded.
- The grace is anchored in `data/demo_grace.json` and is never renewed by restarting; reset via file deletion or `PMW_RESET_DEMO=1`.

## 12. First-use walkthrough (operator checklist)

1. Start the stack (`./run.sh` or `docker compose up -d --build`).
2. Sign in to the admin interface (default **Administrator / Administrator**) — a password change is forced on first use.
3. (Docker) If you set `PMW_DEFAULT_ADMIN_PASSWORD`, use that instead — it only applied because the security DB was empty on first start.
4. In **Database Connections**, define a connection (Exasol host/port/user/password/schema, optional OpenAI-compatible LLM server, TLS options), use **Test connection**, and **assign it to users**. Leaving a password/API-key field blank on an existing connection keeps the stored value.
5. Optionally use **Create schema & tables** to provision `PROJECTS`, `JOURNEYS`, `STEPS`, `METAS`, `NOTES` (idempotent `IF NOT EXISTS`; the DB account needs `CREATE SCHEMA` / `CREATE TABLE` privileges — only a DBA can grant those).
6. In **Users**, create users; grant roles as needed (Admin, *Make power*, *Developer* checkbox), enable Passkey/2FA columns per user if wanted.
7. Users open the main app, click a connection card in **Connections** (click again to disconnect), open **Projects**, and explore the ten views from the **☰** menu: A-Chart, B-Chart, A/B Comparison, Individual Journey, AI Documentation, Statistics, Conformance Check, Happy Path, Notes, Simulation.
8. Upload the license in **App Control → License** if the sign-in panel shows the Demo Mode banner.

## 13. Upgrade notes & gotchas

- **`TRANSITIONS_RAW` rebuild required after upgrade**: any pre-materialized transitions table built before the partition fix (older builds partitioned the `LEAD()` window by `EVENT_ID` alone) can show wrong per-edge values wherever an `EVENT_ID` recurs across projects or sample sets. Press **Rebuild now** on each affected connection (or `POST /api/connections/<id>/rebuild-transitions` on the admin server with `Authorization: Bearer <token>`) once after upgrading.
- **`JOURNEYS` distribution/partition clauses**: new tables are created with `DISTRIBUTE BY EVENT_ID` and `PARTITION BY EVENT_TIME`. Tables that pre-date these clauses are *not* modified by `CREATE TABLE IF NOT EXISTS`; apply once manually: `ALTER TABLE JOURNEYS DISTRIBUTE BY EVENT_ID;` and `ALTER TABLE JOURNEYS PARTITION BY EVENT_TIME;`.
- **LDAP migration**: a directory login never adopts a same-named local account — delete/rename old local rows first or those users keep signing in with local passwords.
- **Docker Compose Watch** needs Compose ≥ 2.22.
- The rebuild-token `curl` example in the admin includes `-k` because the admin cert is typically self-signed.
- README `run.sh` header comment says "all three services" in places — the actual count is **four** (integration console added later); the manual should consistently say four.
- Everything under `data/` is state; the image contains none of it (`.dockerignore`), so image rebuilds/redeployments are safe — state survives in the volume.