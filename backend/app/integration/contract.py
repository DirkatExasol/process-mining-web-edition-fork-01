"""The extractor ⇄ abstraction-layer contract.

This module defines the *stable* public API that every extractor programs against.
An extractor never touches the database directly: the abstraction layer hands it an
:class:`IngestSession` bound to the target schema (of the user's selected
connection) and the extractor pushes records through that session. The layer counts
every row for the live status/progress and owns the connection lifecycle.

See the "Integration abstraction layer" section of the README for the full guide.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable


class ColumnType(str, Enum):
    """The portable column types an extractor declares. The abstraction layer maps
    each to a concrete database type, so extractors stay database-agnostic."""

    STRING = "string"
    INT = "int"
    DECIMAL = "decimal"
    TIMESTAMP = "timestamp"
    BOOL = "bool"


@dataclass(frozen=True)
class ExtractorInfo:
    """Immutable identity of an extractor, shown in the console and used to select
    it. ``id`` must be globally unique and stable (it is the plug-in key)."""

    id: str
    name: str
    version: str
    description: str = ""

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }


@dataclass
class ExtractResult:
    """What an extractor returns from :meth:`Extractor.run`. Purely informational —
    the layer already counts pushed rows itself; this lets the extractor add a
    human-readable summary."""

    records: int = 0
    tables: tuple[str, ...] = ()
    detail: str = ""


class IngestError(Exception):
    """Raised by the abstraction layer for an invalid ingest operation (unknown
    table, bad identifier, type mismatch). Extractors may let it propagate — the
    layer records it as the run's failure."""


class IngestSession(Protocol):
    """The ONLY handle an extractor is given to the target database.

    The abstraction layer creates one per run, bound to the selected connection's
    schema, and passes it to :meth:`Extractor.run`. Every method is synchronous and
    safe to call repeatedly; the layer batches writes and tallies rows for the
    live status. Extractors must not hold on to the session after ``run`` returns.
    """

    @property
    def schema(self) -> str:
        """The target schema every table in this session is written to (taken from
        the user's selected connection)."""
        ...

    def define_table(
        self,
        table: str,
        columns: Mapping[str, ColumnType],
        *,
        keys: Sequence[str] = (),
    ) -> None:
        """Declare (and create if absent) the target table. Idempotent — safe to
        call on every run. ``columns`` maps column name → :class:`ColumnType`;
        ``keys`` names the business-key columns (informational for now). Must be
        called for a table before :meth:`push`."""
        ...

    def push(self, table: str, rows: Iterable[Mapping[str, Any]]) -> int:
        """Append ``rows`` to a previously :meth:`define_table`-d table and return
        the number written. Each row is a mapping of column name → value; missing
        columns become NULL, unknown columns raise :class:`IngestError`. Values are
        coerced/escaped by the layer. Rows are streamed in batches, so an extractor
        can pass a generator over a very large source without buffering it all."""
        ...

    def log(self, message: str) -> None:
        """Emit a progress line surfaced in the layer status (recent messages are
        kept, older ones dropped)."""
        ...


@runtime_checkable
class Extractor(Protocol):
    """A plug-in that reads some source and pushes records through an
    :class:`IngestSession`. Implementations register with the abstraction layer and
    are selected by :attr:`ExtractorInfo.id`.

    ``run`` is synchronous (the layer runs it off the event loop) and should push
    incrementally rather than buffer everything. Raising propagates as the run's
    failure; returning an :class:`ExtractResult` marks success.
    """

    info: ExtractorInfo

    def run(self, session: IngestSession) -> ExtractResult:
        ...
