# Live demo-data generator

A single standalone process that **learns a project's structure** from Exasol (the same
Markov directly-follows model the Simulation view uses) and then **emits one synthetic
journey every few seconds** into a target project's `JOURNEYS` table. Point an **A-Chart**
(with auto-refresh on) or the **Dashboard** at that project and you see data arriving live.

It reads from the *source* project: the directly-follows graph (transition probabilities +
per-edge timing), the entry/end steps, and the `META_1/2/3` value mix (sampled per journey,
keeping their correlation); and the `STEP → STEP_ID` map of the *target* project so the rows
join the transition query. It writes nothing to the local filesystem — only to Exasol.

## Run it in Docker (recommended)

Everything is controlled by environment variables, set in
[`docker-compose.example.yml`](docker-compose.example.yml). Edit the values there, then from
this directory:

```bash
docker compose -f docker-compose.example.yml up --build
```

Stop with `Ctrl-C`, or `docker compose -f docker-compose.example.yml down`.

The build context is the **repository root** (the image bundles `backend/` so the
generator's `import app.*` resolves), which the compose file sets for you. To build the
image by hand instead:

```bash
# from the repository root:
docker build -f generator/Dockerfile -t process-mining-generator .
docker run --rm --init \
  -e PMG_HOST=host.docker.internal -e PMG_SCHEMA=PM_PROD -e PMG_PROJECT=1 \
  -e PMG_INSECURE=true -e PMG_MIN=5 -e PMG_MAX=60 \
  process-mining-generator
```

### Reaching Exasol from the container

`PMG_HOST` must be reachable **from inside the container**:

- Exasol on the **Docker host** → `host.docker.internal` (Docker Desktop; on Linux the
  `extra_hosts: host-gateway` line in the compose file provides it), or the host's LAN IP.
- Exasol as **another compose service** → its service name, after joining a shared network
  (see the commented `networks:` block at the bottom of the compose file).

## Parameters (environment variables)

Every option has a `PMG_*` variable; an explicit command-line flag overrides it.

| Variable | Flag | Default | Meaning |
|---|---|---|---|
| `PMG_HOST` | `--host` | `127.0.0.1` | Exasol host |
| `PMG_PORT` | `--port` | `8563` | Exasol port |
| `PMG_USER` | `--user` | `sys` | database user |
| `PMG_PASSWORD` | `--password` | `exasol` | database password |
| `PMG_SCHEMA` | `--schema` | *(required)* | schema holding the project(s) |
| `PMG_PROJECT` | `--project` | *(required)* | source project id to learn from |
| `PMG_TARGET_PROJECT` | `--target-project` | = `PMG_PROJECT` | project id to write journeys into |
| `PMG_MIN` | `--min` | `5` | min seconds between journeys |
| `PMG_MAX` | `--max` | `60` | max seconds between journeys (uniform in `[min,max]`) |
| `PMG_MAX_STEPS` | `--max-steps` | `60` | safety cap on one journey's length |
| `PMG_COUNT` | `--count` | `0` | stop after N journeys (`0` = forever) |
| `PMG_SEED` | `--seed` | *(none)* | deterministic RNG for reproducible demos |
| `PMG_TLS` | `--tls` / `--no-tls` | `true` | use TLS to Exasol |
| `PMG_INSECURE` | `--insecure` | `false` | skip TLS certificate verification |
| `PMG_FINGERPRINT` | `--fingerprint` | *(none)* | pin the server cert SHA-256 (hex) instead of `--insecure` |
| `PMG_MIN_RSA_BITS` | `--min-rsa-bits` | `2048` | minimum server-key size when verifying |

## Run it without Docker

From the repository root, using the backend's virtualenv:

```bash
./.venv/bin/python generator/launch.py \
  --host 127.0.0.1 --port 8563 --user sys --password exasol \
  --schema PM_PROD --project 1 --insecure --min 5 --max 60
```

The same `PMG_*` variables work here too, so `PMG_SCHEMA=PM_PROD PMG_PROJECT=1 … python
generator/launch.py` needs no flags.
