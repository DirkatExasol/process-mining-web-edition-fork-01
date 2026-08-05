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
