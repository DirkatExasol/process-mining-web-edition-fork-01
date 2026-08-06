"""File-source watchdog: auto-import newly-appended log lines.

A single background loop (started in the compute backend's lifespan) wakes every
``INTEGRATION_WATCHDOG_TICK_SECS`` and, for each File source with the watchdog enabled,
reads only the lines appended since that source's stored **checkpoint** (a byte offset
+ a size/head signature that detects truncation or rotation) and pushes them through the
abstraction layer into the source's configured destination connection. On success the
checkpoint advances so the same lines are never re-imported; on failure the offset stays
put and the error is recorded, so the next poll retries from where it left off.

The destination for a watchdog run is stored *with* the source (connection id + project
id), because the loop runs headless — there is no signed-in user or active connection.
It reuses the same stored connection credentials the admin rebuild job uses.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .. import log_events as logx
from ..config import INTEGRATION_WATCHDOG_ENABLED, INTEGRATION_WATCHDOG_TICK_SECS
from ..store.security import store
from .backends import (
    DEFAULT_TRANSACTION_ROWS,
    SqlIngestBackend,
    clamp_transaction_rows,
)
from .destinations import open_stored_connection as _open_run_sql
from .extractors import FileExtractor
from .files import FileAccessError, read_delta
from .layer import layer


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _due(checkpoint: dict | None, interval_secs: int) -> bool:
    """True if this source is due for a poll (never run, or interval elapsed)."""
    if not checkpoint or not checkpoint.get("updatedAt"):
        return True
    try:
        last = datetime.fromisoformat(checkpoint["updatedAt"])
    except (ValueError, TypeError):
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (_now() - last).total_seconds() >= interval_secs


async def poll_source(source) -> None:
    """Import a File source's newly-appended lines, if the watchdog is on and it's due.

    All errors are caught and recorded on the checkpoint — the watchdog must never crash
    its loop on one misconfigured source."""
    if source.kind != "file":
        return
    cfg = source.public()["config"]
    wd = cfg.get("watchdog") or {}
    if not wd.get("enabled"):
        return

    interval = max(5, int(wd.get("intervalSecs") or 30))
    checkpoint = store.get_source_checkpoint(source.id)
    if not _due(checkpoint, interval):
        return

    path = str(cfg.get("path") or "").strip()
    project_id = str(wd.get("projectId") or "").strip()
    connection_id = str(wd.get("connectionId") or "").strip()
    encoding = str(cfg.get("encoding") or "utf-8")
    transaction_rows = (
        clamp_transaction_rows(cfg.get("transactionRows"))
        if "transactionRows" in cfg else DEFAULT_TRANSACTION_ROWS
    )
    prev_offset = int(checkpoint["byteOffset"]) if checkpoint else 0
    prev_sig = checkpoint["signature"] if checkpoint else ""
    prev_records = int(checkpoint["records"]) if checkpoint else 0

    def _fail(msg: str, *, offset: int, size: int, sig: str) -> None:
        store.set_source_checkpoint(
            source.id, byte_offset=offset, size=size, signature=sig,
            records=prev_records, last_error=msg,
        )
        # Surface it in the admin log too, not just on the checkpoint — a watchdog
        # runs unattended, so a silent failure would go unnoticed.
        logx.warn(
            f"watchdog import failed: {source.name!r} — {msg}",
            username=source.owner, operation="import", tag=logx.TAG_DATA,
        )

    # ── validate the watchdog's destination + source type ─────────────────────
    if not (path and project_id and connection_id):
        _fail("Watchdog is missing a file path, project id or connection.",
              offset=prev_offset, size=0, sig=prev_sig)
        return
    st_id = str(cfg.get("sourceTypeId") or "").strip()
    st = next((s for s in store.list_source_types(source.owner) if s.id == st_id), None)
    if st is None:
        _fail("The source has no source type linked.", offset=prev_offset, size=0, sig=prev_sig)
        return
    fields = st.public()["fields"]
    # Authorisation: the watchdog acts AS the source's owner, so the owner must be
    # assigned to the destination connection. Checked on every poll (not just at save
    # time) so revoking the assignment stops the watchdog immediately. Without this, any
    # developer who learns a connection's id could write into it with its stored
    # credentials.
    if not store.user_can_use(connection_id, source.owner):
        _fail("The destination connection is not assigned to you.",
              offset=prev_offset, size=0, sig=prev_sig)
        return
    conn = store.get_connection(connection_id, with_secrets=True)
    if conn is None:
        _fail("The watchdog's destination connection no longer exists.",
              offset=prev_offset, size=0, sig=prev_sig)
        return
    schema = (conn.schema or "").strip()
    if not schema:
        _fail("The destination connection has no target schema.",
              offset=prev_offset, size=0, sig=prev_sig)
        return

    # ── read the newly-appended lines (rotation-aware) ────────────────────────
    try:
        res = await asyncio.to_thread(read_delta, path, encoding, prev_offset, prev_sig)
    except FileAccessError as exc:
        _fail(str(exc), offset=prev_offset, size=0, sig=prev_sig)
        return

    if not res["lines"]:
        # Nothing new — just record the current size/signature (and clear any old error).
        store.set_source_checkpoint(
            source.id, byte_offset=res["new_offset"], size=res["size"],
            signature=res["signature"], records=prev_records, last_error="",
        )
        return

    # ── extract the new lines into the stored connection ──────────────────────
    extractor = FileExtractor(
        path=path, encoding=encoding, fields=fields, project_id=project_id,
        lines=res["lines"], compound=st.public().get("compound") or [],
    )
    try:
        raw, run_sql = await asyncio.to_thread(_open_run_sql, conn)
    except Exception as exc:  # noqa: BLE001 — connect failure is recorded, not fatal
        _fail(f"Could not connect: {exc}", offset=prev_offset, size=res["size"], sig=res["signature"])
        return
    try:
        result = await layer.run(
            user=source.owner, extractor=extractor,
            backend=SqlIngestBackend(
                run_sql=run_sql, commit=raw.commit, rollback=raw.rollback,
            ),
            schema=schema,
            connection_id=connection_id, connection_name=conn.name,
            source_name=source.name, source_type_name=st.name, trigger="watchdog",
            transaction_rows=transaction_rows,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced on the checkpoint; loop continues
        _fail(f"Import failed: {exc}", offset=prev_offset, size=res["size"], sig=res["signature"])
        return
    finally:
        await asyncio.to_thread(raw.close)

    store.set_source_checkpoint(
        source.id, byte_offset=res["new_offset"], size=res["size"],
        signature=res["signature"], records=prev_records + result.records, last_error="",
    )
    logx.usage(
        f"watchdog imported {result.records} new event(s) from {source.name!r} "
        f"into {conn.name}/{schema} (project {project_id})",
        username=source.owner, operation="import", tag=logx.TAG_DATA,
    )


async def watchdog_loop() -> None:
    """The background loop. One misbehaving source never stops the others or the loop."""
    if not INTEGRATION_WATCHDOG_ENABLED:
        return
    while True:
        await asyncio.sleep(INTEGRATION_WATCHDOG_TICK_SECS)
        try:
            sources = await asyncio.to_thread(store.list_all_sources)
        except Exception as exc:  # noqa: BLE001
            logx.warn(
                f"watchdog: could not list sources: {exc}",
                operation="import", tag=logx.TAG_DATA,
            )
            continue
        for source in sources:
            try:
                await poll_source(source)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logx.error(
                    f"watchdog: source {source.name!r} poll failed: {exc}",
                    username=source.owner, operation="import", tag=logx.TAG_DATA,
                )
