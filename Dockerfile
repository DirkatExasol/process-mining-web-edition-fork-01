# syntax=docker/dockerfile:1
#
# Process Mining Demonstrator — single image running all four services (compute
# backend, GUI server, admin interface, integration console) via run.sh. Persisted
# state (SQLite databases, the Fernet secret key, TLS certificates, the PID files)
# lives under $PMW_DATA_DIR, which docker-compose maps to a host ./data directory.

# ── Stage 1: build the React single-page app ──────────────────────────────────
FROM node:22-slim AS web
WORKDIR /web
# Install deps first (cached until the lockfile changes), then build.
COPY frontend/web/package.json frontend/web/package-lock.json ./
RUN npm ci
COPY frontend/web/ ./
RUN npm run build

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Data (settings/security DBs, secret key, certs, gui.pid) — a mounted volume.
    PMW_DATA_DIR=/app/data \
    # The backend stays private to the container; the GUI, admin + integration
    # console bind all interfaces so their published ports are reachable from the host.
    PMW_BACKEND_HOST=127.0.0.1 \
    PMW_FRONTEND_HOST=0.0.0.0 \
    PMW_ADMIN_HOST=0.0.0.0 \
    PMW_INTEGRATION_HOST=0.0.0.0

WORKDIR /app

# Python dependencies into a venv so run.sh's ./.venv/bin/* paths work unchanged.
COPY requirements.txt ./
RUN python -m venv /app/.venv \
 && /app/.venv/bin/pip install --upgrade pip \
 && /app/.venv/bin/pip install -r requirements.txt

# Application source. node_modules / dist / data are excluded via .dockerignore.
COPY backend/ ./backend/
COPY admin/ ./admin/
COPY integration/ ./integration/
COPY frontend/ ./frontend/
COPY run.sh ./run.sh
RUN chmod +x run.sh

# Drop in the SPA built in stage 1 (so run.sh finds dist and never needs Node).
COPY --from=web /web/dist ./frontend/web/dist

# 8080 = main app (HTTP), 8443 = main app (HTTPS), 8090 = admin (HTTP),
# 8453 = admin (HTTPS), 8100 = integration console (HTTP), 8463 = integration
# console (HTTPS) — HTTPS ports activate once TLS is enabled in admin.
# 8000 (backend) is intentionally kept internal.
EXPOSE 8080 8443 8090 8453 8100 8463

# The backend serves TLS (internal self-signed cert); liveness on loopback does
# not need cert verification.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD /app/.venv/bin/python -c "import ssl, urllib.request; urllib.request.urlopen('https://127.0.0.1:8000/api/health', timeout=4, context=ssl._create_unverified_context())" || exit 1

CMD ["./run.sh"]
