"""The /guides/ routes on a browser surface (web_surface.build_surface_app)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def surface(tmp_path, monkeypatch):
    """A minimal GUI-style surface with a temp guides dir (fresh stores in tmp)."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path / "data"))
    import app.config as config

    importlib.reload(config)
    import app.store.crypto as crypto

    importlib.reload(crypto)
    import app.services.certs as certs

    importlib.reload(certs)
    import app.store.security as security_mod

    importlib.reload(security_mod)
    import app.store.logs as logs_mod

    importlib.reload(logs_mod)
    import app.web_surface as ws

    importlib.reload(ws)

    guides = tmp_path / "docs"
    guides.mkdir()
    (guides / "My-Guide.html").write_text(
        "<!doctype html><html><head><title>My Guide</title></head><body>hi</body></html>",
        encoding="utf-8",
    )
    (guides / "build-my-guide.py").write_text("print('never served')", encoding="utf-8")
    (guides / "notes.txt").write_text("nope", encoding="utf-8")
    (guides / "The-Manual.pdf").write_bytes(b"%PDF-1.4 fake pdf bytes")
    # a numeric-prefixed, space-containing name (how guides get logical ordering)
    (guides / "01 - Intro.html").write_text(
        "<!doctype html><title>Intro</title>hi", encoding="utf-8"
    )

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")

    app = ws.build_surface_app(
        title="t",
        audience="app",
        cookie_name="pmw_test",
        dist_dir=dist,
        index_html=dist / "index.html",
        role_predicate=lambda user: True,
        guides_dir=guides,
    )
    with TestClient(app) as client:
        yield client


def test_guides_index_lists_html_then_pdf(surface):
    body = surface.get("/guides/index.json").json()
    assert body == [
        {"file": "01 - Intro.html", "title": "Intro", "type": "html"},
        {"file": "My-Guide.html", "title": "My Guide", "type": "html"},
        {"file": "The-Manual.pdf", "title": "The Manual", "type": "pdf"},
    ]


def test_numeric_prefixed_name_with_spaces_is_served(surface):
    r = surface.get("/guides/01 - Intro.html")
    assert r.status_code == 200 and "Intro" in r.text


def test_pdf_is_served_with_pdf_media_type(surface):
    r = surface.get("/guides/The-Manual.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")


def test_guide_is_served_without_auth(surface):
    r = surface.get("/guides/My-Guide.html")
    assert r.status_code == 200
    assert "My Guide" in r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_guides_responses_set_nosniff(surface):
    assert surface.get("/guides/index.json").headers["x-content-type-options"] == "nosniff"
    assert surface.get("/guides/The-Manual.pdf").headers["x-content-type-options"] == "nosniff"


def test_only_html_files_are_served(surface):
    assert surface.get("/guides/build-my-guide.py").status_code == 404
    assert surface.get("/guides/notes.txt").status_code == 404
    assert surface.get("/guides/missing.html").status_code == 404


def test_traversal_names_are_rejected(surface):
    # A dot-leading name matches the route but fails the whitelist → 404.
    assert surface.get("/guides/.hidden.html").status_code == 404
    # Encoded slash / dot-dot paths never even reach the guide route: they resolve to
    # non-/guides paths and fall through to the SPA catch-all, which serves the SPA
    # shell — never a file from the guides directory (or anywhere else).
    for url in ("/guides/..%2Fsecret.key", "/guides/%2e%2e/config.py"):
        r = surface.get(url)
        assert r.status_code == 200 and r.text == "<html>spa</html>"
