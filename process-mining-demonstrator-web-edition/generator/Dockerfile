# Live demo-data generator — one standalone process that learns a project's structure
# from Exasol (the same Markov model the Simulation view uses) and emits synthetic
# journeys into a target project's JOURNEYS table, so an A-Chart / Dashboard shows data
# arriving live. See generator/launch.py and generator/README.md.
#
# IMPORTANT: the build context is the REPOSITORY ROOT (the image needs both backend/ and
# generator/). Build it with:
#   docker build -f generator/Dockerfile -t process-mining-generator .
# or, more simply, via generator/docker-compose.example.yml (which sets the context).
#
# No `# syntax=` directive — keep offline/restricted-network builds working (matches the
# main image).
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Reuse the backend's dependency set, so the generator's `import app.*` resolves against
# exactly the versions the backend was built with — no second requirements list to drift.
# (The generator itself only needs pyexasol, pydantic, cryptography and regex out of this.)
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# The generator imports the backend package by path (launch.py adds ../backend to sys.path).
COPY backend/ ./backend/
COPY generator/ ./generator/

# Run as an unprivileged user — the generator writes nothing of its own to the local
# filesystem (it only connects out to Exasol). `chmod a+rX` normalises read access: COPY
# preserves the host file modes, and a few backend sources are owner-only (0600) there,
# which the unprivileged user could otherwise not read.
RUN useradd --create-home --uid 10001 appuser \
 && chmod -R a+rX /app/backend /app/generator
USER appuser

# The backend's config module eagerly creates PMW_DATA_DIR on import (for the app's
# SQLite/logs). The generator never uses it, but point it at a writable path under the
# unprivileged user's home so the import succeeds.
ENV PMW_DATA_DIR=/home/appuser/data

# Every parameter is read from a PMG_* environment variable (see generator/launch.py), so
# no default arguments are needed; extra CLI flags may still be appended and override env.
ENTRYPOINT ["python", "generator/launch.py"]
