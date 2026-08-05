"""Live status of the abstraction layer for one user.

A single :class:`LayerStatus` reflects the most recent (or in-flight) extraction
run: which extractor, which target schema, how many rows have been pushed so far,
and any error. The console polls it. It is mutated only by the abstraction layer
(under its lock) as a run progresses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

_MAX_MESSAGES = 50  # recent log lines kept for display


class LayerState(str, Enum):
    IDLE = "idle"  # nothing has run yet, or the last run is cleared
    RUNNING = "running"  # an extraction is in progress
    COMPLETED = "completed"  # the last run finished successfully
    FAILED = "failed"  # the last run raised


@dataclass
class LayerStatus:
    """A snapshot of one user's abstraction-layer activity."""

    state: LayerState = LayerState.IDLE
    extractor_id: str | None = None
    extractor_name: str | None = None
    # Origin of the run, for the console's pipeline canvas (the source it read from and
    # the source type used to parse it). Set by whoever triggers the run — a manual run,
    # a watchdog, or an API push — so the canvas stays live regardless of the trigger.
    source_name: str | None = None
    source_type_name: str | None = None
    connection_id: str | None = None
    connection_name: str | None = None
    schema: str | None = None
    records_pushed: int = 0
    # Transaction brackets committed so far in this run (see the layer's
    # transaction_rows) — surfaced so the console can show durable progress.
    commits: int = 0
    # Progress for a progress bar: items processed so far, and the total (0 = unknown).
    records_done: int = 0
    records_total: int = 0
    tables_touched: list[str] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None
    messages: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        self.messages.append(message)
        if len(self.messages) > _MAX_MESSAGES:
            del self.messages[: len(self.messages) - _MAX_MESSAGES]

    def touch_table(self, table: str) -> None:
        if table not in self.tables_touched:
            self.tables_touched.append(table)

    def public(self) -> dict:
        return {
            "state": self.state.value,
            "extractorId": self.extractor_id,
            "extractorName": self.extractor_name,
            "sourceName": self.source_name,
            "sourceTypeName": self.source_type_name,
            "connectionId": self.connection_id,
            "connectionName": self.connection_name,
            "schema": self.schema,
            "recordsPushed": self.records_pushed,
            "commits": self.commits,
            "recordsDone": self.records_done,
            "recordsTotal": self.records_total,
            "tablesTouched": list(self.tables_touched),
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "lastError": self.last_error,
            "messages": list(self.messages),
        }
