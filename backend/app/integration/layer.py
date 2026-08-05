"""The abstraction layer: a registry of extractors plus the runner that drives one
against an :class:`IngestSession` and tracks per-user status.

Design in one paragraph: extractors *register* here at import time (plug-in style).
To run one, the layer opens an :class:`IngestSession` bound to a chosen
:class:`~.backends.IngestBackend` and target schema, marks the user's
:class:`~.status.LayerStatus` ``running``, executes ``extractor.run(session)`` off
the event loop, and flips the status to ``completed``/``failed``. Every
``session.push`` tallies rows into that status so the console can watch progress.

Extractor *management* (enabling, scheduling, triggering from the UI) and the first
concrete extractor are built on top of this in later stages; this module is the
stable core they plug into.
"""

from __future__ import annotations

import asyncio
import re
import threading
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .. import log_events as logx
from .backends import IngestBackend, valid_identifier
from .contract import ColumnType, ExtractResult, Extractor, ExtractorInfo, IngestError
from .status import LayerState, LayerStatus


_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Session:
    """Concrete :class:`~.contract.IngestSession`. Delegates writes to an
    :class:`IngestBackend` and reports progress into a :class:`LayerStatus` under a
    lock (``push`` may be called from the extractor's worker thread)."""

    def __init__(self, backend: IngestBackend, schema: str, status: LayerStatus, lock: threading.Lock) -> None:
        self._backend = backend
        self._schema = valid_identifier(schema)
        self._status = status
        self._lock = lock
        self._columns: dict[str, list[str]] = {}  # table → declared column order

    @property
    def schema(self) -> str:
        return self._schema

    def define_table(
        self, table: str, columns: Mapping[str, ColumnType], *, keys: Sequence[str] = ()
    ) -> None:
        if not columns:
            raise IngestError(f"Table {table!r} must declare at least one column.")
        self._backend.create_table(self._schema, table, dict(columns), list(keys))
        self._columns[table] = list(columns.keys())
        with self._lock:
            self._status.touch_table(table)

    def push(self, table: str, rows: Iterable[Mapping[str, Any]]) -> int:
        order = self._columns.get(table)
        if order is None:
            raise IngestError(f"Call define_table({table!r}, ...) before push().")
        known = set(order)
        written = 0
        # Stream in batches so a generator source is never fully buffered.
        batch: list[Sequence[Any]] = []
        for row in rows:
            unknown = row.keys() - known
            if unknown:
                raise IngestError(f"Unknown column(s) for {table}: {', '.join(sorted(unknown))}")
            batch.append([row.get(col) for col in order])
            if len(batch) >= 1000:
                written += self._flush(table, order, batch)
                batch = []
        if batch:
            written += self._flush(table, order, batch)
        return written

    def _flush(self, table: str, order: list[str], batch: list[Sequence[Any]]) -> int:
        n = self._backend.insert(self._schema, table, order, batch)
        with self._lock:
            self._status.records_pushed += n
        return n

    def log(self, message: str) -> None:
        with self._lock:
            self._status.note(message)

    def progress(self, done: int, total: int | None = None) -> None:
        with self._lock:
            self._status.records_done = done
            if total is not None:
                self._status.records_total = total

    def existing_keys(self, table: str, key_columns: Sequence[str]) -> set[tuple[str, ...]]:
        return self._backend.existing_keys(self._schema, table, list(key_columns))


class AbstractionLayer:
    """Registry of extractors + per-user run status. A process-wide singleton
    (``layer`` below)."""

    def __init__(self) -> None:
        self._extractors: dict[str, Extractor] = {}
        self._status: dict[str, LayerStatus] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()

    # ── registry ───────────────────────────────────────────────────────────────
    def register(self, extractor: Extractor) -> None:
        info = extractor.info
        # A URL/console-safe slug id, e.g. "csv-folder".
        if not _SLUG_RE.match(info.id or ""):
            raise ValueError(f"Extractor id {info.id!r} must be a slug (a-z, 0-9, '-').")
        with self._lock:
            if info.id in self._extractors:
                raise ValueError(f"An extractor with id {info.id!r} is already registered.")
            self._extractors[info.id] = extractor

    def unregister(self, extractor_id: str) -> None:
        with self._lock:
            self._extractors.pop(extractor_id, None)

    def get(self, extractor_id: str) -> Extractor | None:
        return self._extractors.get(extractor_id)

    def extractors(self) -> list[ExtractorInfo]:
        return [e.info for e in self._extractors.values()]

    # ── status ───────────────────────────────────────────────────────────────
    def status_for(self, user: str | None) -> LayerStatus:
        key = user or ""
        with self._lock:
            return self._status.setdefault(key, LayerStatus())

    # ── run ────────────────────────────────────────────────────────────────────
    async def run(
        self,
        *,
        user: str | None,
        extractor: "Extractor | str",
        backend: IngestBackend,
        schema: str,
        connection_id: str | None = None,
        connection_name: str | None = None,
        source_name: str | None = None,
        source_type_name: str | None = None,
    ) -> ExtractResult:
        """Run an extractor against ``backend``/``schema`` for ``user``, updating that
        user's status as it goes. ``extractor`` is a registered id, or a configured
        :class:`~.contract.Extractor` instance (e.g. a per-run FileExtractor). One
        concurrent run per user. The optional ``source_name`` / ``source_type_name`` /
        ``connection_name`` describe the run's origin for the console's pipeline canvas
        and are recorded verbatim in the user's status."""
        key = user or ""
        if isinstance(extractor, str):
            resolved = self._extractors.get(extractor)
            if resolved is None:
                raise IngestError(f"No extractor registered with id {extractor!r}.")
            extractor = resolved

        with self._lock:
            if key in self._running:
                raise IngestError("An extraction is already running for this user.")
            self._running.add(key)
            status = self._status.setdefault(key, LayerStatus())
            status.state = LayerState.RUNNING
            status.extractor_id = extractor.info.id
            status.extractor_name = extractor.info.name
            status.source_name = source_name
            status.source_type_name = source_type_name
            status.connection_id = connection_id
            status.connection_name = connection_name
            status.schema = schema
            status.records_pushed = 0
            status.records_done = 0
            status.records_total = 0
            status.tables_touched = []
            status.started_at = _now()
            status.finished_at = None
            status.last_error = None
            status.messages = []

        session = _Session(backend, schema, status, self._lock)
        try:
            result = await asyncio.to_thread(extractor.run, session)
            with self._lock:
                status.state = LayerState.COMPLETED
                status.finished_at = _now()
            logx.usage(
                f"extractor {extractor.info.id} pushed {status.records_pushed} rows to {schema}",
                username=user or "", operation="integration",
            )
            return result
        except Exception as exc:  # noqa: BLE001 — surfaced in status, not swallowed
            with self._lock:
                status.state = LayerState.FAILED
                status.finished_at = _now()
                status.last_error = str(exc)
            logx.warn(
                f"extractor {extractor.info.id} failed: {exc}",
                username=user or "", operation="integration",
            )
            raise
        finally:
            with self._lock:
                self._running.discard(key)


# Process-wide singleton the API and extractors share.
layer = AbstractionLayer()
