"""Opening an ingest destination.

A run's destination is a *stored* connection, opened here with the credentials the
admin saved — not with whatever the caller happens to have connected in their browser
session. That keeps every trigger identical: the manual run from the console, the
watchdog loop, and (soon) a remote push all name a connection by id and land in the
same place. Callers own the returned handle and must close it.
"""

from __future__ import annotations


def open_stored_connection(conn):
    """Open ``conn`` and return ``(raw, run_sql)`` — a synchronous SQL runner bound to
    it (rows for SELECT, empty otherwise).

    Autocommit is switched off so the abstraction layer's transaction bracket, not the
    driver, decides when work becomes durable.
    """
    from ..db.manager import DatabaseManager
    from ..models import DatabaseServer

    server = DatabaseServer(
        id="integration", host=conn.host, port=conn.port, username=conn.username,
        useTLS=conn.use_tls, certModeRaw=conn.cert_mode, fingerprint=conn.fingerprint,
        minRSAKeySizeBits=conn.min_rsa_bits, **{"schema": conn.schema or ""},
    )
    mgr = DatabaseManager.__new__(DatabaseManager)  # no store side effects
    raw = mgr._open(server, conn.password)
    raw.set_autocommit(False)

    def run_sql(sql: str):
        st = raw.execute(sql)
        return [list(r) for r in st.fetchall()] if st.result_type == "resultSet" else []

    return raw, run_sql
