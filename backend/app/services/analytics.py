"""Pure analytics ported from AppViewModel.swift: sampling strategies,
happy-path conformance, process-goodness coverage and the A/B similarity metric.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import datetime

from ..models import HappyPath, JourneyPath, ProcessGraph

# ── Sampling strategies ───────────────────────────────────────────────────────


def random_sample(event_ids: list[str], target_count: int) -> list[str]:
    ids = list(event_ids)
    random.shuffle(ids)
    return ids[:target_count]


def temporal_stratified_sample(
    pairs: list[tuple[str, datetime]], target_count: int
) -> list[str]:
    """Proportional selection across calendar-month buckets."""
    if not pairs or target_count <= 0:
        return []
    buckets: dict[str, list[str]] = defaultdict(list)
    for event_id, when in pairs:
        buckets[f"{when.year}-{when.month:02d}"].append(event_id)

    total = len(pairs)
    result: list[str] = []
    for key in sorted(buckets):
        ids = buckets[key]
        share = max(1, round(len(ids) / total * target_count))
        shuffled = list(ids)
        random.shuffle(shuffled)
        result.extend(shuffled[:share])
        if len(result) >= target_count:
            break
    return result[:target_count]


def path_diverse_sample(pairs: list[tuple[str, str]], target_count: int) -> list[str]:
    """Coverage-maximising selection across distinct journey variants."""
    if not pairs or target_count <= 0:
        return []
    buckets: dict[str, list[str]] = defaultdict(list)
    for event_id, path in pairs:
        buckets[path].append(event_id)

    total = len(pairs)
    result: list[str] = []
    # Most common paths fill their quota first, matching the Swift ordering.
    for _, ids in sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True):
        share = max(1, round(len(ids) / total * target_count))
        shuffled = list(ids)
        random.shuffle(shuffled)
        result.extend(shuffled[:share])
        if len(result) >= target_count:
            break
    return result[:target_count]


# ── Happy-path conformance ────────────────────────────────────────────────────


def _edge_set(steps: list[str]) -> set[str]:
    return {f"{a} -> {b}" for a, b in zip(steps, steps[1:])}


def happy_path_conformance(
    path: HappyPath, variants: list[JourneyPath]
) -> float | None:
    """Journey-count-weighted edge coverage; branching paths score each journey
    against the branch it matches best."""
    if len(path.steps) < 2 or not variants:
        return None

    non_empty = [b for b in path.branches if b.steps]
    complete_paths = (
        [path.steps]
        if not non_empty
        else [p for b in non_empty if len(p := path.steps + b.steps) >= 2]
    )
    if not complete_paths:
        return None

    path_edge_sets = [_edge_set(steps) for steps in complete_paths]

    weighted_sum = 0.0
    total_count = 0
    for variant in variants:
        v_edges = _edge_set(variant.path.split(" -> "))
        coverage = max(
            (len(edges & v_edges) / len(edges) for edges in path_edge_sets if edges),
            default=0.0,
        )
        weighted_sum += variant.journeyCount * coverage
        total_count += variant.journeyCount

    if total_count <= 0:
        return None
    return weighted_sum / total_count


def apply_goodness_coverage(
    raw: float, filtered_count: int, total_journey_count: int | None
) -> float:
    """`raw × (filtered / total) ** 0.5` — penalises heavily filtered views."""
    baseline = float(total_journey_count or filtered_count)
    if baseline <= 0 or filtered_count <= 0:
        return raw
    return raw * math.pow(filtered_count / baseline, 0.5)


# ── A/B process similarity (Q metric) ─────────────────────────────────────────

AB_SIMILARITY_VARIANT_LIMIT = 500


def ab_similarity(
    variants_a: list[JourneyPath],
    variants_b: list[JourneyPath],
    graph_a: ProcessGraph,
    graph_b: ProcessGraph,
) -> float | None:
    """Q = 0.4·Q_var + 0.4·Q_nodes + 0.2·Q_cov."""
    if not variants_a or not variants_b:
        return None
    # Too many variants would be slow and the score untrustworthy.
    if len(variants_a) + len(variants_b) > AB_SIMILARITY_VARIANT_LIMIT * 2:
        return None

    total_count = sum(v.journeyCount for v in variants_a) + sum(
        v.journeyCount for v in variants_b
    )
    if total_count <= 0:
        return None
    total = float(total_count)

    variant_freq: dict[str, float] = defaultdict(float)
    for v in variants_a:
        variant_freq[v.path] += v.journeyCount / total
    for v in variants_b:
        variant_freq[v.path] += v.journeyCount / total

    edges_a = {(t.fromStep, t.toStep) for t in graph_a.transitions}
    edges_b = {(t.fromStep, t.toStep) for t in graph_b.transitions}

    node_scores: dict[str, float] = {}
    for graph in (graph_a, graph_b):
        for name, step in graph.steps.items():
            if step.score is not None:
                node_scores[name] = max(node_scores.get(name, 0.0), abs(float(step.score)))

    sum_abs_diff = sum_max_cost = 0.0
    sum_min_nodes = sum_max_nodes = 0.0
    sum_fits_both = total_freq = 0.0

    for path, freq in variant_freq.items():
        steps = path.split(" -> ")
        if len(steps) < 2:
            continue
        num_edges = len(steps) - 1

        missing_a = missing_b = 0
        for i in range(num_edges):
            edge = (steps[i], steps[i + 1])
            if edge not in edges_a:
                missing_a += 1
            if edge not in edges_b:
                missing_b += 1
        cost_a = missing_a / num_edges
        cost_b = missing_b / num_edges

        sum_abs_diff += freq * abs(cost_a - cost_b)
        sum_max_cost += freq * max(cost_a, cost_b)

        # Q_nodes: soft visit = presence in the variant × (1 − alignment cost)
        nodes_in_variant = set(steps)
        min_ns = max_ns = 0.0
        for name, abs_score in node_scores.items():
            in_var = 1.0 if name in nodes_in_variant else 0.0
            v1 = in_var * (1.0 - cost_a)
            v2 = in_var * (1.0 - cost_b)
            min_ns += min(v1, v2) * abs_score
            max_ns += max(v1, v2) * abs_score
        sum_min_nodes += freq * min_ns
        sum_max_nodes += freq * max_ns

        sum_fits_both += freq * (1.0 if cost_a == 0 and cost_b == 0 else 0.0)
        total_freq += freq

    q_var = 1.0 - sum_abs_diff / sum_max_cost if sum_max_cost > 0 else 1.0
    q_nodes = sum_min_nodes / sum_max_nodes if sum_max_nodes > 0 else 1.0
    q_cov = sum_fits_both / total_freq if total_freq > 0 else 0.0

    score = 0.4 * q_var + 0.4 * q_nodes + 0.2 * q_cov
    return score if math.isfinite(score) else None
