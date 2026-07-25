"""Compute Backend — FastAPI app.

Owns the Exasol connection, all analytics and the settings store. The browser
never talks to this service directly; the GUI server proxies to it.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import log_events as logx
from .api import connections, features, projects
from .db.manager import db

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await db.disconnect()  # release the Exasol connection on shutdown


app = FastAPI(
    title="Process Mining Demonstrator — Compute Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# The GUI server proxies same-origin, but allowing localhost keeps the Vite dev
# server usable against this backend directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Log unhandled failures (5xx / crashes such as an oversized simulation) and 4xx
# gate hits. The user comes from the trusted X-PMW-User header the GUI injects.
logx.install_request_logging(app, lambda r: r.headers.get("x-pmw-user", ""))

app.include_router(connections.router)
app.include_router(projects.router)
app.include_router(features.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "connected": db.is_connected}


