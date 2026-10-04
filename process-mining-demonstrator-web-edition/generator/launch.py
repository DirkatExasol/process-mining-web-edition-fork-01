"""Background demo-event generator — a single standalone process (shell or Docker).

It learns a process's structure from an EXISTING project (the same Markov directly-follows
model the Simulation view uses), then every few seconds emits ONE full synthetic journey
into a target project's JOURNEYS table. Point an A-Chart (with auto-refresh on) or the
Dashboard at that project and you see data arriving live.

What it reads from the source project to shape the journeys:
  * the directly-follows graph (transition probabilities + per-edge timing),
  * the entry/end steps (so a walk starts and stops where real cases do),
  * the META_1/2/3 value combinations (sampled per journey, keeping their correlation),
  * the STEP → STEP_ID map of the TARGET project (so rows join the transition query).

Usage (minimal):
  python generator/launch.py --host 127.0.0.1 --port 8563 --user sys --password exasol \
      --schema PM_PROD --project 1 --insecure

Common options:
  --target-project N   write into a different project than the one learned from (default: same)
  --min 5 --max 60     seconds between journeys, drawn uniformly in [min, max]
  --max-steps 60       safety cap on a single journey's length (cyclic graphs)
  --count 0            stop after N journeys (0 = run forever, until Ctrl-C / SIGTERM)
  --tls / --no-tls     TLS to Exasol (default: --tls); --insecure skips cert verification
  --fingerprint HEX    pin the server certificate (sha-256) instead of --insecure
  --seed N             deterministic RNG (for reproducible demos)

Runs until SIGINT/SIGTERM; a transient DB error is logged and retried on the next tick.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import random
import signal
import sys
import uuid
from datetime import datetime

# This process lives outside the `app` package (a sibling tool, like mcp/ and sink/), so make
# the backend importable by path and reuse its model + the Simulation Markov walk.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.db.manager import DatabaseManager, friendly_error  # noqa: E402
from app.db.repository import ProcessRepository  # noqa: E402
from app.models import DatabaseServer, FilterSpec, SampleSet  # noqa: E402
from app.services.simulation import MarkovModel, _simulate_journey  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s generator: %(message)s"
)
log = logging.getLogger("generator")

F0 = FilterSpec(sampleSet=SampleSet.original)


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Background demo-event generator.")
    p.add_argument("--host", default=os.environ.get("PMG_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PMG_PORT", "8563")))
    p.add_argument("--user", default=os.environ.get("PMG_USER", "sys"))
    p.add_argument("--password", default=os.environ.get("PMG_PASSWORD", "exasol"))
    p.add_argument("--schema", default=os.environ.get("PMG_SCHEMA", ""), required=not os.environ.get("PMG_SCHEMA"))
    p.add_argument("--project", type=int, required=not os.environ.get("PMG_PROJECT"),
                   default=int(os.environ.get("PMG_PROJECT", "0")) or None,
                   help="source project id to learn the structure from")
    p.add_argument("--target-project", type=int, default=None,
                   help="project id to write journeys into (default: same as --project)")
    p.add_argument("--min", type=float, default=float(os.environ.get("PMG_MIN", "5")))
    p.add_argument("--max", type=float, default=float(os.environ.get("PMG_MAX", "60")))
    p.add_argument("--max-steps", type=int, default=60)
    p.add_argument("--count", type=int, default=0, help="stop after N journeys (0 = forever)")
    p.add_argument("--tls", dest="tls", action="store_true", default=True)
    p.add_argument("--no-tls", dest="tls", action="store_false")
    p.add_argument("--insecure", action="store_true", help="skip TLS certificate verification")
    p.add_argument("--fingerprint", default="", help="pin the server cert SHA-256 (hex)")
    p.add_argument("--min-rsa-bits", type=int, default=2048)
    p.add_argument("--seed", type=int, default=None)
    a = p.parse_args()
    if a.min <= 0 or a.max < a.min:
        p.error("--min must be > 0 and --max >= --min")
    return a


def _server(a: argparse.Namespace) -> DatabaseServer:
    cert_mode = "insecure" if a.insecure else ("fingerprint" if a.fingerprint else "verify")
    return DatabaseServer(
        host=a.host, port=a.port, username=a.user, useTLS=a.tls,
        certModeRaw=cert_mode, fingerprint=a.fingerprint, minRSAKeySizeBits=a.min_rsa_bits,
        **{"schema": a.schema},
    )


def _connect(a: argparse.Namespace) -> DatabaseManager:
    server = _server(a)
    mgr = DatabaseManager(load_legacy_active=False)
    mgr._conn = mgr._open(server, a.password)
    mgr.is_connected = True
    mgr._reopen_server = server
    mgr._active_password = a.password
    mgr.use_materialized_transitions = False
    return mgr


def _md5_event_id() -> str:
    return hashlib.md5(uuid.uuid4().bytes).hexdigest()  # 32-char hex → HASHTYPE(16 BYTE)


def _sq(value: str) -> str:
    return (value or "").replace("'", "''")


class _MetaSampler:
    """Samples a (META_1, META_2, META_3) triple from the source project's observed
    combinations, weighted by how many journeys carry each — so generated journeys keep the
    same attribute mix (and correlation) as the real data."""

    def __init__(self, triples: list[tuple[tuple[str, str, str], int]]):
        self._choices = [t for t, _ in triples] or [("", "", "")]
        self._weights = [w for _, w in triples] or [1]

    def sample(self, rng: random.Random) -> tuple[str, str, str]:
        return rng.choices(self._choices, weights=self._weights, k=1)[0]


async def _load_meta_triples(repo: ProcessRepository, pid: int) -> _MetaSampler:
    res = await repo.db.execute(
        "SELECT META_1, META_2, META_3, COUNT(DISTINCT EVENT_ID) "
        f"FROM JOURNEYS WHERE PROJECT_ID = {int(pid)} "
        "AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL) "
        "GROUP BY META_1, META_2, META_3"
    )
    triples = [
        ((str(r[0] or ""), str(r[1] or ""), str(r[2] or "")), int(r[3] or 0))
        for r in res.rows if (r[3] or 0) > 0
    ]
    return _MetaSampler(triples)


async def _load_step_ids(repo: ProcessRepository, pid: int) -> dict[str, int]:
    res = await repo.db.execute(
        f"SELECT STEP, STEP_ID FROM STEPS WHERE PROJECT_ID = {int(pid)} AND STEP_ID IS NOT NULL"
    )
    out: dict[str, int] = {}
    for r in res.rows:
        try:
            out[str(r[0])] = int(r[1])
        except (TypeError, ValueError):
            pass
    return out


def _insert_sql(target_pid: int, eid: str, events, step_ids: dict[str, int],
                meta: tuple[str, str, str]) -> str | None:
    m1, m2, m3 = meta
    rows = []
    for e in events:
        sid = step_ids.get(e.step)
        if sid is None:
            continue  # a step with no activity id in the target can't be written reliably
        rows.append(
            f"({int(target_pid)}, '{eid}', '{_sq(e.step)}', {sid}, "
            f"TIMESTAMP '{e.timestamp:%Y-%m-%d %H:%M:%S}', "
            f"'{_sq(m1)}', '{_sq(m2)}', '{_sq(m3)}', 'ORIGINAL')"
        )
    if not rows:
        return None
    return (
        "INSERT INTO JOURNEYS (PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME, "
        "META_1, META_2, META_3, SAMPLE_SET) VALUES " + ", ".join(rows)
    )


async def _run(a: argparse.Namespace) -> None:
    rng = random.Random(a.seed)
    if a.seed is not None:
        import app.services.simulation as _sim
        _sim.random.seed(a.seed)  # the Markov walk uses the module's random

    target_pid = a.target_project if a.target_project is not None else a.project

    log.info("connecting to %s:%s schema %s (TLS=%s)…", a.host, a.port, a.schema, a.tls)
    mgr = _connect(a)
    repo = ProcessRepository(mgr)
    repo.active_sample_set = SampleSet.original

    log.info("learning the process structure from project %s…", a.project)
    graph = await repo.load_graph(str(a.project), F0)
    if not graph.transitions:
        log.error("project %s has no transitions to learn from — nothing to generate.", a.project)
        await mgr.disconnect()
        return
    model = MarkovModel(graph, graph.steps, set())
    if not model.start_steps:
        log.error("could not determine a start step for project %s.", a.project)
        await mgr.disconnect()
        return
    metas = await _load_meta_triples(repo, a.project)
    step_ids = await _load_step_ids(repo, target_pid)
    if not step_ids:
        log.error("target project %s has no STEPS with activity ids — cannot write journeys.", target_pid)
        await mgr.disconnect()
        return
    log.info("ready: %d steps, %d transitions. Emitting a journey every %g–%g s into project %s. Ctrl-C to stop.",
             len(graph.steps), len(graph.transitions), a.min, a.max, target_pid)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover — not on Windows
            pass

    emitted = 0
    while not stop.is_set():
        delay = rng.uniform(a.min, a.max)
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            break  # stop signalled during the wait
        except asyncio.TimeoutError:
            pass

        result = _simulate_journey(model, datetime.now().replace(microsecond=0),
                                   _md5_event_id(), a.max_steps)
        if result is None:
            continue
        events, _path, _cycle = result
        eid = events[0].journeyId  # the md5 we passed in
        sql = _insert_sql(target_pid, eid, events, step_ids, metas.sample(rng))
        if sql is None:
            continue
        try:
            await mgr.execute(sql)
            emitted += 1
            log.info("emitted journey %s: %d steps, %s → %s",
                     eid[:8], len(events), events[0].step, events[-1].step)
        except Exception as exc:  # noqa: BLE001 — keep running across a transient DB blip
            log.warning("write failed (%s) — retrying on the next tick", friendly_error(exc))
            try:
                await mgr.disconnect()
            except Exception:  # noqa: BLE001
                pass
            mgr = _connect(a)
            repo = ProcessRepository(mgr)
            continue

        if a.count and emitted >= a.count:
            log.info("reached --count %d; stopping.", a.count)
            break

    log.info("stopped after emitting %d journey(s).", emitted)
    try:
        await mgr.disconnect()
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    asyncio.run(_run(_args()))


if __name__ == "__main__":
    main()
