"""Canonical process-mining schema — the single source of truth for the tables
the app reads and writes, and a helper that provisions them on demand.

The source tables (PROJECTS, JOURNEYS, STEPS, METAS) normally arrive with the
customer's data; NOTES is created lazily by the app. This module lets an operator
(an admin, or a power user from the app) create a *fresh* schema with the full,
empty table structure so process-mining data can be loaded into it — provided the
database account has the CREATE SCHEMA / CREATE TABLE privileges (which only a
database administrator can grant; the app cannot).

All statements use IF NOT EXISTS so provisioning is idempotent and never disturbs
an existing schema's data.
"""

from __future__ import annotations

# Kept byte-for-byte in sync with ProcessRepository.ensure_notes_table (which
# imports this constant), so a provisioned NOTES table matches what the app uses.
NOTES_DDL = """
CREATE TABLE IF NOT EXISTS NOTES (
    ID              VARCHAR(36)   NOT NULL,
    PROJECT_ID      VARCHAR(100)  NOT NULL,
    NOTES_DATE      TIMESTAMP     NOT NULL,
    EDITED_DATE     TIMESTAMP,
    NOTE_USER       VARCHAR(200)  DEFAULT '',
    NOTE            VARCHAR(100000) DEFAULT '',
    IS_SHARED       BOOLEAN       DEFAULT FALSE,
    EDITED_BY       VARCHAR(200)  DEFAULT '',
    IMPORTANCE      VARCHAR(20)   DEFAULT 'NORMAL',
    RESOLVED        BOOLEAN       DEFAULT FALSE,
    TITLE           VARCHAR(500)  DEFAULT '',
    TARGET_TYPE     VARCHAR(10)   DEFAULT 'node',
    TARGET_FROM     VARCHAR(500)  DEFAULT '',
    TARGET_TO       VARCHAR(500),
    FILTER_SNAPSHOT VARCHAR(4000),
    PRIMARY KEY (ID)
)
"""

_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS PROJECTS (
    PROJECT_ID  VARCHAR(100)  NOT NULL,
    TITLE       VARCHAR(500)  DEFAULT '',
    DESCRIPTION VARCHAR(2000) DEFAULT '',
    PRIMARY KEY (PROJECT_ID)
)
"""

# The event log: one row per (event, step). STEP_ID orders steps that share an
# EVENT_TIME. SAMPLE_SET tags rows copied into a sample ('ORIGINAL' = source data).
#
# DISTRIBUTE BY EVENT_ID co-locates every event of a journey on one cluster node,
# so the transition query's LEAD() OVER (PARTITION BY EVENT_ID ...) and every
# filter's GROUP BY EVENT_ID run node-local with no cross-node redistribution.
# EVENT_ID is high-cardinality, so rows spread evenly.
#
# PARTITION BY EVENT_TIME lets Exasol prune by date range — chiefly the
# "active in window" EVENT_ID selection behind the last-N-days default and the
# date filter. (The main scan still fetches whole journeys by EVENT_ID, which can
# span partitions, so pruning helps the ID selection more than the final scan.)
# The partition column must differ from the distribution column, which holds here
# (EVENT_TIME vs EVENT_ID). If EVENT_TIME cardinality is extreme, a day-truncated
# EVENT_DATE column would partition more coarsely — but that needs an extra column
# the data load must populate, so EVENT_TIME is the zero-ETL-change default.
#
# Existing tables are unaffected by IF NOT EXISTS — apply to those with
#   ALTER TABLE JOURNEYS DISTRIBUTE BY EVENT_ID;
#   ALTER TABLE JOURNEYS PARTITION  BY EVENT_TIME;
_JOURNEYS_DDL = """
CREATE TABLE IF NOT EXISTS JOURNEYS (
    PROJECT_ID VARCHAR(100)  NOT NULL,
    EVENT_ID   VARCHAR(200)  NOT NULL,
    STEP       VARCHAR(500)  NOT NULL,
    STEP_ID    DECIMAL(18,0),
    EVENT_TIME TIMESTAMP     NOT NULL,
    META_1     VARCHAR(1000),
    META_2     VARCHAR(1000),
    META_3     VARCHAR(1000),
    SAMPLE_SET VARCHAR(20)   DEFAULT 'ORIGINAL',
    DISTRIBUTE BY EVENT_ID,
    PARTITION BY EVENT_TIME
)
"""

# Per-step presentation and scoring, edited from the app's Step editor.
_STEPS_DDL = """
CREATE TABLE IF NOT EXISTS STEPS (
    PROJECT_ID     VARCHAR(100)  NOT NULL,
    STEP           VARCHAR(500)  NOT NULL,
    DESCRIPTION    VARCHAR(2000) DEFAULT '',
    BG_COLOR       VARCHAR(30)   DEFAULT '',
    FG_COLOR       VARCHAR(30)   DEFAULT '',
    SCORE          DECIMAL(18,2),
    SHAPE          VARCHAR(50)   DEFAULT '',
    END_OF_PROCESS BOOLEAN       DEFAULT FALSE,
    BELONGS_TO     VARCHAR(500),
    PRIMARY KEY (PROJECT_ID, STEP)
)
"""

# Human-readable titles for the three META columns, per project.
_METAS_DDL = """
CREATE TABLE IF NOT EXISTS METAS (
    PROJECT_ID   VARCHAR(100) NOT NULL,
    META_1_TITLE VARCHAR(500) DEFAULT '',
    META_2_TITLE VARCHAR(500) DEFAULT '',
    META_3_TITLE VARCHAR(500) DEFAULT '',
    PRIMARY KEY (PROJECT_ID)
)
"""

# (name, DDL) in creation order. NOTES is included so a provisioned schema is
# immediately complete for both reads and the app's own writes.
PROCESS_MINING_TABLES: list[tuple[str, str]] = [
    ("PROJECTS", _PROJECTS_DDL),
    ("JOURNEYS", _JOURNEYS_DDL),
    ("STEPS", _STEPS_DDL),
    ("METAS", _METAS_DDL),
    ("NOTES", NOTES_DDL),
]

TABLE_NAMES: list[str] = [name for name, _ in PROCESS_MINING_TABLES]


# Optional pre-materialised directly-follows pairs (backlog item #3). Built on
# demand per connection; the transition query reads it instead of running the
# LEAD() window on every request. One row per consecutive step-pair, carrying the
# precomputed gap so the map's timing aggregates are pure MIN/MAX/AVG/STDDEV.
#
# Built with CREATE TABLE AS SELECT so every column INHERITS its type from
# JOURNEYS/STEPS — critically EVENT_ID, which varies by deployment (VARCHAR,
# HASHTYPE, DECIMAL, …). Hard-coding it (e.g. VARCHAR) breaks the read query:
# the semi-join `TRANSITIONS_RAW.EVENT_ID IN (SELECT JOURNEYS.EVENT_ID …)` then
# compares mismatched types and Exasol raises "Incomparable Types". Distribution
# is applied afterwards with ALTER (CTAS can't declare it inline).
MATERIALIZED_TRANSITIONS_TABLE = "TRANSITIONS_RAW"


def _quote_ident(name: str) -> str:
    """Quote an Exasol identifier, guarding against injection in the schema name."""
    return '"' + name.replace('"', '""') + '"'


async def rebuild_materialized_transitions(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    schema: str,
    use_tls: bool = False,
    cert_mode: str = "verify",
    fingerprint: str = "",
    min_rsa_bits: int = 2048,
) -> dict:
    """(Re)build ``TRANSITIONS_RAW`` in ``schema`` from its ``JOURNEYS`` table.

    Runs the expensive ``LEAD()`` pairing once and stores the result, so the
    per-request transition query can drop the window function. The fresh copy is
    built in a staging table alongside the live one and swapped in with a RENAME,
    so readers are never blocked by the build and only ever see a complete table
    (a sub-millisecond gap during the swap falls back to the live query).

    Returns ``{"ok", "error", "rows", "built_at"}`` — ``rows`` is the pair count,
    ``built_at`` an ISO-8601 UTC timestamp. Idempotent and safe to re-run.
    """
    import asyncio
    from datetime import datetime, timezone

    from ..models import DatabaseServer
    from .manager import DatabaseManager, friendly_error

    schema = (schema or "").strip()
    if not schema:
        return {"ok": False, "error": "A schema name is required.", "rows": 0, "built_at": None}

    server = DatabaseServer(
        id="materialize",
        host=host,
        port=port,
        username=username,
        useTLS=use_tls,
        certModeRaw=cert_mode,
        fingerprint=fingerprint,
        minRSAKeySizeBits=min_rsa_bits,
        **{"schema": ""},
    )
    mgr = DatabaseManager.__new__(DatabaseManager)  # no store side effects
    ident = _quote_ident(schema)
    final = MATERIALIZED_TRANSITIONS_TABLE
    stage = f"{final}_STAGE"

    def _run() -> int:
        conn = mgr._open(server, password)
        try:
            conn.execute(f"OPEN SCHEMA {ident}")
            # Build the fresh copy beside the live table so reads are unaffected.
            # CTAS ⇒ column types (esp. EVENT_ID) match JOURNEYS/STEPS exactly.
            conn.execute(
                f"""
                CREATE OR REPLACE TABLE {stage} AS
                SELECT PROJECT_ID, EVENT_ID, FROM_STEP, TO_STEP, FROM_TIME, TO_TIME,
                       SECONDS_BETWEEN(TO_TIME, FROM_TIME) AS DUR_SECS, SAMPLE_SET
                FROM (
                    SELECT PROJECT_ID, EVENT_ID, SAMPLE_SET,
                           STEP       AS FROM_STEP,
                           EVENT_TIME AS FROM_TIME,
                           LEAD(STEP)       OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_STEP,
                           LEAD(EVENT_TIME) OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_TIME
                    FROM JOURNEYS
                ) AS t
                WHERE TO_STEP IS NOT NULL AND TO_TIME IS NOT NULL
                """
            )
            # Co-locate by EVENT_ID for the semi-join. Distribution is a pure
            # optimisation, so a failure here must not abort the rebuild.
            try:
                conn.execute(f"ALTER TABLE {stage} DISTRIBUTE BY EVENT_ID")
            except Exception:  # noqa: BLE001
                pass
            rows = conn.execute(f"SELECT COUNT(*) FROM {stage}").fetchval()
            # Swap the fresh copy in. DROP+RENAME leaves a sub-ms window with no
            # live table; the query layer falls back to the live LEAD() for that.
            conn.execute(f"DROP TABLE IF EXISTS {final}")
            conn.execute(f"RENAME TABLE {stage} TO {final}")
            conn.commit()
            return int(rows or 0)
        finally:
            conn.close()

    try:
        rows = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": friendly_error(exc), "rows": 0, "built_at": None}
    return {
        "ok": True,
        "error": None,
        "rows": rows,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def provision_process_mining_schema(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    schema: str,
    use_tls: bool = False,
    cert_mode: str = "verify",
    fingerprint: str = "",
    min_rsa_bits: int = 2048,
) -> dict:
    """Create ``schema`` (if absent) and every process-mining table inside it.

    Connects with the supplied credentials, so the account must hold CREATE SCHEMA
    and CREATE TABLE rights. Returns ``{"ok", "error", "created": [names]}`` — a
    friendly error string on failure, with ``created`` listing what was made before
    the failure. Idempotent: re-running against an existing schema is a no-op.
    """
    import asyncio

    from ..models import DatabaseServer
    from .manager import DatabaseManager, friendly_error

    schema = (schema or "").strip()
    if not schema:
        return {"ok": False, "error": "A schema name is required.", "created": []}

    # Connect WITHOUT opening the target schema — it may not exist yet.
    server = DatabaseServer(
        id="provision",
        host=host,
        port=port,
        username=username,
        useTLS=use_tls,
        certModeRaw=cert_mode,
        fingerprint=fingerprint,
        minRSAKeySizeBits=min_rsa_bits,
        **{"schema": ""},
    )
    mgr = DatabaseManager.__new__(DatabaseManager)  # no store side effects
    ident = _quote_ident(schema)
    created: list[str] = []

    def _run() -> None:
        conn = mgr._open(server, password)
        try:
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {ident}")
            created.append(f"schema {schema}")
            conn.execute(f"OPEN SCHEMA {ident}")
            for name, ddl in PROCESS_MINING_TABLES:
                conn.execute(ddl)
                created.append(name)
            conn.commit()
        finally:
            conn.close()

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": friendly_error(exc), "created": created}
    return {"ok": True, "error": None, "created": created}
