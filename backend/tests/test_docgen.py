"""AI-documentation builder tests — the locally-rendered report sections and the
LLM prompt assembly (no network, no DB)."""

from __future__ import annotations

from app.models import HappyPath, JourneyPath, ProcessGraph, TransitionMetric
from app.services import docgen

from .conftest import edge, step


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


def test_build_prompt_includes_title_template_and_table():
    prompt = docgen.build_prompt("Demo", "Analyse this.", _graph(), "")
    assert "# Project: Demo" in prompt
    assert "Analyse this." in prompt
    assert "| A | B | 10 |" in prompt
    assert "Format your entire response in Markdown" in prompt
