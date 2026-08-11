"""Sandboxed file access for File sources: the resolver rejects escapes, the preview
returns the first N lines."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_INTEGRATION_FILES_DIR", str(tmp_path / "files"))
    monkeypatch.delenv("PMW_INTEGRATION_ALLOW_ANY_PATH", raising=False)
    import app.config as config

    importlib.reload(config)
    import app.integration.files as files_mod

    importlib.reload(files_mod)
    return files_mod, config


def test_reads_a_file_inside_the_sandbox(files):
    files_mod, config = files
    (config.INTEGRATION_FILES_DIR / "app.log").write_text("l1\nl2\n\nl3\nl4\nl5\nl6\n")
    out = files_mod.read_preview("app.log", 3)
    assert out["lines"] == ["l1", "l2", "l3"]  # blank lines skipped
    assert out["truncated"] is True
    # Streaming iter_lines yields all non-blank lines.
    assert list(files_mod.iter_lines("app.log")) == ["l1", "l2", "l3", "l4", "l5", "l6"]


def test_read_new_lines_is_incremental_and_handles_partial_and_rotation(files):
    files_mod, config = files
    f = config.INTEGRATION_FILES_DIR / "grow.log"
    f.write_text("a\nb\n")

    # First read: both complete lines, offset stops at the last newline.
    r1 = files_mod.read_new_lines("grow.log", "utf-8", 0)
    assert r1["lines"] == ["a", "b"]
    assert r1["new_offset"] == 4 and r1["rotated"] is False

    # Append a complete line + a partial (no trailing newline): only the complete one
    # is returned, the partial waits and the offset stops before it.
    with f.open("a") as fh:
        fh.write("c\npartial")
    r2 = files_mod.read_new_lines("grow.log", "utf-8", r1["new_offset"])
    assert r2["lines"] == ["c"]
    assert r2["new_offset"] == 6  # "a\nb\nc\n"

    # Finish the partial line: it's now picked up from the same offset.
    with f.open("a") as fh:
        fh.write("-done\n")
    r3 = files_mod.read_new_lines("grow.log", "utf-8", r2["new_offset"])
    assert r3["lines"] == ["partial-done"]

    # Truncation/rotation: the file shrank below the offset → re-read from the start.
    f.write_text("fresh\n")
    r4 = files_mod.read_new_lines("grow.log", "utf-8", r3["new_offset"])
    assert r4["rotated"] is True and r4["lines"] == ["fresh"]


def test_read_new_lines_caps_the_chunk_per_call(files, monkeypatch):
    """A large backlog is drained cap-by-cap instead of being read into memory at once;
    each call stops at the last complete line inside the cap."""
    files_mod, config = files
    monkeypatch.setattr(files_mod, "_MAX_CHUNK_BYTES", 8)
    f = config.INTEGRATION_FILES_DIR / "big.log"
    f.write_text("aa\nbb\ncc\ndd\n")  # 12 bytes, 4 lines

    r1 = files_mod.read_new_lines("big.log", "utf-8", 0)
    assert r1["lines"] == ["aa", "bb"]  # 8-byte cap → "aa\nbb\ncc" cut at last newline
    assert r1["new_offset"] == 6
    r2 = files_mod.read_new_lines("big.log", "utf-8", r1["new_offset"])
    assert r2["lines"] == ["cc", "dd"]
    assert r2["new_offset"] == 12

    # A single "line" longer than the cap is skipped, not re-read forever.
    f.write_text("x" * 20)  # no newline at all
    r3 = files_mod.read_new_lines("big.log", "utf-8", 0)
    assert r3["lines"] == [] and r3["new_offset"] == 8  # advanced past the chunk


def test_rejects_paths_outside_the_sandbox(files):
    files_mod, _ = files
    for bad in ["../../etc/passwd", "/etc/passwd", "../secret", "sub/../../escape"]:
        with pytest.raises(files_mod.FileAccessError):
            files_mod.resolve_source_file(bad)


def test_rejects_a_symlink_escaping_the_sandbox(files, tmp_path):
    files_mod, config = files
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = config.INTEGRATION_FILES_DIR / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(files_mod.FileAccessError):
        files_mod.resolve_source_file("link.txt")


def test_missing_file_raises(files):
    files_mod, _ = files
    with pytest.raises(files_mod.FileAccessError):
        files_mod.read_preview("nope.log")


def test_allow_any_path_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("PMW_INTEGRATION_FILES_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("PMW_INTEGRATION_ALLOW_ANY_PATH", "1")
    import app.config as config

    importlib.reload(config)
    import app.integration.files as files_mod

    importlib.reload(files_mod)
    outside = tmp_path / "anywhere.log"
    outside.write_text("x\n")
    # With the opt-in, an absolute path outside the sandbox resolves.
    assert files_mod.resolve_source_file(str(outside)).read_text() == "x\n"
    # Restore the default for other tests.
    monkeypatch.delenv("PMW_INTEGRATION_ALLOW_ANY_PATH", raising=False)
    importlib.reload(config)
    importlib.reload(files_mod)


# ── file listing + record-delimiter detection (source-type wizard) ────────────


def test_list_source_files_enumerates_the_sandbox(files):
    files_mod, config = files
    (config.INTEGRATION_FILES_DIR / "a.log").write_text("x\n")
    (config.INTEGRATION_FILES_DIR / ".hidden.log").write_text("secret\n")  # skipped
    sub = config.INTEGRATION_FILES_DIR / "sub"
    sub.mkdir()
    (sub / "b.log").write_text("y\ny\n")

    listed = files_mod.list_source_files()
    names = [e["name"] for e in listed]
    assert "a.log" in names
    assert "sub/b.log" in names  # nested, path relative to the root
    assert ".hidden.log" not in names  # dot-files skipped
    entry = next(e for e in listed if e["name"] == "a.log")
    assert entry["size"] == 2 and isinstance(entry["modified"], int)


def test_detects_crlf_over_lf(files):
    files_mod, config = files
    (config.INTEGRATION_FILES_DIR / "win.log").write_text("one\r\ntwo\r\nthree\r\n")
    out = files_mod.detect_records("win.log")
    assert out["delimiter"] == "crlf"  # not "lf", though every CRLF contains an LF
    assert out["records"][:3] == ["one", "two", "three"]


def test_detects_form_feed_and_returns_five(files):
    files_mod, config = files
    (config.INTEGRATION_FILES_DIR / "ff.log").write_text(
        "\x0c".join(f"page{i}" for i in range(1, 9))
    )
    out = files_mod.detect_records("ff.log", limit=5)
    assert out["delimiter"] == "ff"
    assert out["records"] == ["page1", "page2", "page3", "page4", "page5"]
    assert out["truncated"] is True  # more than five records exist
    assert "ff" in {c["id"] for c in out["candidates"]}


def test_explicit_delimiter_overrides_detection(files):
    files_mod, config = files
    # An LF file, but ask for CR — should split on CR (one record, the whole thing).
    (config.INTEGRATION_FILES_DIR / "u.log").write_text("a\nb\nc\n")
    out = files_mod.detect_records("u.log", delimiter="cr")
    assert out["delimiter"] == "cr"
    assert out["records"] == ["a\nb\nc"]  # no CR present → single record (LF kept inside)


def test_blank_line_delimiter_for_multiline_records(files):
    files_mod, config = files
    (config.INTEGRATION_FILES_DIR / "multi.log").write_text(
        "line1\nline2\n\nlineA\nlineB\n\nlineX\nlineY\n"
    )
    out = files_mod.detect_records("multi.log", delimiter="blank")
    assert out["delimiter"] == "blank"
    assert out["records"][0] == "line1\nline2"
    assert out["records"][1] == "lineA\nlineB"


def test_detect_records_rejects_escape(files):
    files_mod, _ = files
    with pytest.raises(files_mod.FileAccessError):
        files_mod.detect_records("../../etc/passwd")
