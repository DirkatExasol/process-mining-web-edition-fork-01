"""Deeper-analysis queries behind the MCP power-user tools (and the lookup helpers).

Every query runs on the JOURNEYS event log through the same filter machinery as the rest
of the app (``ProcessRepository._all_filters``), so a filter means the same thing here as
in the Work Bench. Safety rules, identical to repository.py:

* caller text (step names, meta values) only ever reaches SQL through ``esc()``;
* numbers are coerced with ``int()`` / ``float()`` before interpolation;
* column names, truncation units and rule kinds come from closed maps, never from input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from ..config import QUERY_TIMEOUT_SECS
from ..models import FilterSpec
from .repository import (
    ProcessRepository,
    _clamp,
    _pid,
    as_float,
    as_int,
    clean_str,
    esc,
    parse_date,
)

META_COLUMNS: dict[str, str] = {"meta1": "META_1", "meta2": "META_2", "meta3": "META_3"}

TREND_UNITS: dict[str, str] = {
    "day": "CAST(ST AS DATE)",
    "week": "TRUNC(ST, 'IW')",
    "month": "TRUNC(ST, 'MM')",
}

RULE_KINDS = ("requires", "forbidden", "precedes", "max_duration", "max_gap")
MAX_RULES = 10


def _in_list(steps: Iterable[str]) -> str:
    return ", ".join(f"'{esc(s)}'" for s in steps)


class Analysis:
    """Read-only analysis queries. Wraps a ProcessRepository (its connection, sample set
    and filter builder); holds no state of its own."""

    def __init__(self, repo: ProcessRepository) -> None:
        self.repo = repo
        self.db = repo.db

    def _where(self, project_id: str, f: FilterSpec) -> str:
        """Row-level filter: only the events inside the date window (and matching meta)."""
        return f"PROJECT_ID = {_pid(project_id)}{self.repo._all_filters(project_id, f, date_only=True)}"

    def _where_journeys(self, project_id: str, f: FilterSpec) -> str:
        """Journey-level filter: WHOLE journeys that are active in the window (and match
        meta) — every event of each such journey, even those outside the window. Used by
        the per-journey analyses (ends, rework, trend, drivers, conformance), which would
        otherwise see journeys cut off at the window edges."""
        return f"PROJECT_ID = {_pid(project_id)}{self.repo._all_filters(project_id, f, date_only=False)}"

    async def _rows(self, sql: str) -> list:
        result = await self.db.execute(sql, timeout=QUERY_TIMEOUT_SECS)
        return list(result.rows)

    # ── attribute values ─────────────────────────────────────────────────────

    async def attribute_values(
        self, project_id: str, meta: str, f: FilterSpec, limit: int
    ) -> tuple[int, list[tuple[str, int]]]:
        """(distinct value count, [(value, journeys)] most frequent first) for one meta
        attribute. ``meta`` is a key of META_COLUMNS."""
        column = META_COLUMNS[meta]
        where = self._where(project_id, f)
        total = await self._rows(
            f"SELECT COUNT(DISTINCT {column}) FROM JOURNEYS WHERE {where} AND {column} IS NOT NULL"
        )
        rows = await self._rows(
            f"""
            SELECT {column} AS META_VAL, COUNT(DISTINCT EVENT_ID) AS J_COUNT
            FROM JOURNEYS
            WHERE {where} AND {column} IS NOT NULL
            GROUP BY {column}
            ORDER BY J_COUNT DESC, META_VAL
            LIMIT {_clamp(limit, 1, 1000)}
            """
        )
        values = [(str(r[0]), as_int(r[1])) for r in rows if r[0] is not None]
        return (as_int(total[0][0]) if total else 0), values

    # ── end steps & rework ───────────────────────────────────────────────────

    async def end_steps(self, project_id: str, f: FilterSpec, limit: int = 25) -> list[tuple[str, int]]:
        """How journeys end: the last step of each journey, counted."""
        rows = await self._rows(
            f"""
            SELECT STEP, COUNT(*) AS J_COUNT FROM (
                SELECT STEP,
                       ROW_NUMBER() OVER (PARTITION BY EVENT_ID
                                          ORDER BY EVENT_TIME DESC, STEP_ID DESC) AS RN
                FROM JOURNEYS
                WHERE {self._where_journeys(project_id, f)}
            ) x
            WHERE RN = 1
            GROUP BY STEP
            ORDER BY J_COUNT DESC, STEP
            LIMIT {_clamp(limit, 1, 1000)}
            """
        )
        return [(str(r[0]), as_int(r[1])) for r in rows if r[0] is not None]

    async def rework(self, project_id: str, f: FilterSpec, limit: int) -> list[dict[str, Any]]:
        """Steps that repeat inside a journey: how many journeys repeat them and how many
        extra visits that adds up to."""
        rows = await self._rows(
            f"""
            SELECT STEP, COUNT(*) AS J_COUNT, SUM(C - 1) AS EXTRA_VISITS FROM (
                SELECT EVENT_ID, STEP, COUNT(*) AS C
                FROM JOURNEYS
                WHERE {self._where_journeys(project_id, f)}
                GROUP BY EVENT_ID, STEP
                HAVING COUNT(*) > 1
            ) r
            GROUP BY STEP
            ORDER BY EXTRA_VISITS DESC, STEP
            LIMIT {_clamp(limit, 1, 1000)}
            """
        )
        return [
            {"step": str(r[0]), "journeys": as_int(r[1]), "extraVisits": as_int(r[2])}
            for r in rows if r[0] is not None
        ]

    # ── trend ────────────────────────────────────────────────────────────────

    async def trend(
        self, project_id: str, f: FilterSpec, unit: str, outcome_steps: list[str], limit: int
    ) -> list[dict[str, Any]]:
        """Per period (by journey START): journeys, average and median duration, and — if
        outcome steps are given — how many journeys reached one of them."""
        trunc = TREND_UNITS[unit]
        hit = (
            f"MAX(CASE WHEN STEP IN ({_in_list(outcome_steps)}) THEN 1 ELSE 0 END)"
            if outcome_steps else "0"
        )
        rows = await self._rows(
            f"""
            WITH pj AS (
                SELECT EVENT_ID, MIN(EVENT_TIME) AS ST, MAX(EVENT_TIME) AS EN, {hit} AS HIT
                FROM JOURNEYS
                WHERE {self._where_journeys(project_id, f)}
                GROUP BY EVENT_ID
            )
            SELECT {trunc} AS PERIOD_START,
                   COUNT(*) AS J_COUNT,
                   AVG(SECONDS_BETWEEN(EN, ST)) AS AVG_SECS,
                   MEDIAN(SECONDS_BETWEEN(EN, ST)) AS MEDIAN_SECS,
                   SUM(HIT) AS HITS
            FROM pj
            GROUP BY {trunc}
            ORDER BY PERIOD_START DESC
            LIMIT {_clamp(limit, 1, 1000)}
            """
        )
        out = []
        # Newest-first + LIMIT keeps the most RECENT periods when capped; present them
        # oldest-first.
        for r in reversed(rows):
            period = parse_date(r[0])
            if period is None:
                continue
            n = as_int(r[1])
            point: dict[str, Any] = {
                "period": period.date().isoformat(),
                "journeys": n,
                "avgDurationSecs": as_float(r[2]),
                "medianDurationSecs": as_float(r[3]),
            }
            if outcome_steps:
                hits = as_int(r[4])
                point["outcomeJourneys"] = hits
                point["outcomeRate"] = round(hits / n, 4) if n else None
            out.append(point)
        return out

    # ── outcome drivers ──────────────────────────────────────────────────────

    async def outcome_drivers(
        self, project_id: str, f: FilterSpec, outcome_steps: list[str], min_support: int
    ) -> dict[str, Any]:
        """Journeys reaching any outcome step, overall and broken down by each meta value
        and by each (other) step the journey visited."""
        where = self._where_journeys(project_id, f)
        outcome = _in_list(outcome_steps)
        min_support = _clamp(min_support, 1, 10_000_000)
        pj = f"""
            pj AS (
                SELECT EVENT_ID,
                       MAX(CASE WHEN STEP IN ({outcome}) THEN 1 ELSE 0 END) AS HIT,
                       MAX(META_1) AS M1, MAX(META_2) AS M2, MAX(META_3) AS M3
                FROM JOURNEYS
                WHERE {where}
                GROUP BY EVENT_ID
            )"""
        overall = await self._rows(f"WITH {pj} SELECT COUNT(*), SUM(HIT) FROM pj")
        total = as_int(overall[0][0]) if overall else 0
        hits = as_int(overall[0][1]) if overall else 0

        meta_rows = await self._rows(
            f"""
            WITH {pj}
            SELECT 'meta1' AS META_COL, M1 AS META_VAL, COUNT(*) AS N, SUM(HIT) AS H
              FROM pj WHERE M1 IS NOT NULL GROUP BY M1 HAVING COUNT(*) >= {min_support}
            UNION ALL
            SELECT 'meta2', M2, COUNT(*), SUM(HIT)
              FROM pj WHERE M2 IS NOT NULL GROUP BY M2 HAVING COUNT(*) >= {min_support}
            UNION ALL
            SELECT 'meta3', M3, COUNT(*), SUM(HIT)
              FROM pj WHERE M3 IS NOT NULL GROUP BY M3 HAVING COUNT(*) >= {min_support}
            """
        )
        step_rows = await self._rows(
            f"""
            WITH {pj},
            js AS (
                SELECT DISTINCT EVENT_ID, STEP FROM JOURNEYS WHERE {where}
            )
            SELECT js.STEP, COUNT(*) AS N, SUM(pj.HIT) AS H
            FROM js JOIN pj ON js.EVENT_ID = pj.EVENT_ID
            WHERE js.STEP NOT IN ({outcome})
            GROUP BY js.STEP
            HAVING COUNT(*) >= {min_support}
            """
        )
        return {
            "total": total,
            "hits": hits,
            "meta": [(str(r[0]), clean_str(r[1]) or "", as_int(r[2]), as_int(r[3])) for r in meta_rows],
            "steps": [(str(r[0]), as_int(r[1]), as_int(r[2])) for r in step_rows if r[0] is not None],
        }

    # ── conformance ──────────────────────────────────────────────────────────

    async def conformance(
        self, project_id: str, f: FilterSpec, rules: list["Rule"], examples: int
    ) -> tuple[int, list[tuple[int, list[str]]]]:
        """(journeys checked, [(violations, example eventIds)] per rule)."""
        where = self._where_journeys(project_id, f)
        flags = ",\n                   ".join(
            f"CASE WHEN {rule.violation_sql()} THEN 1 ELSE 0 END AS V{i}"
            for i, rule in enumerate(rules)
        )
        pj = f"""
            pj AS (
                SELECT EVENT_ID,
                   {flags}
                FROM JOURNEYS
                WHERE {where}
                GROUP BY EVENT_ID
            )"""
        sums = ", ".join(f"SUM(V{i})" for i in range(len(rules)))
        counts = await self._rows(f"WITH {pj} SELECT COUNT(*), {sums} FROM pj")
        row = counts[0] if counts else [0] * (len(rules) + 1)
        checked = as_int(row[0])
        out: list[tuple[int, list[str]]] = []
        for i in range(len(rules)):
            n = as_int(row[i + 1])
            ids: list[str] = []
            if n and examples:
                ex = await self._rows(
                    f"WITH {pj} SELECT EVENT_ID FROM pj WHERE V{i} = 1 "
                    f"ORDER BY EVENT_ID LIMIT {_clamp(examples, 1, 100)}"
                )
                ids = [str(r[0]) for r in ex if r[0] is not None]
            out.append((n, ids))
        return checked, out

    # ── find a case anywhere ─────────────────────────────────────────────────

    async def journey_lookup(self, project_id: str, stored_id: str) -> dict[str, Any] | None:
        rows = await self._rows(
            f"""
            SELECT MIN(EVENT_TIME), MAX(EVENT_TIME), COUNT(*)
            FROM JOURNEYS
            WHERE PROJECT_ID = {_pid(project_id)}
            AND {self.repo.active_sample_set.sql_fragment()}
            AND EVENT_ID = '{esc(stored_id)}'
            """
        )
        if not rows or rows[0][0] is None:
            return None
        start, end = parse_date(rows[0][0]), parse_date(rows[0][1])
        return {
            "startDate": start,
            "endDate": end,
            "durationSecs": (end - start).total_seconds() if start and end else None,
            "stepCount": as_int(rows[0][2]),
        }


# ── conformance rules ──────────────────────────────────────────────────────────


def _first(step: str) -> str:
    return f"MIN(CASE WHEN STEP = '{esc(step)}' THEN EVENT_TIME END)"


def _has(step: str) -> str:
    return f"MAX(CASE WHEN STEP = '{esc(step)}' THEN 1 ELSE 0 END)"


@dataclass
class Rule:
    """One conformance rule. Built only through ``Rule.parse`` (validated input)."""

    kind: str
    step: str = ""
    if_step: str = ""
    before: str = ""
    after: str = ""
    from_step: str = ""
    to_step: str = ""
    max_secs: float = 0.0

    @staticmethod
    def parse(raw: Any, *, step_max: int = 2000) -> "Rule":
        if not isinstance(raw, dict):
            raise ValueError("each rule must be an object")
        kind = str(raw.get("type") or "").strip().lower()
        if kind not in RULE_KINDS:
            raise ValueError(f"unknown rule type {raw.get('type')!r}; expected one of {', '.join(RULE_KINDS)}")

        def step(key: str, required: bool = True) -> str:
            val = raw.get(key)
            if val is None or val == "":
                if required:
                    raise ValueError(f"a '{kind}' rule needs '{key}'")
                return ""
            if not isinstance(val, str) or len(val) > step_max:
                raise ValueError(f"'{key}' must be a step name (a string up to {step_max} characters)")
            return val

        def secs() -> float:
            try:
                val = float(raw.get("maxSecs"))
            except (TypeError, ValueError):
                raise ValueError(f"a '{kind}' rule needs a numeric 'maxSecs'") from None
            if not (0 <= val <= 10 * 365 * 86400):
                raise ValueError("'maxSecs' must be between 0 and ten years")
            return val

        if kind == "requires":
            return Rule(kind, step=step("step"), if_step=step("ifStep", required=False))
        if kind == "forbidden":
            return Rule(kind, step=step("step"))
        if kind == "precedes":
            return Rule(kind, before=step("before"), after=step("after"))
        if kind == "max_duration":
            return Rule(kind, max_secs=secs())
        return Rule(kind, from_step=step("fromStep"), to_step=step("toStep"), max_secs=secs())

    def steps(self) -> list[str]:
        return [s for s in (self.step, self.if_step, self.before, self.after,
                            self.from_step, self.to_step) if s]

    def violation_sql(self) -> str:
        if self.kind == "requires":
            cond = f"{_has(self.step)} = 0"
            return f"{_has(self.if_step)} = 1 AND {cond}" if self.if_step else cond
        if self.kind == "forbidden":
            return f"{_has(self.step)} = 1"
        if self.kind == "precedes":
            return (f"{_has(self.after)} = 1 AND ({_has(self.before)} = 0 "
                    f"OR {_first(self.before)} > {_first(self.after)})")
        if self.kind == "max_duration":
            return f"SECONDS_BETWEEN(MAX(EVENT_TIME), MIN(EVENT_TIME)) > {float(self.max_secs)}"
        # max_gap: both present, 'to' first seen at/after 'from', and too long between them
        return (f"{_has(self.from_step)} = 1 AND {_has(self.to_step)} = 1 "
                f"AND {_first(self.to_step)} >= {_first(self.from_step)} "
                f"AND SECONDS_BETWEEN({_first(self.to_step)}, {_first(self.from_step)}) "
                f"> {float(self.max_secs)}")

    def describe(self) -> str:
        if self.kind == "requires":
            return (f"Journeys that visit '{self.if_step}' must also visit '{self.step}'"
                    if self.if_step else f"Every journey must visit '{self.step}'")
        if self.kind == "forbidden":
            return f"No journey may visit '{self.step}'"
        if self.kind == "precedes":
            return f"'{self.before}' must happen before '{self.after}'"
        if self.kind == "max_duration":
            return f"A journey may last at most {self.max_secs:g} s"
        return f"'{self.to_step}' must follow '{self.from_step}' within {self.max_secs:g} s"
