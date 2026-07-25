"""All Exasol SQL — the port of ProcessRepository.swift.

The queries are kept character-for-character equivalent to the Swift originals so
results, edge cases and performance characteristics carry over unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from ..config import QUERY_TIMEOUT_SECS
from ..models import (
    INT_MAX,
    INT_MIN,
    DurationBucket,
    DurationStats,
    FilterSnapshot,
    FilterSpec,
    JourneyPath,
    JourneyTimePoint,
    NoteTarget,
    ProcessGraph,
    ProcessNote,
    ProcessTransition,
    Project,
    SampleSet,
    StepInfo,
    TimeGranularity,
    new_id,
)
from .manager import DatabaseManager

log = logging.getLogger(__name__)

_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def esc(value: str) -> str:
    """Escape a SQL string literal the way the Swift app did."""
    return value.replace("'", "''")


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, Decimal)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    return str(value).strip().lower() in {"true", "t", "1", "yes"}


def parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def clean_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _ts(when: datetime) -> str:
    """Millisecond-precision timestamp literal, as written by the Swift app."""
    return when.strftime("%Y-%m-%d %H:%M:%S.") + f"{when.microsecond // 1000:03d}"


def dur_label(secs: float) -> str:
    """Bucket-boundary label — matches ProcessRepository.durLabel."""
    if secs < 60:
        return f"{round(secs)}s"
    if secs < 3600:
        minutes = secs / 60
        return f"{minutes:.1f}m" if minutes < 10 else f"{round(minutes)}m"
    if secs < 86400:
        hours = secs / 3600
        return f"{hours:.1f}h" if hours < 10 else f"{round(hours)}h"
    days = secs / 86400
    return f"{days:.1f}d" if days < 10 else f"{round(days)}d"


class ProcessRepository:
    def __init__(self, manager: DatabaseManager) -> None:
        self.db = manager
        self.active_sample_set: SampleSet = SampleSet.original

    # ── clause builders (private helpers in the Swift original) ──────────────

    def _sample_clause(self, alias: str | None = None) -> str:
        return f"\n                AND {self.active_sample_set.sql_fragment(alias)}"

    def _date_clause(self, frm: datetime | None, to: datetime | None) -> str:
        if frm is None and to is None:
            return ""
        parts: list[str] = []
        if frm is not None:
            parts.append(f"AND EVENT_TIME >= TIMESTAMP '{frm:%Y-%m-%d} 00:00:00'")
        if to is not None:
            parts.append(f"AND EVENT_TIME <= TIMESTAMP '{to:%Y-%m-%d} 23:59:59'")
        return "\n                " + "\n                ".join(parts)

    def _meta_clause(self, meta1: str, meta2: str, meta3: str) -> str:
        parts: list[str] = []
        for column, value in (("META_1", meta1), ("META_2", meta2), ("META_3", meta3)):
            if value:
                parts.append(f"AND UPPER({column}) LIKE UPPER('%{esc(value)}%')")
        if not parts:
            return ""
        return "\n                " + "\n                ".join(parts)

    def _journey_activity_filter(
        self,
        frm: datetime | None,
        to: datetime | None,
        project_id: str,
        meta1: str,
        meta2: str,
        meta3: str,
    ) -> str:
        """Selects EVENT_IDs active in the window so LEAD() still sees every step
        of a qualifying journey — cross-day transitions are never dropped."""
        if frm is None and to is None and not (meta1 or meta2 or meta3):
            return ""
        parts = [f"PROJECT_ID = '{project_id}'", self.active_sample_set.sql_fragment()]
        if frm is not None:
            parts.append(f"EVENT_TIME >= TIMESTAMP '{frm:%Y-%m-%d} 00:00:00'")
        if to is not None:
            parts.append(f"EVENT_TIME <= TIMESTAMP '{to:%Y-%m-%d} 23:59:59'")
        for column, value in (("META_1", meta1), ("META_2", meta2), ("META_3", meta3)):
            if value:
                parts.append(f"UPPER({column}) LIKE UPPER('%{esc(value)}%')")
        joined = " AND ".join(parts)
        return (
            "\n                AND EVENT_ID IN "
            f"(SELECT DISTINCT EVENT_ID FROM JOURNEYS WHERE {joined})"
        )

    def _step_clause(
        self, included: Iterable[str], excluded: Iterable[str], project_id: str
    ) -> str:
        def in_list(steps: Iterable[str]) -> str:
            return ", ".join(f"'{esc(s)}'" for s in steps)

        included = list(included)
        excluded = list(excluded)
        parts: list[str] = []
        frag = self.active_sample_set.sql_fragment()
        if included:
            parts.append(
                "AND EVENT_ID IN (SELECT DISTINCT EVENT_ID FROM JOURNEYS WHERE "
                f"PROJECT_ID = '{project_id}' AND {frag} "
                f"AND STEP IN ({in_list(included)}))"
            )
        if excluded:
            parts.append(
                "AND EVENT_ID NOT IN (SELECT DISTINCT EVENT_ID FROM JOURNEYS WHERE "
                f"PROJECT_ID = '{project_id}' AND {frag} "
                f"AND STEP IN ({in_list(excluded)}))"
            )
        if not parts:
            return ""
        return "\n                " + "\n                ".join(parts)

    def _steps_count_clause(self, minimum: int, maximum: int, project_id: str) -> str:
        if minimum <= 0 and maximum >= INT_MAX:
            return ""
        if minimum > 0 and maximum < INT_MAX:
            having = f"HAVING COUNT(*) BETWEEN {minimum} AND {maximum}"
        elif minimum > 0:
            having = f"HAVING COUNT(*) >= {minimum}"
        else:
            having = f"HAVING COUNT(*) <= {maximum}"
        return (
            "\n                AND EVENT_ID IN (SELECT EVENT_ID FROM JOURNEYS WHERE "
            f"PROJECT_ID = '{project_id}' AND {self.active_sample_set.sql_fragment()} "
            f"GROUP BY EVENT_ID {having})"
        )

    def _journey_time_clause(self, min_secs: int, max_secs: int, project_id: str) -> str:
        if min_secs <= 0 and max_secs >= INT_MAX:
            return ""
        expr = "SECONDS_BETWEEN(MAX(EVENT_TIME), MIN(EVENT_TIME))"
        if min_secs > 0 and max_secs < INT_MAX:
            having = f"HAVING {expr} BETWEEN {min_secs} AND {max_secs}"
        elif min_secs > 0:
            having = f"HAVING {expr} >= {min_secs}"
        else:
            having = f"HAVING {expr} <= {max_secs}"
        return (
            "\n                AND EVENT_ID IN (SELECT EVENT_ID FROM JOURNEYS WHERE "
            f"PROJECT_ID = '{project_id}' AND {self.active_sample_set.sql_fragment()} "
            f"GROUP BY EVENT_ID {having})"
        )

    def _score_clause(self, minimum: int, maximum: int, project_id: str) -> str:
        if minimum <= INT_MIN and maximum >= INT_MAX:
            return ""
        return (
            "\n                AND EVENT_ID IN (SELECT j.EVENT_ID FROM JOURNEYS j "
            "LEFT JOIN STEPS s ON j.STEP = s.STEP AND j.PROJECT_ID = s.PROJECT_ID "
            f"WHERE j.PROJECT_ID = '{project_id}' "
            f"AND {self.active_sample_set.sql_fragment('j')} "
            f"GROUP BY j.EVENT_ID HAVING SUM(COALESCE(s.SCORE, 0)) "
            f"BETWEEN {minimum} AND {maximum})"
        )

    def _all_filters(self, project_id: str, f: FilterSpec, *, date_only: bool) -> str:
        """`date_only=True` uses the plain date clause (row-level); `False` uses the
        journey-activity subquery required by the LEAD()-based transition query."""
        safe = esc(project_id)
        clauses = self._sample_clause()
        if date_only:
            clauses += self._date_clause(f.fromDate, f.toDate)
            clauses += self._step_clause(f.includedSteps, f.excludedSteps, safe)
            clauses += self._meta_clause(f.meta1, f.meta2, f.meta3)
        else:
            clauses += self._journey_activity_filter(
                f.fromDate, f.toDate, safe, f.meta1, f.meta2, f.meta3
            )
            clauses += self._step_clause(f.includedSteps, f.excludedSteps, safe)
        clauses += self._steps_count_clause(f.minSteps, f.maxSteps, safe)
        clauses += self._journey_time_clause(f.minJourneyTime, f.maxJourneyTime, safe)
        clauses += self._score_clause(f.minScore, f.maxScore, safe)
        return clauses

    # ── projects, steps, metas ───────────────────────────────────────────────

    async def load_projects(self) -> list[Project]:
        result = await self.db.execute(
            "SELECT PROJECT_ID, TITLE, DESCRIPTION FROM PROJECTS ORDER BY TITLE"
        )
        projects: list[Project] = []
        for row in result.rows:
            if not isinstance(row[0], str) or not isinstance(row[1], str):
                continue
            projects.append(
                Project(
                    projectId=row[0],
                    title=row[1],
                    description=row[2] if isinstance(row[2], str) else "",
                )
            )
        return projects

    async def load_steps(self, project_id: str) -> dict[str, StepInfo]:
        result = await self.db.execute(
            f"""
            SELECT STEP, DESCRIPTION, BG_COLOR, FG_COLOR, SCORE, SHAPE, END_OF_PROCESS, BELONGS_TO
            FROM STEPS
            WHERE PROJECT_ID = '{esc(project_id)}'
            """
        )
        steps: dict[str, StepInfo] = {}
        for row in result.rows:
            step = row[0]
            if not isinstance(step, str):
                continue
            score = None if row[4] is None else as_int(row[4])
            steps[step] = StepInfo(
                step=step,
                description=row[1] if isinstance(row[1], str) else step,
                bgColor=row[2] if isinstance(row[2], str) else "blue",
                fgColor=row[3] if isinstance(row[3], str) else "white",
                score=score,
                shape=row[5] if isinstance(row[5], str) else "stadium",
                endOfProcess=as_bool(row[6]),
                belongsTo=row[7] if len(row) > 7 and isinstance(row[7], str) else None,
            )
        return steps

    async def update_step(
        self,
        project_id: str,
        step: str,
        *,
        bg_color: str,
        fg_color: str,
        score: int | None,
        shape: str,
        belongs_to: str | None,
        description: str | None,
    ) -> None:
        score_sql = f"SCORE = {score}" if score is not None else "SCORE = NULL"
        belongs_sql = (
            f"BELONGS_TO = '{esc(belongs_to)}'" if belongs_to else "BELONGS_TO = NULL"
        )
        desc_sql = (
            f"DESCRIPTION = '{esc(description)}'"
            if description is not None
            else "DESCRIPTION = DESCRIPTION"
        )
        await self.db.execute(
            f"""
            UPDATE STEPS
            SET BG_COLOR = '{esc(bg_color)}',
                FG_COLOR = '{esc(fg_color)}',
                {score_sql},
                SHAPE = '{esc(shape)}',
                {belongs_sql},
                {desc_sql}
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND STEP = '{esc(step)}'
            """
        )

    async def load_meta_titles(self, project_id: str) -> tuple[str | None, str | None, str | None]:
        result = await self.db.execute(
            f"""
            SELECT META_1_TITLE, META_2_TITLE, META_3_TITLE
            FROM METAS
            WHERE PROJECT_ID = '{esc(project_id)}'
            """
        )
        if not result.rows:
            return (None, None, None)
        row = result.rows[0]
        return (clean_str(row[0]), clean_str(row[1]), clean_str(row[2]))

    async def load_meta_values(self, project_id: str, column: str) -> list[str]:
        if column not in {"META_1", "META_2", "META_3"}:
            raise ValueError(f"unsupported meta column {column!r}")
        result = await self.db.execute(
            f"""
            SELECT DISTINCT {column}
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND {self.active_sample_set.sql_fragment()}
            AND {column} IS NOT NULL
            ORDER BY {column}
            """
        )
        return [r[0] for r in result.rows if isinstance(r[0], str)]

    async def load_all_step_names(self, project_id: str) -> list[str]:
        result = await self.db.execute(
            "SELECT DISTINCT STEP FROM JOURNEYS "
            f"WHERE PROJECT_ID = '{esc(project_id)}' "
            f"AND {self.active_sample_set.sql_fragment()} ORDER BY STEP"
        )
        return [r[0] for r in result.rows if isinstance(r[0], str)]

    # ── bounds ───────────────────────────────────────────────────────────────

    async def load_date_bounds(
        self, project_id: str
    ) -> tuple[datetime | None, datetime | None]:
        result = await self.db.execute(
            "SELECT MIN(EVENT_TIME), MAX(EVENT_TIME) FROM JOURNEYS "
            f"WHERE PROJECT_ID = '{esc(project_id)}' "
            f"AND {self.active_sample_set.sql_fragment()}"
        )
        if not result.rows:
            return (None, None)
        row = result.rows[0]
        return (parse_date(row[0]), parse_date(row[1]))

    async def load_journey_time_bounds(self, project_id: str) -> tuple[int, int]:
        result = await self.db.execute(
            f"""
            SELECT MIN(dur), MAX(dur)
            FROM (
                SELECT SECONDS_BETWEEN(MAX(EVENT_TIME), MIN(EVENT_TIME)) AS dur
                FROM JOURNEYS
                WHERE PROJECT_ID = '{esc(project_id)}'
                AND {self.active_sample_set.sql_fragment()}
                GROUP BY EVENT_ID
            ) AS j
            """
        )
        if not result.rows:
            return (0, 0)
        row = result.rows[0]
        return (max(0, as_int(row[0])), max(0, as_int(row[1])))

    async def load_step_count_bounds(self, project_id: str) -> tuple[int, int]:
        result = await self.db.execute(
            f"""
            SELECT MIN(cnt), MAX(cnt)
            FROM (
                SELECT COUNT(*) AS cnt
                FROM JOURNEYS
                WHERE PROJECT_ID = '{esc(project_id)}'
                AND {self.active_sample_set.sql_fragment()}
                GROUP BY EVENT_ID
            ) AS j
            """
        )
        if not result.rows:
            return (1, 1)
        row = result.rows[0]
        return (as_int(row[0], 1), as_int(row[1], 1))

    async def load_score_bounds(self, project_id: str) -> tuple[int, int]:
        result = await self.db.execute(
            f"""
            SELECT MIN(journey_score), MAX(journey_score)
            FROM (
                SELECT j.EVENT_ID, SUM(COALESCE(s.SCORE, 0)) AS journey_score
                FROM JOURNEYS j
                LEFT JOIN STEPS s ON j.STEP = s.STEP AND j.PROJECT_ID = s.PROJECT_ID
                WHERE j.PROJECT_ID = '{esc(project_id)}'
                AND {self.active_sample_set.sql_fragment('j')}
                GROUP BY j.EVENT_ID
            ) AS scored
            """
        )
        if not result.rows:
            return (0, 0)
        row = result.rows[0]
        return (as_int(row[0]), as_int(row[1]))

    async def find_nearest_day_with_data(
        self, day: datetime, project_id: str
    ) -> datetime | None:
        safe = esc(project_id)
        frag = self.active_sample_set.sql_fragment()
        start_of_day = datetime(day.year, day.month, day.day)
        next_day = start_of_day + timedelta(days=1)

        forward = await self.db.execute(
            f"SELECT MIN(EVENT_TIME) FROM JOURNEYS WHERE PROJECT_ID = '{safe}' "
            f"AND {frag} AND EVENT_TIME >= '{next_day:%Y-%m-%d}'"
        )
        if forward.rows and (found := parse_date(forward.rows[0][0])):
            return datetime(found.year, found.month, found.day)

        backward = await self.db.execute(
            f"SELECT MAX(EVENT_TIME) FROM JOURNEYS WHERE PROJECT_ID = '{safe}' "
            f"AND {frag} AND EVENT_TIME < '{start_of_day:%Y-%m-%d}'"
        )
        if backward.rows and (found := parse_date(backward.rows[0][0])):
            return datetime(found.year, found.month, found.day)
        return None

    # ── counts, transitions, graph ───────────────────────────────────────────

    async def load_journey_count(self, project_id: str, f: FilterSpec) -> int:
        filters = self._all_filters(project_id, f, date_only=True)
        result = await self.db.execute(
            f"""
            SELECT COUNT(DISTINCT EVENT_ID)
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'{filters}
            """
        )
        if not result.rows:
            return 0
        return as_int(result.rows[0][0])

    async def load_transitions(
        self, project_id: str, f: FilterSpec
    ) -> list[ProcessTransition]:
        filters = self._all_filters(project_id, f, date_only=False)
        result = await self.db.execute(
            f"""
            SELECT FROM_STEP, TO_STEP, COUNT(*) AS CNT,
                   AVG(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS AVG_SECS,
                   MIN(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS MIN_SECS,
                   MAX(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS MAX_SECS,
                   STDDEV(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS STDDEV_SECS
            FROM (
                SELECT
                    STEP       AS FROM_STEP,
                    EVENT_TIME AS FROM_TIME,
                    LEAD(STEP)       OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_STEP,
                    LEAD(EVENT_TIME) OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_TIME
                FROM JOURNEYS
                WHERE PROJECT_ID = '{esc(project_id)}'{filters}
            ) AS t
            WHERE TO_STEP IS NOT NULL AND TO_TIME IS NOT NULL
            GROUP BY FROM_STEP, TO_STEP
            ORDER BY CNT DESC
            """
        )
        return self._rows_to_transitions(result.rows)

    @staticmethod
    def _rows_to_transitions(rows: list[list[Any]]) -> list[ProcessTransition]:
        transitions: list[ProcessTransition] = []
        for row in rows:
            if not isinstance(row[0], str) or not isinstance(row[1], str):
                continue
            if row[2] is None:
                continue
            transitions.append(
                ProcessTransition(
                    fromStep=row[0],
                    toStep=row[1],
                    occurrences=as_int(row[2]),
                    avgSecs=as_float(row[3]),
                    minSecs=as_float(row[4]),
                    maxSecs=as_float(row[5]),
                    stdDevSecs=as_float(row[6]),
                )
            )
        return transitions

    @staticmethod
    def _assemble_graph(
        steps: dict[str, StepInfo], transitions: list[ProcessTransition]
    ) -> ProcessGraph:
        referenced = {t.fromStep for t in transitions} | {t.toStep for t in transitions}
        pruned = {name: info for name, info in steps.items() if name in referenced}
        for node in referenced:
            if node not in pruned:
                pruned[node] = StepInfo(
                    step=node,
                    description=node,
                    bgColor="gray",
                    fgColor="white",
                    shape="stadium",
                )
        return ProcessGraph(steps=pruned, transitions=transitions)

    async def load_graph(self, project_id: str, f: FilterSpec) -> ProcessGraph:
        steps = await self.load_steps(project_id)
        transitions = await self.load_transitions(project_id, f)
        return self._assemble_graph(steps, transitions)

    async def load_journey_duration_stats(
        self, project_id: str, f: FilterSpec
    ) -> DurationStats:
        filters = self._all_filters(project_id, f, date_only=True)
        result = await self.db.execute(
            f"""
            SELECT
                MIN(SECONDS_BETWEEN(MAX_TIME, MIN_TIME)) AS MIN_SECS,
                AVG(SECONDS_BETWEEN(MAX_TIME, MIN_TIME)) AS AVG_SECS,
                MAX(SECONDS_BETWEEN(MAX_TIME, MIN_TIME)) AS MAX_SECS,
                STDDEV(SECONDS_BETWEEN(MAX_TIME, MIN_TIME)) AS STDDEV_SECS
            FROM (
                SELECT EVENT_ID,
                       MIN(EVENT_TIME) AS MIN_TIME,
                       MAX(EVENT_TIME) AS MAX_TIME
                FROM JOURNEYS
                WHERE PROJECT_ID = '{esc(project_id)}'{filters}
                GROUP BY EVENT_ID
            ) AS j
            """
        )
        if not result.rows:
            return DurationStats()
        row = result.rows[0]
        return DurationStats(
            minSecs=as_float(row[0]),
            avgSecs=as_float(row[1]),
            maxSecs=as_float(row[2]),
            stdDevSecs=as_float(row[3]),
        )

    async def load_duration_buckets(
        self, project_id: str, f: FilterSpec, bin_count: int = 10
    ) -> list[DurationBucket]:
        filters = self._all_filters(project_id, f, date_only=True)
        safe = esc(project_id)
        n = bin_count
        sql = f"""
            SELECT bin_idx, COUNT(*) AS cnt, MIN(min_dur) AS min_dur, MIN(max_dur) AS max_dur
            FROM (
                SELECT
                    CASE
                        WHEN r.max_dur = r.min_dur THEN 0
                        ELSE LEAST(FLOOR((d.dur - r.min_dur) / (r.max_dur - r.min_dur) * {n}), {n - 1})
                    END AS bin_idx,
                    r.min_dur,
                    r.max_dur
                FROM (
                    SELECT EVENT_ID, SECONDS_BETWEEN(MAX(EVENT_TIME), MIN(EVENT_TIME)) AS dur
                    FROM JOURNEYS
                    WHERE PROJECT_ID = '{safe}'{filters}
                    GROUP BY EVENT_ID
                ) d,
                (
                    SELECT MIN(dur) AS min_dur, MAX(dur) AS max_dur
                    FROM (
                        SELECT EVENT_ID, SECONDS_BETWEEN(MAX(EVENT_TIME), MIN(EVENT_TIME)) AS dur
                        FROM JOURNEYS
                        WHERE PROJECT_ID = '{safe}'{filters}
                        GROUP BY EVENT_ID
                    ) d2
                ) r
            ) binned
            GROUP BY bin_idx
            ORDER BY bin_idx
            """
        result = await self.db.execute(sql)
        if not result.rows:
            return []

        min_dur = as_float(result.rows[0][2]) or 0.0
        max_dur = as_float(result.rows[0][3]) or 0.0
        bin_width = (max_dur - min_dur) / n if max_dur > min_dur else max(max_dur, 1.0)

        buckets: list[DurationBucket] = []
        for row in result.rows:
            idx = as_int(row[0])
            low = min_dur + idx * bin_width
            high = low + bin_width
            buckets.append(
                DurationBucket(
                    label=f"{dur_label(low)}–{dur_label(high)}", count=as_int(row[1])
                )
            )
        return buckets

    async def load_journey_time_series(
        self, project_id: str, f: FilterSpec, granularity: TimeGranularity
    ) -> list[JourneyTimePoint]:
        filters = self._all_filters(project_id, f, date_only=True)
        trunc = {
            TimeGranularity.day: "CAST(EVENT_TIME AS DATE)",
            TimeGranularity.week: "TRUNC(EVENT_TIME, 'IW')",
            TimeGranularity.month: "TRUNC(EVENT_TIME, 'MM')",
        }[granularity]
        result = await self.db.execute(
            f"""
            SELECT {trunc} AS period, COUNT(DISTINCT EVENT_ID) AS cnt
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'{filters}
            GROUP BY {trunc}
            ORDER BY {trunc}
            """
        )
        points: list[JourneyTimePoint] = []
        for row in result.rows:
            when = parse_date(row[0])
            if when is None:
                continue
            points.append(JourneyTimePoint(date=when, count=as_int(row[1])))
        return points

    # ── variants & goodness ──────────────────────────────────────────────────

    async def load_journey_paths(
        self, project_id: str, f: FilterSpec, limit: int = 500
    ) -> list[JourneyPath]:
        filters = self._all_filters(project_id, f, date_only=True)
        sql = f"""
            WITH ordered_paths AS (
                SELECT
                    j.EVENT_ID,
                    LISTAGG(j.STEP, ' -> ') WITHIN GROUP (ORDER BY j.EVENT_TIME ASC) AS full_path,
                    COUNT(j.STEP)             AS path_length,
                    SUM(COALESCE(s.SCORE, 0)) AS score
                FROM JOURNEYS j
                LEFT JOIN STEPS s ON j.STEP = s.STEP AND j.PROJECT_ID = s.PROJECT_ID
                WHERE j.PROJECT_ID = '{esc(project_id)}'{filters}
                GROUP BY j.EVENT_ID
            ),
            distinct_paths AS (
                SELECT
                    full_path,
                    path_length,
                    score,
                    COUNT(*) AS journey_count
                FROM ordered_paths
                GROUP BY full_path, path_length, score
            )
            SELECT
                full_path,
                journey_count,
                path_length,
                score
            FROM distinct_paths
            ORDER BY journey_count DESC
            LIMIT {limit}
            """
        try:
            result = await self.db.execute(sql, timeout=QUERY_TIMEOUT_SECS)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"Statistics query timed out ({QUERY_TIMEOUT_SECS:.0f} s). "
                "Narrow your date range or filters and try again."
            ) from exc

        paths: list[JourneyPath] = []
        for row in result.rows:
            if not isinstance(row[0], str):
                continue
            paths.append(
                JourneyPath(
                    path=row[0],
                    journeyCount=as_int(row[1]),
                    stepCount=as_int(row[2]),
                    totalScore=as_int(row[3]),
                )
            )
        return paths

    async def load_process_goodness(
        self, project_id: str, f: FilterSpec
    ) -> tuple[float, int] | None:
        """Returns (rawGoodness, filteredCount); the caller applies the coverage
        penalty `raw * (filtered / total) ** 0.5`."""
        filters = self._all_filters(project_id, f, date_only=True)
        sql = f"""
            WITH ordered_paths AS (
                SELECT
                    j.EVENT_ID,
                    LISTAGG(j.STEP, ' -> ') WITHIN GROUP (ORDER BY j.EVENT_TIME ASC) AS full_path,
                    COUNT(j.STEP)                                                      AS path_length,
                    SUM(COALESCE(s.SCORE, 0))                                          AS total_score,
                    COALESCE(SECONDS_BETWEEN(MAX(j.EVENT_TIME), MIN(j.EVENT_TIME)), 0) AS journey_duration
                FROM JOURNEYS j
                LEFT JOIN STEPS s ON j.STEP = s.STEP AND j.PROJECT_ID = s.PROJECT_ID
                WHERE j.PROJECT_ID = '{esc(project_id)}'{filters}
                GROUP BY j.EVENT_ID
            ),
            distinct_paths AS (
                SELECT
                    path_length,
                    total_score,
                    COUNT(*)              AS journey_count,
                    AVG(journey_duration) AS avg_duration
                FROM ordered_paths
                GROUP BY full_path, path_length, total_score
            ),
            totals AS (
                SELECT SUM(journey_count) AS total_freq FROM distinct_paths
            )
            SELECT
                SUM(
                    (CAST(dp.journey_count AS DOUBLE) / CAST(t.total_freq AS DOUBLE)) *
                    (CAST(dp.total_score   AS DOUBLE) / SQRT(CAST(GREATEST(dp.path_length, 1) AS DOUBLE)) -
                     0.01 * dp.avg_duration)
                ) AS raw_goodness,
                t.total_freq AS filtered_count
            FROM distinct_paths dp, totals t
            GROUP BY t.total_freq
            """
        try:
            result = await self.db.execute(sql, timeout=QUERY_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            return None
        if not result.rows:
            return None
        raw = as_float(result.rows[0][0])
        if raw is None:
            return None
        return (raw, as_int(result.rows[0][1]))

    # ── individual journeys ──────────────────────────────────────────────────

    async def load_event_id_suggestions(
        self, project_id: str, prefix: str, limit: int = 10
    ) -> list[str]:
        result = await self.db.execute(
            f"""
            SELECT DISTINCT EVENT_ID
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND {self.active_sample_set.sql_fragment()}
            AND UPPER(EVENT_ID) LIKE UPPER('%{esc(prefix)}%')
            ORDER BY EVENT_ID
            LIMIT {limit}
            """
        )
        return [r[0] for r in result.rows if isinstance(r[0], str)]

    async def load_journey_info(self, project_id: str, event_id: str) -> dict[str, Any]:
        result = await self.db.execute(
            f"""
            SELECT MIN(EVENT_TIME), MAX(EVENT_TIME),
                   MAX(META_1), MAX(META_2), MAX(META_3)
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND {self.active_sample_set.sql_fragment()}
            AND EVENT_ID = '{esc(event_id)}'
            """
        )
        if not result.rows:
            return {}
        row = result.rows[0]
        return {
            "startDate": parse_date(row[0]),
            "endDate": parse_date(row[1]),
            "meta1": clean_str(row[2]),
            "meta2": clean_str(row[3]),
            "meta3": clean_str(row[4]),
        }

    async def load_journey_graph(self, project_id: str, event_id: str) -> ProcessGraph:
        safe_pid, safe_eid = esc(project_id), esc(event_id)
        frag = self.active_sample_set.sql_fragment()

        trans_result = await self.db.execute(
            f"""
            SELECT FROM_STEP, TO_STEP, COUNT(*) AS CNT,
                   AVG(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS AVG_SECS,
                   MIN(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS MIN_SECS,
                   MAX(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS MAX_SECS,
                   STDDEV(SECONDS_BETWEEN(TO_TIME, FROM_TIME)) AS STDDEV_SECS
            FROM (
                SELECT
                    STEP       AS FROM_STEP,
                    EVENT_TIME AS FROM_TIME,
                    LEAD(STEP)       OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_STEP,
                    LEAD(EVENT_TIME) OVER (PARTITION BY EVENT_ID ORDER BY EVENT_TIME, STEP_ID) AS TO_TIME
                FROM JOURNEYS
                WHERE PROJECT_ID = '{safe_pid}'
                AND {frag}
                AND EVENT_ID = '{safe_eid}'
            ) AS t
            WHERE TO_STEP IS NOT NULL AND TO_TIME IS NOT NULL
            GROUP BY FROM_STEP, TO_STEP
            ORDER BY CNT DESC
            """
        )
        transitions = self._rows_to_transitions(trans_result.rows)

        time_result = await self.db.execute(
            f"""
            SELECT STEP, MIN(EVENT_TIME) AS FIRST_TIME
            FROM JOURNEYS
            WHERE PROJECT_ID = '{safe_pid}'
            AND {frag}
            AND EVENT_ID = '{safe_eid}'
            GROUP BY STEP
            """
        )
        step_times: dict[str, datetime] = {}
        for row in time_result.rows:
            if isinstance(row[0], str) and (when := parse_date(row[1])):
                step_times[row[0]] = when

        steps = await self.load_steps(project_id)
        graph = self._assemble_graph(steps, transitions)
        for name, when in step_times.items():
            if name in graph.steps:
                graph.steps[name].eventTime = when
        return graph

    # ── NOTES table ──────────────────────────────────────────────────────────

    async def ensure_notes_table(self) -> None:
        from .schema_ddl import NOTES_DDL

        await self.db.execute_quiet(NOTES_DDL)
        await self.db.execute_quiet(
            "ALTER TABLE NOTES ADD COLUMN IS_SHARED BOOLEAN DEFAULT FALSE"
        )
        await self.db.execute_quiet(
            "ALTER TABLE NOTES ADD COLUMN EDITED_BY VARCHAR(200) DEFAULT ''"
        )

    async def load_notes(self, project_id: str, username: str) -> list[ProcessNote]:
        vis_filter = ""
        if username:
            safe_user = esc(username.upper())
            vis_filter = (
                f"AND (UPPER(NOTE_USER) = '{safe_user}' "
                "OR NOTE_USER = '' OR IS_SHARED = TRUE)"
            )
        result = await self.db.execute(
            f"""
            SELECT ID, NOTES_DATE, EDITED_DATE, NOTE_USER, NOTE, IS_SHARED, EDITED_BY,
                   TARGET_TYPE, TARGET_FROM, TARGET_TO, FILTER_SNAPSHOT
            FROM NOTES
            WHERE PROJECT_ID = '{esc(project_id)}'
            {vis_filter}
            ORDER BY NOTES_DATE ASC
            """
        )
        notes: list[ProcessNote] = []
        for row in result.rows:
            created = parse_date(row[1])
            if not isinstance(row[0], str) or created is None:
                continue
            target_type = row[7] if isinstance(row[7], str) else "node"
            target_from = row[8] if isinstance(row[8], str) else ""
            target_to = row[9] if isinstance(row[9], str) else ""
            if target_type == "edge" and target_to:
                target = NoteTarget.model_validate(
                    {"type": "edge", "from": target_from, "to": target_to}
                )
            else:
                target = NoteTarget(type="node", value=target_from)

            snapshot: FilterSnapshot | None = None
            if isinstance(row[10], str) and row[10]:
                try:
                    snapshot = FilterSnapshot(**json.loads(row[10]))
                except (json.JSONDecodeError, TypeError, ValueError):
                    snapshot = None
            if snapshot is None:
                now = datetime.now()
                snapshot = FilterSnapshot(fromDate=now, toDate=now)

            notes.append(
                ProcessNote(
                    id=row[0],
                    text=row[4] if isinstance(row[4], str) else "",
                    createdAt=created,
                    editedAt=parse_date(row[2]),
                    target=target,
                    filterSnapshot=snapshot,
                    username=row[3] if isinstance(row[3], str) else "",
                    lastEditedBy=row[6] if isinstance(row[6], str) else "",
                    isShared=as_bool(row[5]),
                )
            )
        return notes

    async def note_owner(self, note_id: str) -> str | None:
        """The NOTE_USER (author) of a note by its globally-unique ID, or None if
        no such note exists. Used to authorize edits/deletes independently of note
        *visibility* (shared notes are visible to all, but only the author owns them)."""
        result = await self.db.execute(
            f"SELECT NOTE_USER FROM NOTES WHERE ID = '{esc(note_id)}'"
        )
        for row in result.rows:
            return row[0] if isinstance(row[0], str) else ""
        return None

    async def upsert_note(self, note: ProcessNote, project_id: str, username: str) -> None:
        # Scope the delete-then-insert to the caller's own (or an unowned/legacy)
        # note so a crafted ID can never clobber another user's note. The endpoint
        # already 403s a non-owner edit; this is defence in depth.
        safe_user = esc(username.upper())
        await self.db.execute_quiet(
            f"DELETE FROM NOTES WHERE ID = '{esc(note.id)}' "
            f"AND (UPPER(NOTE_USER) = '{safe_user}' OR NOTE_USER = '')"
        )

        if note.target.is_node:
            target_type, target_from, target_to = "node", note.target.value or "", ""
        else:
            target_type = "edge"
            target_from = note.target.from_ or ""
            target_to = note.target.to or ""

        created_sql = f"TIMESTAMP '{_ts(note.createdAt)}'"
        edited_sql = f"TIMESTAMP '{_ts(note.editedAt)}'" if note.editedAt else "NULL"
        snapshot_json = note.filterSnapshot.model_dump_json(by_alias=True)
        await self.db.execute(
            f"""
            INSERT INTO NOTES
                (ID, PROJECT_ID, NOTES_DATE, EDITED_DATE, NOTE_USER, NOTE, IS_SHARED, EDITED_BY,
                 TARGET_TYPE, TARGET_FROM, TARGET_TO, FILTER_SNAPSHOT)
            VALUES (
                '{esc(note.id)}', '{esc(project_id)}',
                {created_sql}, {edited_sql},
                '{esc(note.username)}', '{esc(note.text)}',
                {'TRUE' if note.isShared else 'FALSE'}, '{esc(note.lastEditedBy)}',
                '{target_type}', '{esc(target_from)}', '{esc(target_to)}',
                '{esc(snapshot_json)}'
            )
            """
        )

    async def delete_note(self, note_id: str, project_id: str, username: str) -> None:
        # Only the author (or an unowned/legacy note) may be deleted — a user must
        # not be able to delete another user's note, even a shared one whose ID is
        # visible to them.
        safe_user = esc(username.upper())
        await self.db.execute(
            f"DELETE FROM NOTES WHERE ID = '{esc(note_id)}' "
            f"AND PROJECT_ID = '{esc(project_id)}' "
            f"AND (UPPER(NOTE_USER) = '{safe_user}' OR NOTE_USER = '')"
        )

    # ── sampling ─────────────────────────────────────────────────────────────

    async def ensure_sample_set_column(self) -> None:
        await self.db.execute_quiet(
            "ALTER TABLE JOURNEYS ADD COLUMN SAMPLE_SET VARCHAR(20) DEFAULT 'ORIGINAL'"
        )
        await self.db.execute_quiet(
            "UPDATE JOURNEYS SET SAMPLE_SET = 'ORIGINAL' WHERE SAMPLE_SET IS NULL"
        )

    async def load_sample_journey_counts(self, project_id: str) -> dict[str, int]:
        result = await self.db.execute(
            f"""
            SELECT SAMPLE_SET, COUNT(DISTINCT EVENT_ID) AS cnt
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            GROUP BY SAMPLE_SET
            """
        )
        counts: dict[str, int] = {}
        for row in result.rows:
            if not isinstance(row[0], str):
                continue
            try:
                key = SampleSet(row[0]).value
            except ValueError:
                continue
            counts[key] = as_int(row[1])
        return counts

    async def load_all_event_ids_for_sampling(self, project_id: str) -> list[str]:
        result = await self.db.execute(
            f"""
            SELECT DISTINCT EVENT_ID
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL)
            """
        )
        return [r[0] for r in result.rows if isinstance(r[0], str)]

    async def load_event_ids_with_start_times(
        self, project_id: str
    ) -> list[tuple[str, datetime]]:
        result = await self.db.execute(
            f"""
            SELECT EVENT_ID, MIN(EVENT_TIME) AS start_time
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL)
            GROUP BY EVENT_ID
            """
        )
        pairs: list[tuple[str, datetime]] = []
        for row in result.rows:
            when = parse_date(row[1])
            if isinstance(row[0], str) and when is not None:
                pairs.append((row[0], when))
        return pairs

    async def load_event_ids_with_paths(self, project_id: str) -> list[tuple[str, str]]:
        result = await self.db.execute(
            f"""
            SELECT EVENT_ID,
                   LISTAGG(STEP, '->') WITHIN GROUP (ORDER BY EVENT_TIME, STEP_ID) AS journey_path
            FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL)
            GROUP BY EVENT_ID
            """
        )
        return [
            (r[0], r[1]) for r in result.rows if isinstance(r[0], str) and isinstance(r[1], str)
        ]

    async def insert_sample_journeys(
        self, project_id: str, event_ids: list[str], sample_set: SampleSet
    ) -> None:
        if not event_ids or sample_set.is_original:
            return
        safe_pid = esc(project_id)
        batch_size = 200
        for start in range(0, len(event_ids), batch_size):
            batch = event_ids[start : start + batch_size]
            in_list = ", ".join(f"'{esc(e)}'" for e in batch)
            await self.db.execute(
                f"""
                INSERT INTO JOURNEYS
                    (PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME, META_1, META_2, META_3, SAMPLE_SET)
                SELECT PROJECT_ID, EVENT_ID, STEP, STEP_ID, EVENT_TIME, META_1, META_2, META_3, '{sample_set.value}'
                FROM JOURNEYS
                WHERE PROJECT_ID = '{safe_pid}'
                AND (SAMPLE_SET = 'ORIGINAL' OR SAMPLE_SET IS NULL)
                AND EVENT_ID IN ({in_list})
                """
            )

    async def delete_sample(self, project_id: str, sample_set: SampleSet) -> None:
        if sample_set.is_original:
            return
        await self.db.execute(
            f"""
            DELETE FROM JOURNEYS
            WHERE PROJECT_ID = '{esc(project_id)}'
            AND SAMPLE_SET = '{sample_set.value}'
            """
        )
