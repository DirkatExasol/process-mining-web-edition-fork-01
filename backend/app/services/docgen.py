"""AI-supported documentation — port of AppViewModel.runLLMAnalysis().

Builds the prompt that is sent to the LLM plus the three summary sections that
are rendered locally (journey paths, conformance gap analysis, happy-path
conformance) and never sent to the model.
"""

from __future__ import annotations

import html
from collections import defaultdict

from ..models import (
    NOTE_IMPORTANCE,
    HappyPath,
    JourneyPath,
    ProcessGraph,
    ProcessNote,
    TransitionMetric,
    normalize_importance,
)
from .analytics import happy_path_conformance, happy_path_routes

_SEVERITY_LABEL = {
    "URGENT": "🔴 Urgent",
    "IMPORTANT": "🟠 Important",
    "INFO": "🔵 Info",
    "NORMAL": "⚪ Normal",
}


def notes_section(notes: list[ProcessNote]) -> str:
    """HTML for the Notes chapter: two tables (Open / Resolved), each sorted by severity
    (most severe first, then most recent). Returns '' when there are no notes."""
    if not notes:
        return ""

    def esc(s: str) -> str:
        return html.escape(s or "", quote=False)

    def rank(n: ProcessNote) -> int:
        return NOTE_IMPORTANCE.index(normalize_importance(n.importance))

    def table(group: list[ProcessNote], empty_msg: str) -> str:
        if not group:
            return f'<p class="caption">{empty_msg}</p>'
        rows = ""
        for n in sorted(group, key=lambda x: (rank(x), x.createdAt), reverse=True):
            elem = ("⬚ " if n.target.is_node else "→ ") + n.target.display_name
            when = n.createdAt.strftime("%d %b %Y") if hasattr(n.createdAt, "strftime") else str(n.createdAt)
            text = esc(n.text).replace("\n", "<br>")
            rows += (
                "<tr>"
                f"<td>{esc(_SEVERITY_LABEL[normalize_importance(n.importance)])}</td>"
                f"<td>{esc(elem)}</td>"
                f"<td>{esc(n.title) or '—'}</td>"
                f"<td>{text or '—'}</td>"
                f"<td>{esc(n.authorName or n.username) or '—'}</td>"
                f"<td>{esc(when)}</td>"
                "</tr>"
            )
        return (
            '<table class="ltable"><thead><tr>'
            "<th>Severity</th><th>Element</th><th>Title</th><th>Note</th><th>Author</th><th>Date</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    open_notes = [n for n in notes if not n.resolved]
    resolved_notes = [n for n in notes if n.resolved]
    return (
        f"<h3>Open ({len(open_notes)})</h3>{table(open_notes, 'No open notes.')}"
        f"<h3>Resolved ({len(resolved_notes)})</h3>{table(resolved_notes, 'No resolved notes.')}"
    )


def _fmt_duration(secs: float) -> str:
    if secs < 60:
        return f"{secs:.0f}s"
    if secs < 3600:
        return f"{secs / 60:.0f}m"
    if secs < 86400:
        return f"{secs / 3600:.1f}h"
    return f"{secs / 86400:.1f}d"


def _fmt_value(value: float, metric: TransitionMetric) -> str:
    if metric is TransitionMetric.count:
        return f"{value:.1f}%"  # count norms are percentages
    if metric.is_time_based:
        return _fmt_duration(value)
    return str(round(value))


def transitions_table(graph: ProcessGraph) -> str:
    """Markdown table of the A-Chart transitions, plus a summary line."""
    ordered = sorted(graph.transitions, key=lambda t: t.occurrences, reverse=True)
    table = "| From Step | To Step | Count |\n|-----------|---------|-------|\n"
    for t in ordered:
        table += f"| {t.fromStep} | {t.toStep} | {t.occurrences} |\n"
    counts = [t.occurrences for t in ordered]
    if counts:
        total = sum(counts)
        avg = total // len(counts)
        table += (
            f"\n**Transitions:** {len(ordered)}  |  **Total:** {total}  |  "
            f"**Min:** {min(counts)}  |  **Max:** {max(counts)}  |  **Avg:** {avg}"
        )
    return table


def journey_paths_section(paths: list[JourneyPath]) -> tuple[str, str]:
    """Returns (html_table, markdown_section). Empty strings when there are none."""
    if not paths:
        return "", ""

    def esc(s: str) -> str:
        return html.escape(s, quote=False)

    rows = "".join(
        "<tr>"
        f"<td style='overflow-wrap:break-word;word-break:break-word'>{esc(p.path)}</td>"
        f"<td style='text-align:right'>{p.journeyCount:,}</td>"
        f"<td style='text-align:right'>{p.stepCount}</td>"
        f"<td style='text-align:right'>{p.totalScore}</td>"
        f"<td style='text-align:right'>{p.aggregatedScore:,}</td>"
        "</tr>"
        for p in paths
    )
    table = (
        "<table style='table-layout:fixed;width:100%'>"
        "<colgroup>"
        "<col style='width:46%'><col style='width:14%'><col style='width:12%'>"
        "<col style='width:14%'><col style='width:14%'>"
        "</colgroup>"
        "<thead><tr>"
        "<th>Journey Path</th>"
        "<th style='white-space:nowrap;text-align:right'>Journeys</th>"
        "<th style='white-space:nowrap;text-align:right'>Steps</th>"
        "<th style='white-space:nowrap;text-align:right'>Score/J</th>"
        "<th style='white-space:nowrap;text-align:right'>Total</th>"
        "</tr></thead><tbody>"
        f"{rows}</tbody></table>"
    )
    total_journeys = sum(p.journeyCount for p in paths)
    section = (
        f"\n\n## Journey Paths\n\n{table}\n\n"
        f"**Paths:** {len(paths)}  |  **Total Journeys:** {total_journeys:,}"
    )
    return table, section


def conformance_section(
    graph: ProcessGraph,
    target_norms: dict[str, dict[str, float]],
    target_metric: TransitionMetric,
) -> str:
    """Gap analysis per metric that has norms defined."""
    normed = {k: v for k, v in target_norms.items() if v}
    if not normed:
        return ""

    ordered = sorted(graph.transitions, key=lambda t: t.occurrences, reverse=True)
    outgoing: dict[str, int] = defaultdict(int)
    for t in ordered:
        outgoing[t.fromStep] += t.occurrences

    # Current target metric first, then the rest alphabetically.
    def sort_key(key: str) -> tuple[int, str]:
        return (0 if key == target_metric.value else 1, key)

    parts: list[str] = []
    for metric_key in sorted(normed, key=sort_key):
        try:
            metric = TransitionMetric(metric_key)
        except ValueError:
            continue
        metric_norms = normed[metric_key]
        is_count_pct = metric is TransitionMetric.count

        entries = []
        for t in ordered:
            if t.fromStep == t.toStep:
                continue
            if is_count_pct:
                total_out = outgoing.get(t.fromStep) or 1
                actual = t.occurrences / total_out * 100.0
            else:
                actual = t.metric_value(metric)
                if actual is None:
                    actual = float(t.occurrences)
            norm = metric_norms.get(t.id)
            delta = None if norm is None else actual - norm
            entries.append(
                {
                    "from": t.fromStep,
                    "to": t.toStep,
                    "actual": actual,
                    "norm": norm,
                    "delta": delta,
                    "violation": None if delta is None else delta > 0,
                }
            )

        entries.sort(
            key=lambda e: (0 if e["violation"] is True else 1, -(e["delta"] or 0.0))
        )

        violations = sum(1 for e in entries if e["violation"] is True)
        compliant = sum(1 for e in entries if e["violation"] is False)
        no_norm = sum(1 for e in entries if e["norm"] is None)

        table = "| From Step | To Step | Actual | Norm | Delta | Status |\n"
        table += "|-----------|---------|--------|------|-------|--------|\n"
        for e in entries:
            act = _fmt_value(e["actual"], metric)
            nrm = _fmt_value(e["norm"], metric) if e["norm"] is not None else "—"
            dlt = _fmt_value(e["delta"], metric) if e["delta"] is not None else "—"
            if e["violation"] is None:
                status = "— No norm"
            else:
                status = "❌ VIOLATION" if e["violation"] else "✅ Compliant"
            table += f"| {e['from']} | {e['to']} | {act} | {nrm} | {dlt} | {status} |\n"

        parts.append(
            f"### {metric.value}\n\n"
            f"Summary: **{violations} violation(s)**, {compliant} compliant, "
            f"{no_norm} without norm.\n\n{table}"
        )

    return "\n\n## Conformance Check – Gap Analysis\n\n" + "\n".join(parts)


def happy_path_section(
    happy_paths: list[HappyPath], variants: list[JourneyPath]
) -> str:
    if not happy_paths:
        return (
            "\n\n## Happy Path Conformance\n\n"
            "> ⚠️ **No Happy Paths defined for this project.** "
            "Happy Path conformance could not be included in the analysis. "
            "Open the Happy Path view and define at least one ideal process sequence "
            "to measure how closely real journeys follow your intended design.\n"
        )

    qualified = [
        p for p in happy_paths if any(len(r) >= 2 for r in happy_path_routes(p.nodes))
    ]
    if not qualified:
        return ""

    rows = ""
    for path in qualified:
        score = happy_path_conformance(path, variants)
        score_str = f"{score:.2f}" if score is not None else "N/A"
        if score is None:
            rating = "— No data"
        elif score >= 0.7:
            rating = "✅  High (≥ 0.70)"
        elif score >= 0.3:
            rating = "⚠️  Moderate (0.30–0.69)"
        else:
            rating = "❌  Low (< 0.30)"
        routes = [r for r in happy_path_routes(path.nodes) if len(r) >= 2]
        routes_str = "1 (linear)" if len(routes) <= 1 else f"{len(routes)} routes"
        rows += f"| {path.name} | {routes_str} | {score_str} | {rating} |\n"

    table = (
        "| Happy Path | Routes | Conformance | Rating |\n"
        "|------------|--------|-------------|--------|\n" + rows
    )

    return (
        "\n\n## Happy Path Conformance\n\n"
        "The Conformance Score is a journey-count-weighted average of edge coverage: "
        "**1.00** = every journey follows the ideal path perfectly; "
        "**0.00** = no journey shares a single transition with the ideal sequence. "
        "A path may split into alternatives that rejoin and continue (splits can nest); "
        "each journey is scored against the route it matches best.\n\n"
        f"{table}\n"
        "| Rating thresholds | Meaning |\n"
        "|-------------------|---------|\n"
        "| ✅ High (≥ 0.70) | Most journeys closely follow the designed process |\n"
        "| ⚠️ Moderate (0.30–0.69) | Significant share of journeys deviate from the ideal |\n"
        "| ❌ Low (< 0.30) | Most journeys diverge substantially from the ideal sequence |\n"
    )


def build_prompt(
    project_title: str, template: str, graph: ProcessGraph, paths_html: str
) -> str:
    return (
        f"# Project: {project_title}\n\n"
        f"{template}\n\n"
        "**Important: Format your entire response in Markdown** "
        "(use # headers, **bold**, tables with | separators, - bullet lists, "
        "``` code blocks).\n\n"
        "## Transition Data\n\n"
        f"{transitions_table(graph)}{paths_html}\n"
    )
