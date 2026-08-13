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
