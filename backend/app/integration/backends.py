"""Where the abstraction layer actually writes ingested records.

An :class:`IngestBackend` is the seam between the database-agnostic ingest API and a
concrete target database. Two implementations ship:

* :class:`InMemoryIngestBackend` — keeps tables in memory. The default for local
  development and the reference target for tests (no database required).
* :class:`SqlIngestBackend` — generates schema-qualified DDL/DML and runs it through
  a caller-supplied ``run_sql`` (the production path binds this to the user's Exasol
  connection). Identifiers are strictly validated and values defensively escaped.

Extractors never see a backend — they only see the :class:`~.contract.IngestSession`.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from .contract import ColumnType, IngestError

# A conservative identifier grammar (letters, digits, underscore; not starting with a
# digit; ≤128 chars). Anything else is rejected rather than escaped, so a table or
# column name can never inject SQL.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

# Portable → Exasol column types.
_SQL_TYPE = {
    ColumnType.STRING: "VARCHAR(2000000)",
    ColumnType.INT: "DECIMAL(18,0)",
    ColumnType.DECIMAL: "DECIMAL(36,6)",
    ColumnType.TIMESTAMP: "TIMESTAMP",
    ColumnType.BOOL: "BOOLEAN",
}

_MAX_BATCH = 1000  # rows per INSERT statement


def valid_identifier(name: str) -> str:
    """Return ``name`` if it is a safe SQL identifier, else raise IngestError."""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise IngestError(f"Invalid SQL identifier: {name!r}")
    return name


class IngestBackend(Protocol):
    """Concrete write target for the abstraction layer."""

    def create_table(
        self, schema: str, table: str, columns: Mapping[str, ColumnType], keys: Sequence[str]
    ) -> None:
        ...

    def insert(
        self, schema: str, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]
    ) -> int:
        ...


class InMemoryIngestBackend:
    """A dependency-free target: tables and rows live in dictionaries. Used for dev
    and as the tested reference implementation of the ingest semantics."""

    def __init__(self) -> None:
        # schema → table → {"columns": {name: type}, "rows": [ {col: value} ]}
        self.tables: dict[str, dict[str, dict[str, Any]]] = {}

    def _table(self, schema: str, table: str) -> dict[str, Any] | None:
        return self.tables.get(schema, {}).get(table)

    def create_table(self, schema, table, columns, keys) -> None:
        valid_identifier(schema)
        valid_identifier(table)
        for col in columns:
            valid_identifier(col)
        existing = self._table(schema, table)
        if existing is None:
            self.tables.setdefault(schema, {})[table] = {
                "columns": dict(columns),
                "keys": list(keys),
                "rows": [],
            }

    def insert(self, schema, table, columns, rows) -> int:
        tbl = self._table(schema, table)
        if tbl is None:
            raise IngestError(f"Table {schema}.{table} was not defined.")
        for row in rows:
            tbl["rows"].append(dict(zip(columns, row)))
        return len(rows)


class SqlIngestBackend:
    """Generates schema-qualified SQL and runs it through ``run_sql`` (a synchronous
    ``str -> None`` callable). The production wiring binds ``run_sql`` to the user's
    Exasol connection; tests bind it to a recorder to assert the generated SQL.

    Identifiers are validated (never escaped-and-hoped); values are rendered as
    strictly-escaped literals. Extractor code is trusted, but the layer still escapes
    defensively so a malformed source value can't corrupt a statement.
    """

    def __init__(self, run_sql: Callable[[str], Any]) -> None:
        self._run = run_sql

    # ── DDL ───────────────────────────────────────────────────────────────────
    def create_table(self, schema, table, columns, keys) -> None:
        q = self._qualified(schema, table)
        cols = ", ".join(
            f'"{valid_identifier(name)}" {_SQL_TYPE[ctype]}' for name, ctype in columns.items()
        )
        self._run(f"CREATE TABLE IF NOT EXISTS {q} ({cols})")

    # ── DML ───────────────────────────────────────────────────────────────────
    def insert(self, schema, table, columns, rows) -> int:
        if not rows:
            return 0
        q = self._qualified(schema, table)
        col_list = ", ".join(f'"{valid_identifier(c)}"' for c in columns)
        written = 0
        for start in range(0, len(rows), _MAX_BATCH):
            batch = rows[start : start + _MAX_BATCH]
            values = ", ".join(
                "(" + ", ".join(_literal(v) for v in row) + ")" for row in batch
            )
            self._run(f"INSERT INTO {q} ({col_list}) VALUES {values}")
            written += len(batch)
        return written

    @staticmethod
    def _qualified(schema: str, table: str) -> str:
        return f'"{valid_identifier(schema)}"."{valid_identifier(table)}"'


def _literal(value: Any) -> str:
    """Render a Python value as a safe SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise IngestError(f"Non-finite numeric value: {value!r}")
        return repr(value)
    if isinstance(value, datetime):
        return f"TIMESTAMP '{value.strftime('%Y-%m-%d %H:%M:%S.%f')[:23]}'"
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    # Everything else is treated as text: double single-quotes, strip NULs.
    text = str(value).replace("\x00", "").replace("'", "''")
    return f"'{text}'"
