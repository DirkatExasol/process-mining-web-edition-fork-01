"""Shared fixtures for the pure-logic test suite.

Every test here runs without a database connection, mirroring the Swift
`ModelLogicTests` / `SimulationEngineTests` which run on the host with no Exasol.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `app` package importable without installing the backend.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest

from app.models import (
    ProcessGraph,
    ProcessTransition,
    SimulationConfig,
    StepInfo,
)


def step(name: str, end_of_process: bool = False) -> StepInfo:
    return StepInfo(
        step=name,
        description=name,
        bgColor="blue",
        fgColor="white",
        shape="stadium",
        endOfProcess=end_of_process,
    )


def edge(
    frm: str, to: str, count: int = 10, avg_secs: float | None = 3600.0
) -> ProcessTransition:
    return ProcessTransition(fromStep=frm, toStep=to, occurrences=count, avgSecs=avg_secs)


@pytest.fixture
def linear_graph() -> tuple[ProcessGraph, dict[str, StepInfo]]:
    """A → B → C, with C terminal."""
    infos = {"A": step("A"), "B": step("B"), "C": step("C", end_of_process=True)}
    graph = ProcessGraph(steps=infos, transitions=[edge("A", "B"), edge("B", "C")])
    return graph, infos


@pytest.fixture
def fork_graph() -> tuple[ProcessGraph, dict[str, StepInfo]]:
    """A → B → C and A → D → C, equal weights, C terminal."""
    infos = {
        "A": step("A"),
        "B": step("B"),
        "D": step("D"),
        "C": step("C", end_of_process=True),
    }
    graph = ProcessGraph(
        steps=infos,
        transitions=[edge("A", "B"), edge("B", "C"), edge("A", "D"), edge("D", "C")],
    )
    return graph, infos


def config(
    journey_count: int = 100,
    excluded: list[str] | None = None,
    required: list[str] | None = None,
    max_steps: int = 60,
) -> SimulationConfig:
    return SimulationConfig(
        journeyCount=journey_count,
        excludedSteps=excluded or [],
        requiredSteps=required or [],
        maxStepsPerJourney=max_steps,
    )
