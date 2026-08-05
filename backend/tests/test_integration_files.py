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
