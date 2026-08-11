"""Safe access to the files a File source reads.

Every user-supplied file path goes through :func:`resolve_source_file` — the *only*
place that turns a path into an openable file. By default reads are sandboxed to
``INTEGRATION_FILES_DIR`` (a mounted volume in Docker); path traversal and symlink
escapes are rejected. Setting ``INTEGRATION_ALLOW_ANY_PATH`` opts a deployment into
reading any absolute path the server process can access.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.config import (
    INTEGRATION_ALLOW_ANY_PATH,
    INTEGRATION_FILES_DIR,
    PROJECT_ROOT,
)

_MAX_PREVIEW = 50
_MAX_LINE_CHARS = 2000


class FileAccessError(Exception):
    """A source file could not be accessed (missing, not a file, or outside the sandbox)."""


def resolve_source_file(path: str) -> Path:
    """Resolve a user-supplied path to a readable regular file, honouring the sandbox.

    Sandboxed (default): ``path`` is taken relative to ``INTEGRATION_FILES_DIR`` (an
    absolute path is accepted only if it already lives inside it); the real path (symlinks
    resolved) must stay within the root. Unrestricted mode accepts any absolute path.
    """
    raw = (path or "").strip()
    if not raw:
        raise FileAccessError("No file path given.")

    if INTEGRATION_ALLOW_ANY_PATH:
        candidate = Path(raw).expanduser()
        real = Path(os.path.realpath(candidate))
    else:
        root = Path(os.path.realpath(INTEGRATION_FILES_DIR))
        candidate = Path(raw)
        # Absolute paths are only allowed if they already sit under the root; otherwise
        # treat the path as relative to the root.
        base = candidate if candidate.is_absolute() else root / candidate
        real = Path(os.path.realpath(base))
        try:
            inside = os.path.commonpath([str(root), str(real)]) == str(root)
        except ValueError:  # different drives on Windows
            inside = False
        if not inside:
            raise FileAccessError(
                "That path is outside the allowed sources directory."
            )

    if not real.exists():
        raise FileAccessError("File not found.")
    if not real.is_file():
        raise FileAccessError("Not a regular file.")
    return real


# ── file listing (for the source-type wizard's file picker) ──────────────────

_MAX_LISTED_FILES = 500


def list_source_files() -> list[dict]:
    """List the readable files under ``INTEGRATION_FILES_DIR`` for the wizard's file
    picker: ``[{name, size, modified}]`` sorted by name, where ``name`` is the path
    relative to the sandbox root (so it can be handed straight back as a source path).

    Bounded to ``_MAX_LISTED_FILES`` entries; hidden files/dirs (dot-prefixed) are
    skipped. In unrestricted mode (``INTEGRATION_ALLOW_ANY_PATH``) there is no single
    root to enumerate, so this returns an empty list — the user types a path instead.
    """
    if INTEGRATION_ALLOW_ANY_PATH:
        return []
    root = Path(os.path.realpath(INTEGRATION_FILES_DIR))
    if not root.is_dir():
        return []
    out: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune hidden directories in place so os.walk doesn't descend into them.
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith("."):
                continue
            full = Path(dirpath) / fn
            try:
                if not full.is_file() or full.is_symlink():
                    continue  # symlinks could point outside the sandbox
                st = full.stat()
            except OSError:
                continue
            out.append({
                "name": str(full.relative_to(root)),
                "size": st.st_size,
                "modified": int(st.st_mtime),
            })
            if len(out) >= _MAX_LISTED_FILES:
                return sorted(out, key=lambda e: e["name"])
    return sorted(out, key=lambda e: e["name"])


# ── record-delimiter detection (wizard step 1) ───────────────────────────────

# Candidate record delimiters, in tie-break preference order. Each is (id, bytes, label).
_DELIMITERS: list[tuple[str, bytes, str]] = [
    ("crlf", b"\r\n", "CRLF (\\r\\n) — Windows line ending"),
    ("lf", b"\n", "LF (\\n) — Unix newline"),
    ("cr", b"\r", "CR (\\r) — classic Mac line ending"),
    ("ff", b"\x0c", "FF (\\f, 0x0C) — form feed"),
    ("rs", b"\x1e", "RS (0x1E) — record separator"),
    ("nul", b"\x00", "NUL (0x00) — null-delimited"),
    ("blank", b"\n\n", "Blank line — multi-line records"),
]
_DELIM_BY_ID = {d[0]: d for d in _DELIMITERS}
_MAX_DETECT_BYTES = 256 * 1024  # sample this much of the file for detection
_MAX_RECORDS = 20


def _effective_counts(chunk: bytes) -> dict[str, int]:
    """How many times each candidate delimiter actually separates records in ``chunk``.

    LF and CR counts exclude the ones that form a CRLF pair, so a Windows file reads as
    CRLF-delimited, not as both LF and CR.
    """
    crlf = chunk.count(b"\r\n")
    counts = {
        "crlf": crlf,
        "lf": chunk.count(b"\n") - crlf,
        "cr": chunk.count(b"\r") - crlf,
        "ff": chunk.count(b"\x0c"),
        "rs": chunk.count(b"\x1e"),
        "nul": chunk.count(b"\x00"),
        # Blank-line separators; only meaningful when there are real blank lines.
        "blank": chunk.count(b"\n\n"),
    }
    return counts


def _detect_delimiter(chunk: bytes) -> str:
    """Pick the most plausible record delimiter id for ``chunk``.

    Highest effective count wins; ties break by ``_DELIMITERS`` order (CRLF before LF …).
    A blank-line delimiter only wins if it clearly dominates plain newlines (multi-line
    records), otherwise every double newline would also be counted as a single LF split.
    """
    counts = _effective_counts(chunk)
    order = {d[0]: i for i, d in enumerate(_DELIMITERS)}
    ranked = sorted(
        (id_ for id_, c in counts.items() if c > 0),
        key=lambda id_: (-counts[id_], order[id_]),
    )
    if not ranked:
        return "lf"  # no separators at all → the whole file is one record
    best = ranked[0]
    # Guard the blank-line case: prefer it only when it accounts for most newlines.
    if best == "blank" and counts["lf"] and counts["blank"] * 2 < counts["lf"]:
        return "lf"
    return best


def detect_records(
    path: str, delimiter: str | None = None, limit: int = 5, encoding: str = "utf-8"
) -> dict:
    """Read a bounded head of a source file, detect (or use the given) record delimiter,
    and return the first ``limit`` records split on it.

    Returns ``{delimiter, candidates: [{id, label, count}], records, truncated,
    encoding}``. Records are stripped of surrounding whitespace, blank ones dropped, and
    each truncated to ``_MAX_LINE_CHARS``. ``candidates`` lists every delimiter seen at
    least once (plus the chosen one), so the UI can offer alternatives with their counts.
    """
    limit = max(1, min(int(limit or 5), _MAX_RECORDS))
    real = resolve_source_file(path)
    with real.open("rb") as fh:
        chunk = fh.read(_MAX_DETECT_BYTES)
        more = fh.read(1)  # is there content beyond the sampled head?
    file_truncated = bool(more)

    counts = _effective_counts(chunk)
    chosen = delimiter if (delimiter in _DELIM_BY_ID) else _detect_delimiter(chunk)

    # Candidate list: any delimiter actually present, plus the chosen one, ranked.
    order = {d[0]: i for i, d in enumerate(_DELIMITERS)}
    seen = {id_ for id_, c in counts.items() if c > 0} | {chosen}
    candidates = [
        {"id": id_, "label": _DELIM_BY_ID[id_][2], "count": counts[id_]}
        for id_ in sorted(seen, key=lambda id_: (-counts[id_], order[id_]))
    ]

    text = chunk.decode(encoding or "utf-8", errors="replace")
    sep = _DELIM_BY_ID[chosen][1].decode("latin-1")
    parts = text.split(sep)
    # If we didn't read the whole file, the final part may be a cut-off record — drop it.
    if file_truncated and parts:
        parts = parts[:-1]
    records: list[str] = []
    for p in parts:
        r = p.strip("\r\n").strip()
        if not r:
            continue
        records.append(r[:_MAX_LINE_CHARS])
        if len(records) >= limit:
            break
    more_records = file_truncated or len([p for p in parts if p.strip()]) > len(records)
    return {
        "delimiter": chosen,
        "candidates": candidates,
        "records": records,
        "truncated": more_records,
        "encoding": encoding or "utf-8",
    }


def read_preview(path: str, limit: int = 5) -> dict:
    """Return the first ``limit`` non-blank lines of a source file (each truncated),
    plus whether more lines follow. ``limit`` is clamped to 1..50."""
    limit = max(1, min(int(limit or 5), _MAX_PREVIEW))
    real = resolve_source_file(path)
    lines: list[str] = []
    truncated = False
    with real.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n\r")
            if not line.strip():
                continue
            lines.append(line[:_MAX_LINE_CHARS])
            if len(lines) >= limit:
                # Is there any further non-blank content?
                for more in fh:
                    if more.strip():
                        truncated = True
                        break
                break
    return {"lines": lines, "truncated": truncated}


def iter_lines(path: str, encoding: str = "utf-8"):
    """Stream a source file's non-blank lines (each truncated), for extraction."""
    real = resolve_source_file(path)
    enc = encoding or "utf-8"
    with real.open("r", encoding=enc, errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n\r")
            if line.strip():
                yield line[:_MAX_LINE_CHARS]


def count_lines(path: str, encoding: str = "utf-8") -> int:
    """Count the non-blank lines of a source file (the extraction's denominator for a
    progress bar). A cheap pre-pass; matches what `iter_lines` yields."""
    real = resolve_source_file(path)
    enc = encoding or "utf-8"
    n = 0
    with real.open("r", encoding=enc, errors="replace") as fh:
        for raw in fh:
            if raw.strip():
                n += 1
    return n


_SIG_BYTES = 64  # a small, fixed prefix — stable as the file grows by appends


def _signature(fh) -> str:
    """Fingerprint the file's first ``_SIG_BYTES`` bytes, so the watchdog notices when the
    file is *replaced* by different content (rotation). Uses a small FIXED prefix that
    doesn't change as the file grows by appends; returns "" for a file too short to
    fingerprint (rotation is then detected only by the size shrinking)."""
    import hashlib

    fh.seek(0)
    head = fh.read(_SIG_BYTES)
    return hashlib.md5(head).hexdigest() if len(head) >= _SIG_BYTES else ""


# Upper bound on the bytes one poll reads into memory. A larger backlog (e.g. the first
# poll of a huge existing file) is consumed over successive polls, cap by cap, instead of
# loading it all at once.
_MAX_CHUNK_BYTES = 8 * 1024 * 1024


def read_new_lines(path: str, encoding: str, offset: int) -> dict:
    """Read the file's newly-appended, *complete* lines since byte ``offset``.

    Returns ``{lines, new_offset, size, signature, rotated}``:
    * only whole lines (up to the last newline) are returned — a partial trailing line
      is left for the next poll, and ``new_offset`` stops at that boundary;
    * at most ``_MAX_CHUNK_BYTES`` are read per call — a bigger backlog is drained over
      successive calls (``new_offset`` < ``size`` signals more is pending);
    * ``rotated`` is True when the file shrank below ``offset`` (truncated/rotated), in
      which case reading restarts from 0;
    * blank lines are skipped and each line is length-capped, matching ``iter_lines``.
    """
    real = resolve_source_file(path)
    enc = encoding or "utf-8"
    with real.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        signature = _signature(fh)
        start = int(offset or 0)
        rotated = start > size  # the file shrank ⇒ it was truncated or rotated
        if rotated:
            start = 0
        if start >= size:
            return {"lines": [], "new_offset": start, "size": size,
                    "signature": signature, "rotated": rotated}
        capped = min(size - start, _MAX_CHUNK_BYTES)
        fh.seek(start)
        data = fh.read(capped)

    last_nl = data.rfind(b"\n")
    if last_nl == -1:
        if len(data) >= _MAX_CHUNK_BYTES:
            # A single "line" longer than the whole cap is not a parseable log line —
            # skip past it rather than re-reading it forever.
            return {"lines": [], "new_offset": start + len(data), "size": size,
                    "signature": signature, "rotated": rotated}
        # No complete new line yet — wait for the rest.
        return {"lines": [], "new_offset": start, "size": size,
                "signature": signature, "rotated": rotated}
    consumed = data[: last_nl + 1]
    new_offset = start + len(consumed)
    lines = [
        ln.rstrip("\r")[:_MAX_LINE_CHARS]
        for ln in consumed.decode(enc, errors="replace").split("\n")
        if ln.strip()
    ]
    return {"lines": lines, "new_offset": new_offset, "size": size,
            "signature": signature, "rotated": rotated}


def read_delta(path: str, encoding: str, offset: int, signature: str) -> dict:
    """:func:`read_new_lines` plus *replacement* detection — the read every incremental
    import does, whether triggered by the watchdog or by hand.

    A file whose head changed while its size did not shrink was replaced rather than
    appended to (rotation that reuses the name), so the stored offset points into
    unrelated content and the file must be re-read from the start. ``read_new_lines``
    only catches the shrinking case on its own.

    An empty file, or one with nothing appended since ``offset``, yields no lines and
    the current size/signature — not an error.
    """
    res = read_new_lines(path, encoding, offset)
    if not res["rotated"] and signature and res["signature"] != signature and offset > 0:
        res = read_new_lines(path, encoding, 0)
    return res


class DeltaReader:
    """Stream **every** complete line appended to a file since ``(offset, signature)``,
    draining it to EOF in ``_MAX_CHUNK_BYTES`` chunks.

    Each chunk is read with :func:`read_new_lines` (so no more than one chunk is ever
    held in memory), but unlike a single delta read this keeps going until the whole
    file is consumed — so a large *manual* import finishes in one run instead of leaving
    a backlog for the next. Rotation/replacement is handled by the first read, exactly
    like :func:`read_delta`.

    Iterate it once (e.g. hand it to the extractor). Afterwards:
      * ``end_offset`` / ``size`` / ``signature`` — the checkpoint to store,
      * ``lines_read`` — how many lines were yielded,
      * ``rotated`` — whether the file had shrunk and was re-read from the start.
    """

    def __init__(self, path: str, encoding: str, offset: int = 0, signature: str = "") -> None:
        self._path = path
        self._encoding = encoding or "utf-8"
        self._offset = int(offset or 0)
        self._signature = signature or ""
        self.end_offset = self._offset
        self.size = 0
        self.signature = self._signature
        self.rotated = False
        self.lines_read = 0

    def __iter__(self):
        # First read handles rotation/replacement (may restart from byte 0).
        res = read_delta(self._path, self._encoding, self._offset, self._signature)
        self.rotated = bool(res["rotated"])
        while True:
            for ln in res["lines"]:
                self.lines_read += 1
                yield ln
            self.end_offset = res["new_offset"]
            self.size = res["size"]
            self.signature = res["signature"]
            if res["new_offset"] >= res["size"]:
                break  # reached EOF
            nxt = read_new_lines(self._path, self._encoding, res["new_offset"])
            # No forward progress and nothing read → stop rather than spin (defensive; a
            # line longer than the whole cap already advances the offset in read_new_lines).
            if not nxt["lines"] and nxt["new_offset"] <= res["new_offset"]:
                self.end_offset = nxt["new_offset"]
                self.size = nxt["size"]
                self.signature = nxt["signature"]
                break
            res = nxt


def seed_demo_files() -> None:
    """Copy the bundled example log(s) into the sandbox dir on first use, so the demo
    works out of the box. Never overwrites an existing file. Best-effort."""
    try:
        examples = PROJECT_ROOT / "examples"
        if not examples.is_dir():
            return
        for src in examples.glob("*.log"):
            dst = INTEGRATION_FILES_DIR / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
    except Exception:  # noqa: BLE001 — seeding is a convenience, never fatal
        pass
