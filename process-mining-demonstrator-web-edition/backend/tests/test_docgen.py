"""AI-documentation builder tests — the locally-rendered report sections and the
LLM prompt assembly (no network, no DB)."""

from __future__ import annotations

from datetime import datetime

from app.models import (
    FilterSnapshot,
    HappyPath,
    JourneyPath,
    NoteTarget,
    ProcessGraph,
    ProcessNote,
    TransitionMetric,
)
from app.services import docgen

from .conftest import edge, step


def _note(*, title, importance, resolved=False, is_node=True, day=1) -> ProcessNote:
    target = NoteTarget(type="node", value="A") if is_node else NoteTarget(
        type="edge", **{"from": "A"}, to="B"
    )
    return ProcessNote(
        title=title,
        text="body of " + title,
        importance=importance,
        resolved=resolved,
        target=target,
        createdAt=datetime(2026, 8, day),
        filterSnapshot=FilterSnapshot(
            fromDate=datetime(2026, 1, 1), toDate=datetime(2026, 12, 31)
        ),
        authorName="Dirk",
    )


def _graph() -> ProcessGraph:
    steps = {n: step(n) for n in "ABC"}
    return ProcessGraph(
        steps=steps,
        transitions=[edge("A", "B", count=10), edge("B", "C", count=4)],
    )


def test_transitions_table_lists_edges_and_summary():
    table = docgen.transitions_table(_graph())
    assert "| A | B | 10 |" in table
    assert "| B | C | 4 |" in table
    assert "**Transitions:** 2" in table
    assert "**Total:** 14" in table
    assert "**Max:** 10" in table


def test_journey_paths_section_empty_when_no_paths():
    html, section = docgen.journey_paths_section([])
    assert html == "" and section == ""


def test_journey_paths_section_builds_html_table():
    paths = [JourneyPath(path="A -> B -> C", journeyCount=5, stepCount=3, totalScore=2)]
    html, section = docgen.journey_paths_section(paths)
    assert "<table" in html and "A -&gt; B -&gt; C" in html  # HTML-escaped arrow
    assert "## Journey Paths" in section
    assert "**Total Journeys:** 5" in section


def test_conformance_section_neutralises_hostile_step_names():
    # A DB step name (shared JOURNEYS table → another user's report) that tries to break out
    # of the pipe-table row with a newline + <table> must not do so: newlines/pipes are
    # stripped from the cell, so the markdown stays one clean row and the rendered HTML (with
    # the report's default allow_raw_html=False) contains no injected raw <table>.
    from app.models import ProcessGraph
    from app.services import report as R
    from .conftest import edge, step as mkstep

    hostile = "Login\n\n<table><tr><td>PWNED"
    steps = {hostile: mkstep(hostile), "B": mkstep("B")}
    graph = ProcessGraph(steps=steps, transitions=[edge(hostile, "B", count=10)])
    md = docgen.conformance_section(graph, {"Count": {f"{hostile}->B": 50.0}}, TransitionMetric.count)
    assert "\n\n<table" not in md  # the hostile newline+<table> never starts a fresh line
    rendered = R.md_to_html(md)  # default allow_raw_html=False → the legit pipe table renders,
    # but the hostile payload is escaped INSIDE a cell (never an injected element).
    assert "&lt;table&gt;&lt;tr&gt;&lt;td&gt;PWNED" in rendered
    assert "<td>PWNED" not in rendered  # never a real breakout element


def test_conformance_section_flags_violations():
    graph = _graph()
    # Count norms are percentages of a node's outgoing traffic. A→B is 100% of A's
    # outgoing (only edge), so a 50% norm is exceeded → a violation.
    norms = {"Count": {"A->B": 50.0}}
    md = docgen.conformance_section(graph, norms, TransitionMetric.count)
    assert "## Conformance Check" in md
    assert "VIOLATION" in md
    assert "1 violation(s)" in md


def test_conformance_section_empty_without_norms():
    assert docgen.conformance_section(_graph(), {}, TransitionMetric.count) == ""


def test_conformance_section_norm_is_minimum_flips_the_verdict():
    graph = _graph()
    # A→B is 100% of A's outgoing traffic. Against a 50% CEILING that is a violation;
    # against a 50% FLOOR (norm_is_minimum=True) it is compliant — and vice versa a
    # floor above the actual becomes the violation.
    md_max = docgen.conformance_section(graph, {"Count": {"A->B": 50.0}}, TransitionMetric.count)
    assert "VIOLATION" in md_max and "read as **maximums**" in md_max

    md_min = docgen.conformance_section(
        graph, {"Count": {"A->B": 50.0}}, TransitionMetric.count, norm_is_minimum=True
    )
    assert "VIOLATION" not in md_min and "1 compliant" in md_min
    assert "read as **minimums**" in md_min

    md_min_hi = docgen.conformance_section(
        graph, {"Count": {"A->B": 120.0}}, TransitionMetric.count, norm_is_minimum=True
    )
    assert "1 violation(s)" in md_min_hi  # 100% actual < 120% floor → violation


def test_happy_path_section_warns_when_none_defined():
    md = docgen.happy_path_section([], [])
    assert "No Happy Paths defined" in md


def test_happy_path_section_scores_defined_paths():
    paths = [HappyPath(name="Ideal", steps=["A", "B", "C"])]
    variants = [JourneyPath(path="A -> B -> C", journeyCount=10, stepCount=3, totalScore=0)]
    md = docgen.happy_path_section(paths, variants)
    assert "| Ideal |" in md
    assert "1.00" in md  # full conformance


def test_notes_section_empty_without_notes():
    assert docgen.notes_section([]) == ""


def test_notes_section_separates_open_resolved_and_sorts_by_severity():
    notes = [
        _note(title="Minor", importance="NORMAL", day=5),
        _note(title="Critical", importance="URGENT", day=1),
        _note(title="Fixed thing", importance="IMPORTANT", resolved=True),
    ]
    html = docgen.notes_section(notes)
    assert "Open (2)" in html and "Resolved (1)" in html
    # Within the Open group, URGENT sorts before NORMAL.
    assert html.index("Critical") < html.index("Minor")
    assert "🔴 Urgent" in html and "⚪ Normal" in html
    # The resolved note is in its own section.
    assert "Fixed thing" in html and "🟠 Important" in html


def test_build_prompt_includes_title_template_and_table():
    prompt = docgen.build_prompt("Demo", "Analyse this.", _graph(), "")
    assert "# Project: Demo" in prompt
    assert "Analyse this." in prompt
    assert "| A | B | 10 |" in prompt
    assert "Format your entire response in Markdown" in prompt
