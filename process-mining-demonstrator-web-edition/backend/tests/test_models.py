"""Model logic tests — the Python counterpart of Swift's ModelLogicTests.

Pure value-type behaviour: time granularity, transition metrics, graph maxima,
happy-path decoding, server/profile defaults and round-trips, note targets,
sample-set SQL fragments and colour parsing.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.models import (
    ConnectionProfile,
    DatabaseServer,
    HappyPath,
    HappyPathNode,
    LLMServer,
    NoteTarget,
    ProcessGraph,
    ProcessTransition,
    SampleSet,
    TimeGranularity,
    TransitionMetric,
)


# ── TimeGranularity.auto ──────────────────────────────────────────────────────


def test_time_granularity_picks_bucket_by_span():
    base = datetime(2023, 11, 14)

    def granularity(days: int) -> TimeGranularity:
        return TimeGranularity.auto(base, base + timedelta(days=days))

    assert granularity(0) is TimeGranularity.day
    assert granularity(14) is TimeGranularity.day
    assert granularity(15) is TimeGranularity.week
    assert granularity(90) is TimeGranularity.week
    assert granularity(91) is TimeGranularity.month


# ── TransitionMetric ──────────────────────────────────────────────────────────


def test_only_time_metrics_are_time_based():
    assert TransitionMetric.count.is_time_based is False
    for metric in (
        TransitionMetric.avgTime,
        TransitionMetric.minTime,
        TransitionMetric.maxTime,
        TransitionMetric.stdDev,
    ):
        assert metric.is_time_based is True


def test_transition_exposes_the_right_metric_value():
    t = ProcessTransition(
        fromStep="A",
        toStep="B",
        occurrences=7,
        avgSecs=1.0,
        minSecs=0.5,
        maxSecs=3.0,
        stdDevSecs=0.25,
    )
    assert t.id == "A->B"
    assert t.metric_value(TransitionMetric.count) == 7
    assert t.metric_value(TransitionMetric.avgTime) == 1.0
    assert t.metric_value(TransitionMetric.minTime) == 0.5
    assert t.metric_value(TransitionMetric.maxTime) == 3.0
    assert t.metric_value(TransitionMetric.stdDev) == 0.25


# ── ProcessGraph aggregates ──────────────────────────────────────────────────


def test_process_graph_reports_maxima():
    graph = ProcessGraph(
        steps={},
        transitions=[
            ProcessTransition(fromStep="A", toStep="B", occurrences=3, avgSecs=2, minSecs=1, maxSecs=4),
            ProcessTransition(fromStep="B", toStep="C", occurrences=9, avgSecs=5, minSecs=2, maxSecs=8),
        ],
    )
    assert graph.max_occurrences == 9
    assert graph.max_value(TransitionMetric.count) == 9
    assert graph.max_value(TransitionMetric.avgTime) == 5
    assert graph.max_value(TransitionMetric.maxTime) == 8


def test_empty_process_graph_falls_back_to_one():
    graph = ProcessGraph()
    assert graph.transitions == []
    assert graph.max_occurrences == 1  # guarded fallback, never 0
    assert graph.max_value(TransitionMetric.count) == 1


# ── HappyPath backward-compatible decoding ───────────────────────────────────


def test_happy_path_migrates_legacy_trunk_only():
    # Legacy flat JSON (trunk, no branches) folds into a linear list of step nodes.
    payload = json.loads('{"id":"X","name":"Ideal","steps":["A","B","C"]}')
    path = HappyPath(**payload)
    assert path.name == "Ideal"
    assert [n.step for n in path.nodes] == ["A", "B", "C"]
    assert all(not n.branches for n in path.nodes)


def test_happy_path_migrates_legacy_branches_to_trailing_split():
    # Legacy trunk + flat branches → step nodes + one trailing split (empty branch dropped).
    payload = {
        "id": "Y", "name": "Main", "steps": ["A", "B"],
        "branches": [{"label": "l", "steps": ["C"]}, {"steps": ["D"]}, {"steps": []}],
    }
    path = HappyPath(**payload)
    assert [n.step for n in path.nodes[:2]] == ["A", "B"]
    split = path.nodes[2]
    assert split.step == "" and [[m.step for m in br] for br in split.branches] == [["C"], ["D"]]


def test_happy_path_round_trips_nested_nodes():
    # A -> split{ (B -> split{(C)|(D)}) | (E) } -> F  (nesting + rejoin) survives JSON.
    original = HappyPath(
        name="Nested",
        nodes=[
            HappyPathNode(step="A"),
            HappyPathNode(branches=[
                [HappyPathNode(step="B"),
                 HappyPathNode(branches=[[HappyPathNode(step="C")], [HappyPathNode(step="D")]])],
                [HappyPathNode(step="E")],
            ]),
            HappyPathNode(step="F"),
        ],
    )
    decoded = HappyPath(**json.loads(original.model_dump_json(by_alias=True)))
    assert decoded.model_dump() == original.model_dump()
    assert decoded.nodes[1].branches[0][1].branches[0][0].step == "C"


def test_happy_path_split_carries_a_rejoin_label():
    original = HappyPath(
        name="Named",
        nodes=[
            HappyPathNode(label="Fork", rejoinLabel="Merge", branches=[
                [HappyPathNode(step="A")], [HappyPathNode(step="B")],
            ]),
            HappyPathNode(step="C"),
        ],
    )
    decoded = HappyPath(**json.loads(original.model_dump_json(by_alias=True)))
    assert decoded.nodes[0].label == "Fork" and decoded.nodes[0].rejoinLabel == "Merge"
    # Legacy blobs (no rejoinLabel) still decode, defaulting to "".
    legacy = HappyPath(**{"id": "X", "name": "P", "steps": ["A", "B"]})
    assert all(n.rejoinLabel == "" for n in legacy.nodes)


# ── Server definitions & connection pairing ──────────────────────────────────


def test_database_server_has_sane_defaults_and_round_trips():
    server = DatabaseServer()
    assert server.port == 8563
    assert server.certModeRaw == "verify"
    assert server.minRSAKeySizeBits == 2048

    server.name = "Prod"
    server.host = "db.example.com"
    server.schema_ = "PM"
    decoded = DatabaseServer.model_validate(json.loads(server.model_dump_json(by_alias=True)))
    assert decoded == server
    # `schema` is the wire name; `schema_` the field.
    assert json.loads(server.model_dump_json(by_alias=True))["schema"] == "PM"


def test_llm_server_round_trips():
    server = LLMServer(name="Local", serverURL="http://localhost:1234/v1", model="qwen3")
    decoded = LLMServer.model_validate(json.loads(server.model_dump_json(by_alias=True)))
    assert decoded == server


def test_connection_profile_is_a_pairing_and_round_trips():
    profile = ConnectionProfile()
    assert profile.databaseServerId is None
    assert profile.llmServerId is None

    profile.name = "Prod"
    profile.databaseServerId = "db-1"
    profile.llmServerId = "llm-1"
    decoded = ConnectionProfile.model_validate(
        json.loads(profile.model_dump_json(by_alias=True))
    )
    assert decoded == profile


# ── NoteTarget round-trips ───────────────────────────────────────────────────


def test_note_target_edge_round_trips():
    target = NoteTarget.model_validate({"type": "edge", "from": "A", "to": "B"})
    assert target.display_name == "A → B"
    assert target.is_node is False
    decoded = NoteTarget.model_validate(json.loads(target.model_dump_json(by_alias=True)))
    assert decoded.type == "edge"
    assert decoded.from_ == "A"
    assert decoded.to == "B"


def test_note_target_node_round_trips():
    target = NoteTarget(type="node", value="Checkout")
    assert target.display_name == "Checkout"
    assert target.is_node is True
    decoded = NoteTarget.model_validate(json.loads(target.model_dump_json(by_alias=True)))
    assert decoded.type == "node"
    assert decoded.value == "Checkout"


# ── SampleSet SQL fragments ──────────────────────────────────────────────────


def test_sample_set_sql_fragments():
    assert SampleSet.original.is_original is True
    assert SampleSet.original.sql_fragment() == "(SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL)"
    assert SampleSet.sample1.sql_fragment() == "SAMPLE_SET = 'SAMPLE_1'"
    assert SampleSet.sample2.sql_fragment(alias="j") == "j.SAMPLE_SET = 'SAMPLE_2'"
    assert (
        SampleSet.original.sql_fragment(alias="j")
        == "(j.SAMPLE_SET = 'ORIGINAL' OR j.SAMPLE_SET IS NULL)"
    )


def test_normalize_importance():
    from app.models import NOTE_IMPORTANCE, normalize_importance

    for level in NOTE_IMPORTANCE:
        assert normalize_importance(level) == level
        assert normalize_importance(level.lower()) == level  # case-insensitive
    # Anything unknown / non-string / injection-y collapses to the NORMAL default.
    assert normalize_importance("bogus") == "NORMAL"
    assert normalize_importance("") == "NORMAL"
    assert normalize_importance(None) == "NORMAL"
    assert normalize_importance(42) == "NORMAL"
    assert normalize_importance("URGENT'; DROP TABLE NOTES; --") == "NORMAL"
