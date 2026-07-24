"""Shared TLS-aware launcher / supervisor.

Serves an ASGI app over HTTP and/or HTTPS according to the TLS plan managed by
the admin service — the *same* mode (off / optional / required) and the *same*
active certificate for every service that uses it:

  off       → HTTP  on http_port
  optional  → HTTP  on http_port  +  HTTPS on https_port
  required  → HTTPS on https_port

The launcher writes its PID to ``pid_path`` and installs a SIGHUP handler. When
the admin interface requests a restart it sends SIGHUP: the current listeners are
shut down gracefully and rebuilt from the *current* TLS plan, so a mode or
certificate change takes effect without touching the terminal. The process (and
PID) stays the same across restarts. SIGTERM/SIGINT stop it.

If a mode needs a certificate but none is active, the launcher falls back to HTTP
so the service is never left unreachable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import uvicorn

from .store.security import store


def _build_servers(
    app, host: str, http_port: int, https_port: int, log: logging.Logger
) -> list[uvicorn.Server]:
    """Resolve the current TLS plan into uvicorn Server instances."""
    plan = store.tls_plan()
    servers: list[uvicorn.Server] = []

    if plan["http"]:
        servers.append(
            uvicorn.Server(
                uvicorn.Config(app, host=host, port=http_port, log_level="info")
            )
        )
        log.info("HTTP listener on %s:%s", host, http_port)

    if plan["https"]:
        servers.append(
            uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=host,
                    port=https_port,
                    ssl_certfile=plan["certPath"],
                    ssl_keyfile=plan["keyPath"],
                    log_level="info",
                )
            )
        )
        log.info("HTTPS listener on %s:%s", host, https_port)

    if plan["mode"] != "off" and not plan["hasActiveCert"]:
        log.warning(
            "TLS mode is %r but no certificate is active — serving plain HTTP. "
            "Generate or activate a certificate in the admin interface.",
            plan["mode"],
        )

    if not servers:  # safety net: never leave the service unreachable
        log.warning("No listeners resolved from the TLS plan — defaulting to HTTP.")
        servers.append(uvicorn.Server(uvicorn.Config(app, host=host, port=http_port)))
    return servers


async def _serve_cycle(
    app,
    host: str,
    http_port: int,
    https_port: int,
    log: logging.Logger,
    restart_event: asyncio.Event,
    stop_event: asyncio.Event,
) -> bool:
    """Run one set of listeners until a restart or stop is requested.

    Returns True when the process should exit (stop), False to rebuild and go
    round again (restart).
    """
    servers = _build_servers(app, host, http_port, https_port, log)
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
        server.should_exit = True  # graceful: finish in-flight requests, then close
    await asyncio.gather(*serve_tasks, return_exceptions=True)
    for waiter in (restart_wait, stop_wait):
        waiter.cancel()

    return stop_event.is_set()


async def _main(
    app, host: str, http_port: int, https_port: int, pid_path: Path, name: str
) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    )
    log = logging.getLogger(f"{name}-launcher")
    loop = asyncio.get_running_loop()
    restart_event = asyncio.Event()
    stop_event = asyncio.Event()

    loop.add_signal_handler(signal.SIGHUP, restart_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)
    loop.add_signal_handler(signal.SIGINT, stop_event.set)

    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    log.info("%s launcher pid %s — SIGHUP restarts listeners", name, os.getpid())
    try:
        while True:
            should_stop = await _serve_cycle(
                app, host, http_port, https_port, log, restart_event, stop_event
            )
            if should_stop:
                break
            restart_event.clear()
            log.info("↻ restarting %s listeners with the current TLS plan", name)
    finally:
        try:
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass
        log.info("%s launcher stopped", name)


def run(
    app, *, host: str, http_port: int, https_port: int, pid_path: Path, name: str
) -> None:
    """Serve ``app`` under the TLS plan, rebinding on SIGHUP. Blocks until stopped."""
    asyncio.run(_main(app, host, http_port, https_port, pid_path, name))
