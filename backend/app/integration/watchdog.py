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
import hashlib
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
from .files import (
    FORMAT_JSON,
    FORMAT_TEXT,
    FileAccessError,
    json_shape,
    read_delta,
    read_text_file,
)
from .layer import layer
from .structured import iter_json_from_text, iter_xml_records, parse_xml


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
    fmt = st.public().get("format") or FORMAT_TEXT
    record_path = st.public().get("recordPath") or ""
    compound = st.public().get("compound") or []
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

    # ── decide the read strategy by data format ───────────────────────────────
    # text / JSONL are line-oriented → byte-offset delta (rotation-aware). A JSON array
    # or XML document is whole-file → import-once by content signature (an unchanged file
    # imports nothing; a changed one re-imports whole).
    if fmt == FORMAT_JSON:
        try:
            shape = await asyncio.to_thread(json_shape, path)
        except FileAccessError as exc:
            _fail(str(exc), offset=prev_offset, size=0, sig=prev_sig)
            return
    else:
        shape = ""
    use_byte_delta = fmt == FORMAT_TEXT or (fmt == FORMAT_JSON and shape == "jsonl")

    if use_byte_delta:
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
        extractor = FileExtractor(
            path=path, encoding=encoding, fields=fields, project_id=project_id,
            fmt=fmt, lines=res["lines"], compound=compound,
        )
        new_offset, new_size, new_sig = res["new_offset"], res["size"], res["signature"]
    else:
        try:
            text = await asyncio.to_thread(read_text_file, path, encoding)
        except FileAccessError as exc:
            _fail(str(exc), offset=prev_offset, size=0, sig=prev_sig)
            return
        size = len(text.encode("utf-8", errors="ignore"))
        content_sig = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        if checkpoint and prev_sig == content_sig and int(checkpoint.get("size") or 0) == size:
            # Unchanged since the last import — nothing to do; just clear any old error.
            store.set_source_checkpoint(
                source.id, byte_offset=size, size=size, signature=content_sig,
                records=prev_records, last_error="",
            )
            return
        try:
            if fmt == FORMAT_JSON:
                records = list(iter_json_from_text(text))
            else:
                root = await asyncio.to_thread(parse_xml, text)
                records = iter_xml_records(root, record_path)
        except ValueError as exc:  # malformed / unsafe document
            _fail(str(exc), offset=prev_offset, size=size, sig=content_sig)
            return
        extractor = FileExtractor(
            path=path, encoding=encoding, fields=fields, project_id=project_id,
            fmt=fmt, record_path=record_path, records=records, record_total=len(records),
            compound=compound,
        )
        new_offset, new_size, new_sig = size, size, content_sig

    # ── extract into the stored connection ────────────────────────────────────
    try:
        raw, run_sql = await asyncio.to_thread(_open_run_sql, conn)
    except Exception as exc:  # noqa: BLE001 — connect failure is recorded, not fatal
        _fail(f"Could not connect: {exc}", offset=prev_offset, size=new_size, sig=new_sig)
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
        _fail(f"Import failed: {exc}", offset=prev_offset, size=new_size, sig=new_sig)
        return
    finally:
        await asyncio.to_thread(raw.close)

    # Byte-delta accumulates onto the running total; import-once replaces it (whole re-read).
    total_records = prev_records + result.records if use_byte_delta else result.records
    store.set_source_checkpoint(
        source.id, byte_offset=new_offset, size=new_size,
        signature=new_sig, records=total_records, last_error="",
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
