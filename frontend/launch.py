"""TLS-aware launcher / supervisor for the GUI server.

Reads the TLS plan managed by the admin service and starts the appropriate
uvicorn listeners in a single process:

  off       → HTTP  on FRONTEND_PORT
  optional  → HTTP  on FRONTEND_PORT  +  HTTPS on FRONTEND_HTTPS_PORT
  required  → HTTPS on FRONTEND_HTTPS_PORT

The launcher writes its PID to ``data/gui.pid`` and installs a SIGHUP handler.
When the admin interface requests a restart it sends SIGHUP: the current
listeners are shut down gracefully and rebuilt from the *current* TLS plan, so a
mode or certificate change takes effect without touching the terminal. The
process (and PID) stays the same across restarts. SIGTERM/SIGINT stop it.

If a TLS mode needs a certificate but none is active, the launcher falls back to
HTTP so the app is never left unreachable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # local `server` module
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import uvicorn  # noqa: E402

from app.config import (  # noqa: E402
    FRONTEND_HOST,
    FRONTEND_HTTPS_PORT,
    FRONTEND_PORT,
    GUI_PID_PATH,
)
from app.store.security import store  # noqa: E402
from server import app  # noqa: E402  — the static + proxy application

log = logging.getLogger("gui-launcher")


def _build_servers() -> list[uvicorn.Server]:
    """Resolve the current TLS plan into uvicorn Server instances."""
    plan = store.tls_plan()
    servers: list[uvicorn.Server] = []

    if plan["http"]:
        servers.append(
            uvicorn.Server(
                uvicorn.Config(
                    app, host=FRONTEND_HOST, port=FRONTEND_PORT, log_level="info"
                )
            )
        )
        log.info("HTTP listener on %s:%s", FRONTEND_HOST, FRONTEND_PORT)

    if plan["https"]:
        servers.append(
            uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=FRONTEND_HOST,
                    port=FRONTEND_HTTPS_PORT,
                    ssl_certfile=plan["certPath"],
                    ssl_keyfile=plan["keyPath"],
                    log_level="info",
                )
            )
        )
        log.info("HTTPS listener on %s:%s", FRONTEND_HOST, FRONTEND_HTTPS_PORT)

    if plan["mode"] != "off" and not plan["hasActiveCert"]:
        log.warning(
            "TLS mode is %r but no certificate is active — serving plain HTTP. "
            "Generate or activate a certificate in the admin interface.",
            plan["mode"],
        )

    if not servers:  # safety net: never leave the app unreachable
        log.warning("No listeners resolved from the TLS plan — defaulting to HTTP.")
        servers.append(
            uvicorn.Server(uvicorn.Config(app, host=FRONTEND_HOST, port=FRONTEND_PORT))
        )
    return servers


def _write_pid() -> None:
    GUI_PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    try:
        GUI_PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass


async def _serve_cycle(restart_event: asyncio.Event, stop_event: asyncio.Event) -> bool:
    """Run one set of listeners until a restart or stop is requested.

    Returns True when the process should exit (stop), False to rebuild and go
    round again (restart).
    """
    servers = _build_servers()
    for server in servers:
        # The launcher owns the signals; stop uvicorn from installing its own.
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    serve_tasks = [asyncio.create_task(s.serve()) for s in servers]
    restart_wait = asyncio.create_task(restart_event.wait())
    stop_wait = asyncio.create_task(stop_event.wait())

    await asyncio.wait(
        {restart_wait, stop_wait, *serve_tasks},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for server in servers:
        server.should_exit = True
    await asyncio.gather(*serve_tasks, return_exceptions=True)
    for waiter in (restart_wait, stop_wait):
        waiter.cancel()

    return stop_event.is_set()


async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    loop = asyncio.get_running_loop()
    restart_event = asyncio.Event()
    stop_event = asyncio.Event()

    loop.add_signal_handler(signal.SIGHUP, restart_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    _write_pid()
    log.info("GUI launcher pid %s — SIGHUP restarts listeners", GUI_PID_PATH.read_text())
    try:
        while True:
            should_stop = await _serve_cycle(restart_event, stop_event)
            if should_stop:
                break
            restart_event.clear()
            log.info("↻ restarting GUI listeners with the current TLS plan")
    finally:
        _clear_pid()
        log.info("GUI launcher stopped")


if __name__ == "__main__":
    asyncio.run(_main())
