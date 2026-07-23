# syntax=docker/dockerfile:1
#
# Process Mining Demonstrator — single image running all three services
# (compute backend, GUI server, admin interface) via run.sh. Persisted state
# (SQLite databases, the Fernet secret key, TLS certificates, the GUI PID file)
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
    # The backend stays private to the container; the GUI + admin bind all
    # interfaces so their published ports are reachable from the host.
    PMW_BACKEND_HOST=127.0.0.1 \
    PMW_FRONTEND_HOST=0.0.0.0 \
    PMW_ADMIN_HOST=0.0.0.0

WORKDIR /app

# Python dependencies into a venv so run.sh's ./.venv/bin/* paths work unchanged.
COPY requirements.txt ./
RUN python -m venv /app/.venv \
 && /app/.venv/bin/pip install --upgrade pip \
 && /app/.venv/bin/pip install -r requirements.txt

# Application source. node_modules / dist / data are excluded via .dockerignore.
COPY backend/ ./backend/
COPY admin/ ./admin/
COPY frontend/ ./frontend/
COPY run.sh ./run.sh
RUN chmod +x run.sh

# Drop in the SPA built in stage 1 (so run.sh finds dist and never needs Node).
COPY --from=web /web/dist ./frontend/web/dist

# 8080 = main app (HTTP), 8443 = main app (HTTPS, when TLS is enabled),
# 8090 = admin interface. 8000 (backend) is intentionally kept internal.
EXPOSE 8080 8443 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["./run.sh"]
