"""Concrete extractors that plug into the abstraction layer.

``FileExtractor`` is the first one: it reads a File source line by line, applies the
linked source type's regexes to each line, and pushes the parsed events into the
target schema's ``JOURNEYS`` table (normalising the timestamp), through the
:class:`~.contract.IngestSession` it is handed.
"""

from __future__ import annotations

import hashlib
import re
import zlib
from datetime import datetime

# User-authored regexes are applied to every line, so a catastrophic-backtracking
# pattern must not be able to hang the process. The `regex` module supports a wall-clock
# timeout per match; fall back to stdlib `re` (no timeout available) if it is missing.
try:  # pragma: no cover - exercised by whichever branch the environment provides
    import regex as _rx

    _MATCH_TIMEOUT_SECS = 0.25
    _MATCH_KW = {"timeout": _MATCH_TIMEOUT_SECS}
except ImportError:  # pragma: no cover
    _rx = re
    _MATCH_KW = {}

from .compound import CompoundRules
from .contract import ColumnType, ExtractResult, ExtractorInfo, IngestError, IngestSession
from .files import count_lines, iter_lines
from .parsing import TIMESTAMP_TARGET, analyze_timestamp

# The columns we populate (see backend/app/db/schema_ddl.py).
_JOURNEYS_COLUMNS = {
    "PROJECT_ID": ColumnType.STRING,
    "EVENT_ID": ColumnType.STRING,
    "STEP": ColumnType.STRING,
    "STEP_ID": ColumnType.INT,
    "EVENT_TIME": ColumnType.TIMESTAMP,
    "META_1": ColumnType.STRING,
    "META_2": ColumnType.STRING,
    "META_3": ColumnType.STRING,
    "SAMPLE_SET": ColumnType.STRING,
}
_PROJECTS_COLUMNS = {
    "PROJECT_ID": ColumnType.STRING,
    "TITLE": ColumnType.STRING,
    "DESCRIPTION": ColumnType.STRING,
}
_STEPS_COLUMNS = {
    "PROJECT_ID": ColumnType.STRING,
    "STEP": ColumnType.STRING,
    "DESCRIPTION": ColumnType.STRING,
    "BG_COLOR": ColumnType.STRING,
    "FG_COLOR": ColumnType.STRING,
    "SCORE": ColumnType.DECIMAL,
    "SHAPE": ColumnType.STRING,
    "END_OF_PROCESS": ColumnType.BOOL,
    "BELONGS_TO": ColumnType.STRING,
}
_METAS_COLUMNS = {
    "PROJECT_ID": ColumnType.STRING,
    "META_1_TITLE": ColumnType.STRING,
    "META_2_TITLE": ColumnType.STRING,
    "META_3_TITLE": ColumnType.STRING,
}
_BATCH = 500

# Auto-created steps get a colour + a shape picked deterministically per step name
# (from the shapes the mining app predefines — see StepEditor SHAPES), a white
# foreground and a zero score (so they show but don't skew scoring).
_STEP_PALETTE = [
    "#4a90d9", "#7ed321", "#f5a623", "#bd10e0", "#50e3c2",
    "#e0245e", "#9013fe", "#417505", "#d0021b", "#8b572a",
]
_STEP_SHAPES = ["stadium", "round", "hex", "circle"]


def _step_color(step: str) -> str:
    # crc32 gives a stable, well-distributed index (unlike hash(), which is salted).
    return _STEP_PALETTE[zlib.crc32(step.encode("utf-8")) % len(_STEP_PALETTE)]


def _step_shape(step: str) -> str:
    # Offset the seed so shape and colour don't correlate.
    return _STEP_SHAPES[zlib.crc32(b"shape:" + step.encode("utf-8")) % len(_STEP_SHAPES)]


def _md5(value: str) -> str:
    """Hex MD5 digest — used to pseudonymise EVENT_ID before it's written to JOURNEYS."""
    return hashlib.md5(value.encode("utf-8")).hexdigest()

# The extractor id used both for the registry entry and per-run instances.
FILE_EXTRACTOR_ID = "file"


def file_extractor_info() -> ExtractorInfo:
    return ExtractorInfo(
        id=FILE_EXTRACTOR_ID,
        name="File",
        version="1.0",
        description="Reads a File source line by line and writes JOURNEYS events using "
        "the linked source type's regexes.",
    )


class FileExtractor:
    """A configured run over one File source. ``fields`` is the source type's extraction
    spec (a list of ``{name, role, regex}``); ``project_id`` fills JOURNEYS.PROJECT_ID."""

    info = file_extractor_info()

    def __init__(
        self,
        *,
        path: str,
        encoding: str,
        fields: list[dict],
        project_id: str,
        lines: list[str] | None = None,
        line_stream=None,
        line_total: int | None = None,
        compound: list[dict] | None = None,
    ) -> None:
        self._path = path
        self._encoding = encoding or "utf-8"
        self._project_id = project_id
        # Incremental (watchdog) mode: when ``lines`` is given, those exact lines are
        # extracted instead of reading the whole file — the caller has already read only
        # the newly-appended lines from the file's checkpoint offset.
        self._lines = lines
        # Streaming delta mode (manual run): an iterable that yields all appended lines,
        # draining the file to EOF in bounded chunks (see files.DeltaReader). Kept
        # separate from ``lines`` so its length is never taken (it is a generator).
        self._line_stream = line_stream
        self._line_total = line_total
        # Compile the regexes once, split by role. Only the first field of each single
        # role is used; up to three meta fields map to META_1..3.
        self._ts = self._compiled(fields, "timestamp")
        self._id = self._compiled(fields, "id")
        self._step = self._compiled(fields, "step")
        meta_fields = [f for f in fields if f.get("role") == "meta"][:3]
        self._metas = [self._compile(f["regex"]) for f in meta_fields]
        # Business names for META_1..3 — only the explicitly-given titles (a METAS row
        # is written only when at least one is set).
        self._meta_titles = [(f.get("title") or "").strip() for f in meta_fields]
        # Compound steps (optional): rules that derive the final STEP from several field
        # values. Every named field — including "aux" helper fields that are extracted
        # but written to no column — is available to them, so compile them all by name.
        self._compound = CompoundRules(compound)
        self._named = (
            [
                (str(f.get("name") or "").strip(), self._compile(f.get("regex", "")))
                for f in fields
                if str(f.get("name") or "").strip()
            ]
            if self._compound
            else []
        )
        self._seen_steps: set[str] = set()

    @staticmethod
    def _compile(pattern: str):
        try:
            return _rx.compile(pattern)
        except Exception:  # noqa: BLE001 — any bad pattern simply yields no matches
            return None

    def _compiled(self, fields: list[dict], role: str):
        for f in fields:
            if f.get("role") == role:
                return self._compile(f.get("regex", ""))
        return None

    @staticmethod
    def _capture(rx, line: str) -> str | None:
        if rx is None:
            return None
        try:
            m = rx.search(line, **_MATCH_KW)
        except TimeoutError:
            # Catastrophic backtracking on this line. The regexes come from the user's
            # source type and run against every line of the log (and inside the
            # watchdog's background loop) — and CPython's `re` does NOT release the GIL,
            # so an unbounded match would freeze the whole backend process, not just
            # this worker. Skip the line instead; it is counted as unparseable.
            return None
        if not m:
            return None
        return m.group(1) if m.groups() else m.group(0)

    def run(self, session: IngestSession) -> ExtractResult:
        session.define_table("JOURNEYS", _JOURNEYS_COLUMNS, keys=["PROJECT_ID", "EVENT_ID", "STEP"])
        session.define_table("PROJECTS", _PROJECTS_COLUMNS, keys=["PROJECT_ID"])
        session.define_table("STEPS", _STEPS_COLUMNS, keys=["PROJECT_ID", "STEP"])

        # Three read modes: a streaming delta drain (manual run), the exact lines the
        # watchdog handed us, or a whole-file read.
        if self._line_stream is not None:
            source = self._line_stream
            total = self._line_total or 0  # unknown up front → indeterminate progress
            session.log(
                f"reading appended lines from {self._path} → "
                f"{session.schema}.JOURNEYS (project {self._project_id})"
            )
        elif self._lines is not None:
            source = self._lines
            total = len(self._lines)
            session.log(
                f"watchdog: {total} new line(s) from {self._path} → "
                f"{session.schema}.JOURNEYS (project {self._project_id})"
            )
        else:
            source = iter_lines(self._path, self._encoding)
            total = count_lines(self._path, self._encoding)
            session.log(f"reading {self._path} → {session.schema}.JOURNEYS (project {self._project_id})")
        session.progress(0, total)

        batch: list[dict] = []
        written = 0
        skipped = 0
        processed = 0
        for line in source:
            processed += 1
            row = self._row(line)
            if row is None:
                skipped += 1
            else:
                batch.append(row)
                if len(batch) >= _BATCH:
                    written += session.push("JOURNEYS", batch)
                    batch = []
            if processed % 200 == 0:
                session.progress(processed)
        if batch:
            written += session.push("JOURNEYS", batch)
        session.progress(processed)

        session.log(f"pushed {written} events, skipped {skipped} unparseable line(s)")
        # Make sure the project + its meta titles exist and every step seen is defined.
        project_created = self._ensure_project(session)
        self._ensure_metas(session)
        steps_created = self._ensure_steps(session)

        detail = f"{written} events written, {skipped} skipped"
        if steps_created:
            detail += f", {steps_created} new step(s)"
        if project_created:
            detail += ", project created"
        return ExtractResult(
            records=written, skipped=skipped,
            tables=("JOURNEYS", "PROJECTS", "STEPS", "METAS"), detail=detail,
        )

    def _ensure_project(self, session: IngestSession) -> bool:
        """Create the PROJECTS row for this run's project id if it isn't there yet."""
        if (self._project_id,) in session.existing_keys("PROJECTS", ["PROJECT_ID"]):
            return False
        session.push("PROJECTS", [{
            "PROJECT_ID": self._project_id, "TITLE": self._project_id, "DESCRIPTION": "",
        }])
        session.log(f"created project {self._project_id!r}")
        return True

    def _ensure_metas(self, session: IngestSession) -> bool:
        """Create the METAS row (the META_1..3 business names) for this project if it
        isn't there yet. Skipped when no meta business names are configured."""
        titles = (self._meta_titles + ["", "", ""])[:3]
        if not any(titles):
            return False
        session.define_table("METAS", _METAS_COLUMNS, keys=["PROJECT_ID"])
        if (self._project_id,) in session.existing_keys("METAS", ["PROJECT_ID"]):
            return False
        session.push("METAS", [{
            "PROJECT_ID": self._project_id,
            "META_1_TITLE": titles[0], "META_2_TITLE": titles[1], "META_3_TITLE": titles[2],
        }])
        session.log(f"created meta titles: {', '.join(t for t in titles if t)}")
        return True

    def _ensure_steps(self, session: IngestSession) -> int:
        """Create a STEPS definition (shape + colour, zero score) for every step seen
        that doesn't already exist for this project. Returns how many were created."""
        existing = session.existing_keys("STEPS", ["PROJECT_ID", "STEP"])
        new = [s for s in sorted(self._seen_steps) if (self._project_id, s) not in existing]
        if not new:
            return 0
        session.push("STEPS", [{
            "PROJECT_ID": self._project_id, "STEP": s, "DESCRIPTION": "",
            "BG_COLOR": _step_color(s), "FG_COLOR": "#ffffff", "SCORE": 0,
            "SHAPE": _step_shape(s), "END_OF_PROCESS": False, "BELONGS_TO": None,
        } for s in new])
        session.log(f"created {len(new)} new step(s): {', '.join(new)}")
        return len(new)

    def _row(self, line: str) -> dict | None:
        event_id = self._capture(self._id, line)
        step = self._capture(self._step, line)
        ts_raw = self._capture(self._ts, line)
        # A journey event needs at least a case id, a step and a time.
        if not (event_id and step and ts_raw):
            return None
        event_time = self._to_datetime(ts_raw)
        if event_time is None:
            return None
        # Compound steps: when rules are configured, the final STEP may be derived from
        # several fields at once (e.g. step "login" + status "200" → "login successful").
        # The plain step value stands whenever no rule matches, so rules are additive.
        if self._compound:
            values = {name: v for name, rx in self._named if (v := self._capture(rx, line)) is not None}
            step = self._compound.derive(values) or step
        self._seen_steps.add(step)
        metas = [self._capture(rx, line) for rx in self._metas]
        metas += [None] * (3 - len(metas))
        return {
            "PROJECT_ID": self._project_id,
            # EVENT_ID is pseudonymised: the raw case id (which may be a login/user id)
            # is never written in the clear — only its MD5 digest lands in JOURNEYS.
            "EVENT_ID": _md5(event_id),
            "STEP": step,
            "STEP_ID": None,
            "EVENT_TIME": event_time,
            "META_1": metas[0],
            "META_2": metas[1],
            "META_3": metas[2],
            "SAMPLE_SET": "ORIGINAL",
        }

    @staticmethod
    def _to_datetime(value: str) -> datetime | None:
        normalized = analyze_timestamp(value).get("normalized")
        if not normalized:
            return None
        try:
            return datetime.strptime(normalized, TIMESTAMP_TARGET)
        except ValueError:
            return None


class _FileExtractorDescriptor:
    """Registry-only entry so ``/extractors`` lists the File extractor. Actual runs use a
    per-run configured :class:`FileExtractor`, not this stub."""

    info = file_extractor_info()

    def run(self, session: IngestSession) -> ExtractResult:  # noqa: ARG002
        raise IngestError("The File extractor is run per source, not from the registry.")


def register_builtin_extractors(layer) -> None:
    """Register the built-in extractor descriptors on ``layer`` (idempotent)."""
    if layer.get(FILE_EXTRACTOR_ID) is None:
        layer.register(_FileExtractorDescriptor())
