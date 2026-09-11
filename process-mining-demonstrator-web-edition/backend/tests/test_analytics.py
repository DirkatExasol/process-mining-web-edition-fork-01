"""Analytics tests — sampling strategies, happy-path conformance,
process-goodness coverage and the A/B similarity metric (all pure, no DB)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest

from app.models import HappyPath, HappyPathNode, JourneyPath, ProcessGraph
from app.services import analytics

from .conftest import edge, step


@pytest.fixture(autouse=True)
def _seed():
    random.seed(1234)


# ── Sampling ──────────────────────────────────────────────────────────────────


def test_random_sample_respects_target_count():
    ids = [f"E{i}" for i in range(100)]
    chosen = analytics.random_sample(ids, 30)
    assert len(chosen) == 30
    assert len(set(chosen)) == 30  # no duplicates
    assert set(chosen) <= set(ids)


def test_random_sample_caps_at_population():
    ids = ["A", "B", "C"]
    assert sorted(analytics.random_sample(ids, 10)) == ["A", "B", "C"]


def test_temporal_stratified_sample_covers_multiple_months():
    base = datetime(2024, 1, 1)
    pairs: list[tuple[str, datetime]] = []
    for month in range(6):
        for i in range(20):
            pairs.append((f"E{month}-{i}", base + timedelta(days=month * 31 + i)))
    chosen = analytics.temporal_stratified_sample(pairs, 60)
    assert 0 < len(chosen) <= 60
    # Roughly proportional → all six months should be represented.
    months = {cid.split("-")[0] for cid in chosen}
    assert len(months) >= 5


def test_temporal_stratified_sample_empty_input():
    assert analytics.temporal_stratified_sample([], 10) == []


def test_path_diverse_sample_prioritises_common_paths():
    pairs = [(f"E{i}", "A->B->C") for i in range(80)]
    pairs += [(f"F{i}", "A->D->C") for i in range(20)]
    chosen = set(analytics.path_diverse_sample(pairs, 50))
    assert 0 < len(chosen) <= 50
    # Both variants should appear in a coverage-maximising sample.
    assert any(c.startswith("E") for c in chosen)
    assert any(c.startswith("F") for c in chosen)


# ── Happy-path conformance ────────────────────────────────────────────────────


def _steps(*names):
    return [HappyPathNode(step=n) for n in names]


def test_conformance_full_match_scores_one():
    path = HappyPath(name="Ideal", nodes=_steps("A", "B", "C"))
    variants = [JourneyPath(path="A -> B -> C", journeyCount=10, stepCount=3, totalScore=0)]
    assert analytics.happy_path_conformance(path, variants) == pytest.approx(1.0)


def test_conformance_is_journey_count_weighted():
    path = HappyPath(name="Ideal", nodes=_steps("A", "B", "C"))  # edges A->B, B->C
    variants = [
        JourneyPath(path="A -> B -> C", journeyCount=8, stepCount=3, totalScore=0),  # coverage 1.0
        JourneyPath(path="A -> D -> C", journeyCount=2, stepCount=3, totalScore=0),  # coverage 0.0
    ]
    # (8*1.0 + 2*0.0) / 10 = 0.8
    assert analytics.happy_path_conformance(path, variants) == pytest.approx(0.8)


def test_conformance_scores_against_best_matching_route():
    # A -> split{ (C) | (D) } (terminal split == legacy branches). Best route wins.
    path = HappyPath(name="Ideal", nodes=[
        HappyPathNode(step="A"), HappyPathNode(step="B"),
        HappyPathNode(branches=[_steps("C"), _steps("D")]),
    ])
    variants = [JourneyPath(path="A -> B -> D", journeyCount=5, stepCount=3, totalScore=0)]
    assert analytics.happy_path_conformance(path, variants) == pytest.approx(1.0)


def test_conformance_handles_nested_split_and_rejoin():
    # A -> split{ (B -> split{(C)|(X)}) | (D) } -> E  (rejoin then continue to E).
    path = HappyPath(name="Ideal", nodes=[
        HappyPathNode(step="A"),
        HappyPathNode(branches=[
            [HappyPathNode(step="B"),
             HappyPathNode(branches=[_steps("C"), _steps("X")])],
            _steps("D"),
        ]),
        HappyPathNode(step="E"),
    ])
    routes = {" -> ".join(r) for r in analytics.happy_path_routes(path.nodes)}
    assert routes == {"A -> B -> C -> E", "A -> B -> X -> E", "A -> D -> E"}
    # A journey taking the rejoining "D" alternative matches that route fully.
    v = [JourneyPath(path="A -> D -> E", journeyCount=3, stepCount=3, totalScore=0)]
    assert analytics.happy_path_conformance(path, v) == pytest.approx(1.0)


def test_routes_are_capped():
    nodes = [HappyPathNode(branches=[_steps(f"s{i}a"), _steps(f"s{i}b")]) for i in range(20)]
    assert len(analytics.happy_path_routes(nodes)) <= analytics._MAX_ROUTES


def test_conformance_none_for_too_short_path_or_no_variants():
    v = [JourneyPath(path="A -> B", journeyCount=1, stepCount=2, totalScore=0)]
    assert analytics.happy_path_conformance(HappyPath(name="x", nodes=_steps("A")), v) is None
    assert analytics.happy_path_conformance(HappyPath(name="x", nodes=_steps("A", "B")), []) is None


# ── Process-goodness coverage penalty ────────────────────────────────────────


def test_goodness_coverage_penalty():
    # raw × (filtered / total) ** 0.5
    assert analytics.apply_goodness_coverage(10.0, 25, 100) == pytest.approx(5.0)
    # full coverage → unchanged
    assert analytics.apply_goodness_coverage(7.0, 100, 100) == pytest.approx(7.0)
    # no baseline → unchanged
    assert analytics.apply_goodness_coverage(3.0, 5, 0) == pytest.approx(3.0)


# ── A/B similarity (Q metric) ────────────────────────────────────────────────


def _graph_from_paths(paths: list[str]) -> ProcessGraph:
    steps: dict = {}
    transitions = []
    for path in paths:
        nodes = path.split(" -> ")
        for name in nodes:
            steps.setdefault(name, step(name))
        for a, b in zip(nodes, nodes[1:]):
            transitions.append(edge(a, b))
    return ProcessGraph(steps=steps, transitions=transitions)


def test_similarity_of_identical_inputs_is_high():
    variants = [JourneyPath(path="A -> B -> C", journeyCount=10, stepCount=3, totalScore=0)]
    graph = _graph_from_paths(["A -> B -> C"])
    q = analytics.ab_similarity(variants, variants, graph, graph)
    assert q is not None and q == pytest.approx(1.0)


def test_similarity_of_disjoint_processes_is_low():
    va = [JourneyPath(path="A -> B -> C", journeyCount=10, stepCount=3, totalScore=0)]
    vb = [JourneyPath(path="X -> Y -> Z", journeyCount=10, stepCount=3, totalScore=0)]
    ga = _graph_from_paths(["A -> B -> C"])
    gb = _graph_from_paths(["X -> Y -> Z"])
    q = analytics.ab_similarity(va, vb, ga, gb)
    assert q is not None and q < 0.5


def test_similarity_none_when_a_side_is_empty():
    variants = [JourneyPath(path="A -> B", journeyCount=1, stepCount=2, totalScore=0)]
    graph = _graph_from_paths(["A -> B"])
    assert analytics.ab_similarity([], variants, graph, graph) is None
