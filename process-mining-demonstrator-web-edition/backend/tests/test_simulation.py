"""Simulation engine tests — the Python counterpart of Swift's
SimulationEngineTests. Covers `simulate()` and `build_graph()`.

Note: web variant paths join steps with " → " (matching SimulationEngine.swift).
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pytest

from app.models import ProcessGraph, SimulatedEvent, SimulationConfig, StepInfo
from app.services import simulation

from .conftest import config, edge, step


@pytest.fixture(autouse=True)
def _seed():
    """Deterministic runs so variant-coverage assertions never flake."""
    random.seed(20240607)


# ── Empty / boundary ──────────────────────────────────────────────────────────


def test_empty_graph_returns_empty_result():
    result = simulation.simulate(ProcessGraph(), {}, config())
    assert result.totalJourneys == 0
    assert result.events == []
    assert result.variants == []
    assert result.cycleTimes == []


# ── Journey count ─────────────────────────────────────────────────────────────


def test_linear_graph_produces_requested_journey_count(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=100))
    assert result.totalJourneys == 100
    assert len(result.cycleTimes) == 100


def test_linear_journey_visits_each_step_exactly_once(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50))
    assert len(result.events) == 150  # A → B → C = 3 events per journey


# ── Event ordering ────────────────────────────────────────────────────────────


def test_events_are_chronologically_ordered_within_journey(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50))
    by_journey: dict[str, list[datetime]] = {}
    for e in result.events:
        by_journey.setdefault(e.journeyId, []).append(e.timestamp)
    for timestamps in by_journey.values():
        assert timestamps == sorted(timestamps)


# ── Cycle times ───────────────────────────────────────────────────────────────


def test_cycle_times_are_all_positive(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50))
    assert all(t > 0 for t in result.cycleTimes)


def test_statistics_are_consistent_with_cycle_times(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=100))
    times = result.cycleTimes
    assert result.totalJourneys == len(times)
    assert result.minCycleTimeSecs == min(times)
    assert result.maxCycleTimeSecs == max(times)
    assert abs(result.avgCycleTimeSecs - sum(times) / len(times)) < 1e-6
    assert result.stdDevCycleTimeSecs >= 0


# ── Variant accounting ────────────────────────────────────────────────────────


def test_variant_percentages_sum_to_hundred(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=100))
    assert abs(sum(v.percentage for v in result.variants) - 100.0) < 1e-6


def test_variant_counts_sum_to_total_journeys(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=100))
    assert sum(v.count for v in result.variants) == result.totalJourneys


def test_variants_are_sorted_by_count_descending(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=200))
    counts = [v.count for v in result.variants]
    assert all(a >= b for a, b in zip(counts, counts[1:]))


# ── Variant path labels ───────────────────────────────────────────────────────


def test_linear_graph_has_exactly_one_variant_with_correct_path(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50))
    assert len(result.variants) == 1
    assert result.variants[0].path == "A → B → C"


def test_fork_graph_produces_two_variants_with_correct_paths(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=200))
    assert {v.path for v in result.variants} == {"A → B → C", "A → D → C"}


def test_variant_avg_cycle_time_is_positive(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=100))
    assert all(v.avgCycleTimeSecs > 0 for v in result.variants)


# ── Excluded steps ────────────────────────────────────────────────────────────


def test_excluded_step_never_appears_in_events(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=100, excluded=["D"]))
    assert "D" not in {e.step for e in result.events}
    assert result.totalJourneys == 100


def test_excluding_all_transitions_from_start_returns_empty(linear_graph):
    graph, infos = linear_graph
    # Excluding B removes A→B and B→C; no valid path exists from A.
    result = simulation.simulate(graph, infos, config(journey_count=50, excluded=["B"]))
    assert result.totalJourneys == 0


# ── Required steps ────────────────────────────────────────────────────────────


def test_required_step_that_is_never_visited_filters_all_journeys(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(
        graph, infos, config(journey_count=50, required=["MISSING"])
    )
    assert result.totalJourneys == 0


def test_required_step_visited_by_every_journey_preserves_count(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50, required=["B"]))
    assert result.totalJourneys == 50


def test_required_step_on_one_fork_branch_filters_other_branch(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(graph, infos, config(journey_count=200, required=["B"]))
    assert result.totalJourneys > 0
    assert "D" not in {e.step for e in result.events}


def test_mutually_exclusive_required_steps_yield_no_journeys(fork_graph):
    graph, infos = fork_graph
    result = simulation.simulate(
        graph, infos, config(journey_count=100, required=["B", "D"])
    )
    assert result.totalJourneys == 0


# ── Cyclic graph / max steps ─────────────────────────────────────────────────


def test_cyclic_graph_respects_max_steps_per_journey():
    infos = {"A": step("A"), "B": step("B")}  # A → B → A, no end step
    graph = ProcessGraph(steps=infos, transitions=[edge("A", "B"), edge("B", "A")])
    result = simulation.simulate(
        graph, infos, config(journey_count=20, max_steps=4)
    )
    assert result.totalJourneys == 20
    by_journey: dict[str, int] = {}
    for e in result.events:
        by_journey[e.journeyId] = by_journey.get(e.journeyId, 0) + 1
    # first step + at most max_steps transitions = 5 events max
    assert all(count <= 5 for count in by_journey.values())


# ── build_graph ───────────────────────────────────────────────────────────────


def test_build_graph_from_empty_events_is_empty():
    graph = simulation.build_graph([], {})
    assert graph.transitions == []
    assert graph.steps == {}


def _events(base: datetime, pairs: list[tuple[str, str, float, float]]) -> list[SimulatedEvent]:
    out: list[SimulatedEvent] = []
    for jid, s, offset, _ in pairs:
        out.append(SimulatedEvent(journeyId=jid, step=s, timestamp=base + timedelta(seconds=offset)))
    return out


def test_build_graph_computes_correct_transition_stats():
    base = datetime(2023, 11, 14)
    events = [
        SimulatedEvent(journeyId="J1", step="A", timestamp=base),
        SimulatedEvent(journeyId="J1", step="B", timestamp=base + timedelta(seconds=7200)),
        SimulatedEvent(journeyId="J2", step="A", timestamp=base + timedelta(seconds=100)),
        SimulatedEvent(journeyId="J2", step="B", timestamp=base + timedelta(seconds=3700)),
    ]
    graph = simulation.build_graph(events, {})
    assert len(graph.transitions) == 1
    t = graph.transitions[0]
    assert (t.fromStep, t.toStep) == ("A", "B")
    assert t.occurrences == 2
    assert abs((t.avgSecs or 0) - 5400.0) < 1.0  # avg of 7200 and 3600


def test_build_graph_computes_min_max_and_std_dev():
    base = datetime(2023, 11, 14)
    events = [
        SimulatedEvent(journeyId="J1", step="A", timestamp=base),
        SimulatedEvent(journeyId="J1", step="B", timestamp=base + timedelta(seconds=1000)),
        SimulatedEvent(journeyId="J2", step="A", timestamp=base + timedelta(seconds=5000)),
        SimulatedEvent(journeyId="J2", step="B", timestamp=base + timedelta(seconds=7000)),
        SimulatedEvent(journeyId="J3", step="A", timestamp=base + timedelta(seconds=10000)),
        SimulatedEvent(journeyId="J3", step="B", timestamp=base + timedelta(seconds=13000)),
    ]
    t = simulation.build_graph(events, {}).transitions[0]
    assert t.occurrences == 3
    assert abs((t.minSecs or 0) - 1000.0) < 1.0
    assert abs((t.maxSecs or 0) - 3000.0) < 1.0
    # population stdDev of {1000,2000,3000} = sqrt(2e6/3) ≈ 816.5
    assert abs((t.stdDevSecs or 0) - 816.5) < 1.0


def test_build_graph_sorts_events_by_timestamp_within_journey():
    base = datetime(2023, 11, 14)
    events = [
        SimulatedEvent(journeyId="J1", step="B", timestamp=base + timedelta(seconds=3600)),
        SimulatedEvent(journeyId="J1", step="A", timestamp=base),
    ]
    t = simulation.build_graph(events, {}).transitions[0]
    assert (t.fromStep, t.toStep) == ("A", "B")
    assert abs((t.avgSecs or 0) - 3600.0) < 1.0


def test_build_graph_contains_all_visited_steps():
    base = datetime(2023, 11, 14)
    events = [
        SimulatedEvent(journeyId="J1", step="X", timestamp=base),
        SimulatedEvent(journeyId="J1", step="Y", timestamp=base + timedelta(seconds=60)),
    ]
    graph = simulation.build_graph(events, {})
    assert sorted(graph.steps.keys()) == ["X", "Y"]


# ── simProcessGraph ───────────────────────────────────────────────────────────


def test_simulated_graph_contains_expected_transitions(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50))
    assert {t.id for t in result.simProcessGraph.transitions} == {"A->B", "B->C"}


def test_simulated_graph_transition_occurrences_match_journey_count(linear_graph):
    graph, infos = linear_graph
    result = simulation.simulate(graph, infos, config(journey_count=50))
    by_id = {t.id: t.occurrences for t in result.simProcessGraph.transitions}
    assert by_id["A->B"] == 50
    assert by_id["B->C"] == 50
