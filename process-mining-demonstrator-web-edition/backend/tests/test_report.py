"""AI report engine (services/report.py) + report-config store (security.py)."""

from __future__ import annotations

import importlib

import pytest

from app.services import report as R


@pytest.fixture
def security(tmp_path, monkeypatch):
    """A fresh security store bound to a throwaway data dir (mirrors test_security.py)."""
    monkeypatch.setenv("PMW_DATA_DIR", str(tmp_path))
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
    return security_mod


def test_md_to_html_basic_blocks():
    html = R.md_to_html(
        "## Heading\n\nA **bold** and *em* and `code`.\n\n- one\n- two\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |"
    )
    assert "<h3>Heading</h3>" in html  # never emits <h1>
    assert "<strong>bold</strong>" in html and "<em>em</em>" in html and "<code>code</code>" in html
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<table>" in html and "<th>A</th>" in html and "<td>2</td>" in html


def test_md_inline_escapes_before_formatting():
    # A raw < is escaped; ** still becomes bold around escaped content.
    assert R.md_inline("**<b>x**") == "<strong>&lt;b&gt;x</strong>"


def test_parse_findings_tolerates_fence_and_prose():
    raw = 'Sure:\n```json\n{"title":"T","sections":[]}\n```\nthanks'
    f = R.parse_findings(raw)
    assert f and f["title"] == "T"
    # balanced-brace extraction without a fence
    f2 = R.parse_findings('prefix {"a": {"b": 1}} suffix')
    assert f2 == {"a": {"b": 1}}
    assert R.parse_findings("no json here") is None


def test_build_analysis_prompt_contains_only_the_table():
    p = R.build_analysis_prompt("Proj", "Find outliers", "| From | To | Count |")
    assert "Find outliers" in p
    assert "Transition table" in p and "| From | To | Count |" in p
    assert "JSON" in p  # asks for structured output


def test_findings_parts_splits_cover_and_sections():
    findings = {
        "title": "Airport Departure",
        "subtitle": "Outlier analysis",
        "executive_summary": ["**Volumes** reconcile", "Timings look synthetic"],
        "sections": [
            {"heading": "Finding", "body": "The **avg** equals the midpoint.",
             "table": {"columns": ["Stage", "Δ"], "rows": [["Security", "+0.4"]], "note": "n=47"}},
        ],
    }
    title, subtitle, exec_html, sections_html = R.findings_parts(findings)
    assert title == "Airport Departure" and subtitle == "Outlier analysis"
    assert "Executive summary" in exec_html and "<strong>Volumes</strong>" in exec_html
    assert "n=47" in sections_html and "<strong>avg</strong>" in sections_html


def test_render_report_assembles_toc_chapters_and_sanitises():
    svg = R.sanitize_svg("<svg viewBox='0 0 10 10'><script>alert(1)</script><rect/></svg>")
    html = R.render_report(
        meta={"user": "Dirk", "source": "transition table", "generatedAt": "12 Aug 2026"},
        style={"accent": "#4a3aa7", "orgName": "ACME"},
        title="Airport Departure",
        subtitle="Outlier analysis",
        exec_summary_html="<h2>Executive summary</h2><ul><li>Volumes reconcile</li></ul>",
        chapters=[
            {"id": "flow", "title": "Process flow", "html": f'<div class="diagram">{svg}</div>'},
            {"id": "happy", "title": "Happy Path Conformance",
             "html": R.md_to_html("| Path | Score |\n|---|---|\n| Ideal | 0.82 |")},
        ],
    )
    assert html.startswith("<!doctype html>")
    assert "Airport Departure" in html and "Outlier analysis" in html
    assert "Prepared for Dirk" in html and "ACME" in html
    assert "Executive summary" in html
    # Clickable TOC links to each chapter, and chapters carry the matching ids.
    assert '<nav class="toc"' in html and 'href="#flow"' in html and 'href="#happy"' in html
    assert 'id="flow"' in html and 'id="happy"' in html
    assert 'class="chapter-title"' in html and "Happy Path Conformance" in html
    assert "--accent:#4a3aa7" in html
    # The SVG is embedded but its injected <script> is stripped, and the report itself
    # carries NO script at all (it renders in a non-script-enabled iframe).
    assert "<svg" in html and "alert(1)" not in html
    assert "<script" not in html


def test_render_report_places_logo_on_configured_side():
    logo = "data:image/png;base64,AAAA"
    common = dict(
        meta={"user": "Dirk", "generatedAt": "13 Aug 2026"},
        title="T",
        chapters=[{"id": "a", "title": "A", "html": "<p>x</p>"}],
    )
    left = R.render_report(style={"logo": logo, "logoPos": "left", "orgName": "ACME"}, **common)
    right = R.render_report(style={"logo": logo, "logoPos": "right", "orgName": "ACME"}, **common)
    # A logo AND an organisation name both appear: the logo on its side, the letterhead
    # text on the other. For left, the logo precedes the org; for right, it follows it.
    for h in (left, right):
        assert '<img class="logo"' in h and "ACME" in h
    rhead_left = left.split("<h1>")[0]
    rhead_right = right.split("<h1>")[0]
    assert rhead_left.index("<img") < rhead_left.index("ACME")
    assert rhead_right.index("ACME") < rhead_right.index("<img")


def test_render_report_scales_logo_keeping_aspect():
    logo = "data:image/png;base64,AAAA"
    base = R.render_report(meta={"user": "D"}, title="T", style={"logo": logo},
                           chapters=[{"id": "a", "title": "A", "html": "<p>x</p>"}])
    big = R.render_report(meta={"user": "D"}, title="T", style={"logo": logo, "logoScale": 2},
                          chapters=[{"id": "a", "title": "A", "html": "<p>x</p>"}])
    # Base box is 48×190; scale multiplies both bounds together (aspect ratio preserved).
    assert "max-height:48px;max-width:190px" in base
    assert "max-height:96px;max-width:380px" in big


def test_render_report_shows_org_without_a_logo():
    html = R.render_report(
        meta={"user": "Dirk"}, title="T", style={"orgName": "ACME Airports"},
        chapters=[{"id": "a", "title": "A", "html": "<p>x</p>"}],
    )
    assert '<div class="org">ACME Airports</div>' in html


def test_render_report_is_script_free():
    # The report is a STATIC document — it must contain no <script> (it renders in a
    # same-origin iframe that is NOT granted allow-scripts; the host wires TOC scrolling).
    html = R.render_report(
        meta={"user": "Dirk"}, title="T", style={},
        chapters=[{"id": "notes", "title": "Notes", "html": "<p>x</p>"}],
    )
    assert "<script" not in html


def test_svg_img_neutralises_svg_and_embeds_as_data_uri():
    # An attacker-controlled SVG with a script and a slash-separated on-handler → embedded as
    # an <img> data URI (which can't execute), and the sanitiser also strips both vectors.
    import base64

    hostile = "<svg onload=alert(1)><script>steal()</script><rect/></svg>"
    out = R.svg_img(hostile)
    assert out.startswith('<img class="diagram-svg"') and "data:image/svg+xml;base64," in out
    decoded = base64.b64decode(out.split("base64,")[1].split('"')[0]).decode()
    assert "script" not in decoded.lower() and "onload" not in decoded.lower()
    # The slash-separator trick is also handled.
    slash = R.sanitize_svg("<svg/onload=alert(1)><rect/></svg>")
    assert "onload" not in slash.lower()
    assert R.svg_img("not an svg") == ""


def test_md_to_html_escapes_raw_html_unless_trusted():
    # LLM output (default) → the raw tags are ESCAPED (never real elements), so the injected
    # <img onerror> can't fire; the text is inert.
    escaped = R.md_to_html('<table><tr><td><img src=x onerror=alert(1)></td></tr></table>')
    assert "<table" not in escaped and "<img" not in escaped
    assert "&lt;table&gt;" in escaped
    # Trusted server-built tables opt in and pass through.
    trusted = R.md_to_html("<table><tr><td>ok</td></tr></table>", allow_raw_html=True)
    assert "<table><tr><td>ok</td></tr></table>" in trusted


def test_render_report_falls_back_on_a_non_hex_accent():
    # A tampered/legacy non-#rrggbb accent must never reach the CSS raw (it could close the
    # <style> block); render_report falls back to the default.
    html = R.render_report(
        meta={"user": "D"}, title="T",
        style={"accent": "#000</style><script>alert(1)</script>"},
        chapters=[{"id": "a", "title": "A", "html": "<p>x</p>"}],
    )
    assert "</style><script>" not in html and "alert(1)" not in html
    assert "--accent:#4a3aa7" in html


def test_report_llm_config_roundtrip(security):
    store = security.store
    store.set_report_config(
        llm_url="https://api.openai.com/v1", llm_model="gpt-4o", llm_key="secret"
    )
    cfg = store.report_config(with_secret=True)
    assert cfg["llmUrl"].endswith("/v1") and cfg["llmModel"] == "gpt-4o"
    assert cfg["hasLlmKey"] is True and cfg["llmKey"] == "secret"
    # The admin channel must never leak the key, and the LLM config carries no style.
    public = store.report_config()
    assert "llmKey" not in public and "accent" not in public
    # A None key keeps the stored one.
    store.set_report_config(llm_url="https://api.openai.com/v1", llm_model="gpt-4o")
    assert store.report_config(with_secret=True)["llmKey"] == "secret"


def test_report_style_is_per_connection_and_project(security):
    store = security.store
    logo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42m" + "A" * 8 + "="
    # A project with no style yet has none — the caller applies the built-in default.
    assert store.report_style_for("conn-a", "APF") is None

    store.set_report_style(
        "conn-a", "APF", accent="#123456", org_name="ACME Air", logo=logo,
        logo_pos="right", logo_scale=1.5, include_happy_path=False,
    )
    store.set_report_style("conn-b", "APF", accent="#00ff00")  # same project id, other conn

    a = store.report_style_for("conn-a", "APF")
    assert a["accent"] == "#123456" and a["orgName"] == "ACME Air"
    assert a["logo"] == logo and a["logoPos"] == "right" and a["includeHappyPath"] is False
    assert a["logoScale"] == 1.5
    # logoScale is clamped to [0.5, 2.0] and defaults to 1.0.
    assert store.report_style_for("conn-b", "APF")["logoScale"] == 1.0
    store.set_report_style("conn-a", "APF", logo_scale=9)
    assert store.report_style_for("conn-a", "APF")["logoScale"] == 2.0
    # Keyed by BOTH connection and project — the other connection is independent.
    b = store.report_style_for("conn-b", "APF")
    assert b["accent"] == "#00ff00" and b["logo"] == "" and b["includeHappyPath"] is True

    # The list view omits the heavy logo payload but flags it.
    rows = {(r["connectionId"], r["projectId"]): r for r in store.report_styles()}
    assert rows[("conn-a", "APF")]["hasLogo"] is True and "logo" not in rows[("conn-a", "APF")]
    assert rows[("conn-b", "APF")]["hasLogo"] is False

    # A None logo on re-save keeps that project's stored logo.
    store.set_report_style("conn-a", "APF", accent="#111111", logo=None)
    assert store.report_style_for("conn-a", "APF")["logo"] == logo

    # Delete reverts a project to the default (None).
    store.delete_report_style("conn-a", "APF")
    assert store.report_style_for("conn-a", "APF") is None
    assert store.report_style_for("conn-b", "APF") is not None  # unaffected

    with pytest.raises(ValueError):
        store.set_report_style("conn-a", "APF", accent="not-a-hex")
    with pytest.raises(ValueError):
        store.set_report_style("", "APF")  # connection + project required


def test_report_prompts_roundtrip(security):
    store = security.store
    store.set_report_prompt("c1", "p1", "Analyse the airport flow")
    store.set_report_prompt("c1", "p2", "Different prompt")
    assert store.report_prompt_for("c1", "p1") == "Analyse the airport flow"
    assert store.report_prompt_for("c1", "nope") is None
    # Empty prompt removes the mapping.
    store.set_report_prompt("c1", "p1", "")
    assert store.report_prompt_for("c1", "p1") is None
    assert len(store.report_prompts()) == 1
