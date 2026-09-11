/** Statistics — port of StatisticsView.swift.
 *
 * Routes tab: time series + searchable, sortable, paginated variant table.
 * Analytics tab: duration histogram, step traffic, and a transition heat map. */

import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { KpiStrip } from '../components/KpiStrip'
import { Chevron, Divider, Segmented, Unavailable } from '../components/ui'
import { formatDateShort, formatDurationLong } from '../graph/format'
import { useSetting } from '../settings'
import { useStore } from '../store'
import type { JourneyPath } from '../types'

type SortCol = 'path' | 'journeys' | 'steps' | 'score' | 'total'

const PAGE_SIZES = [25, 50, 100, 250]

export function StatisticsView() {
  const store = useStore()
  const [tab, setTab] = useState<'routes' | 'analytics'>('routes')
  const [kpiExpanded, setKpiExpanded] = useSetting<boolean>('statistics.kpiExpanded', true)
  const [sortCol, setSortCol] = useState<SortCol>('journeys')
  const [sortAsc, setSortAsc] = useState(false)
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(25)
  const [search, setSearch] = useState('')

  const stats = store.statistics
  const paths = stats?.paths ?? []

  // Load once per project, matching the Swift `.task(id: projectId)`.
  useEffect(() => {
    if (store.selectedProject && !store.statistics && !store.isLoadingStats) {
      void store.loadStatistics()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.selectedProject?.projectId])

  useEffect(() => {
    setPage(0)
  }, [sortCol, sortAsc, search, pageSize])

  const filtered = useMemo(
    () =>
      search
        ? paths.filter((p) => p.path.toLowerCase().includes(search.toLowerCase()))
        : paths,
    [paths, search],
  )

  const sorted = useMemo(() => {
    const key = (p: JourneyPath): number | string => {
      switch (sortCol) {
        case 'path':
          return p.path
        case 'journeys':
          return p.journeyCount
        case 'steps':
          return p.stepCount
        case 'score':
          return p.totalScore
        case 'total':
          return p.totalScore * p.journeyCount
      }
    }
    return [...filtered].sort((a, b) => {
      const ka = key(a)
      const kb = key(b)
      const cmp =
        typeof ka === 'string' && typeof kb === 'string'
          ? ka.localeCompare(kb)
          : (ka as number) - (kb as number)
      return sortAsc ? cmp : -cmp
    })
  }, [filtered, sortCol, sortAsc])

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const pageItems = sorted.slice(page * pageSize, page * pageSize + pageSize)

  // "Filters changed since the last load" banner.
  const isStale = useMemo(() => {
    const snap = store.statsLoadedSnapshot
    if (!snap) return false
    return (
      snap.fromDate !== store.fromDate ||
      snap.toDate !== store.toDate ||
      snap.includedSteps.join() !== store.includedSteps.join() ||
      snap.excludedSteps.join() !== store.excludedSteps.join() ||
      snap.meta1 !== store.meta1Filter ||
      snap.meta2 !== store.meta2Filter ||
      snap.meta3 !== store.meta3Filter ||
      snap.minSteps !== store.minStepsFilter ||
      snap.maxSteps !== store.maxStepsFilter ||
      snap.minScore !== store.minScoreFilter ||
      snap.maxScore !== store.maxScoreFilter
    )
  }, [store])

  if (store.isLoadingStats) {
    return (
      <div className="center-fill">
        <span className="spinner large" />
        <span>Computing journey routes</span>
      </div>
    )
  }

  if (!store.selectedProject) {
    return (
      <Unavailable
        glyph="🗺"
        title="No Project Selected"
        description="Select a project from the sidebar."
      />
    )
  }

  if (paths.length === 0) {
    return (
      <Unavailable
        glyph={store.statsErrorMessage ? '⚠️' : '⑂'}
        title={store.statsErrorMessage ? 'Query Failed' : 'No Routes Yet'}
        description={
          store.statsErrorMessage ??
          'Compute all journey routes for the current filters.'
        }
        action={
          <button className="btn prominent" onClick={() => void store.loadStatistics()}>
            ↻ {store.statsErrorMessage ? 'Retry' : 'Compute Routes'}
          </button>
        }
      />
    )
  }

  const header = (col: SortCol, label: string, numeric = false) => (
    <th
      style={{ cursor: 'pointer', textAlign: numeric ? 'right' : 'left' }}
      onClick={() => {
        if (sortCol === col) setSortAsc(!sortAsc)
        else {
          setSortCol(col)
          setSortAsc(col === 'path')
        }
      }}
    >
      {label} {sortCol === col ? (sortAsc ? '▲' : '▼') : ''}
    </th>
  )

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      <button className="kpi-handle" onClick={() => setKpiExpanded(!kpiExpanded)}>
        <Chevron open={kpiExpanded} />
        {!kpiExpanded && store.journeyCount != null && (
          <span>
            {store.journeyCount.toLocaleString()}
            {store.totalJourneyCount != null &&
              ` / ${store.totalJourneyCount.toLocaleString()}`}{' '}
            Journeys
          </span>
        )}
      </button>
      {kpiExpanded && (
        <KpiStrip
          graph={stats?.processGraph ?? store.processGraph}
          journeyCount={store.journeyCount}
          durations={store.durations}
          goodness={store.processGoodnessScore}
          loading={false}
        />
      )}

      <div className="row t-caption2 fg-secondary" style={{ padding: '5px 16px', gap: 6 }}>
        <span aria-hidden>ⓘ</span> Statistics use the same filters as Chart A.
      </div>

      {isStale && (
        <div
          className="row"
          style={{ padding: '7px 16px', gap: 10, background: 'rgba(255,149,0,0.10)' }}
        >
          <span className="fg-orange">⚠</span>
          <span className="t-caption fg-secondary spacer">
            Filters changed since last load
          </span>
          <button className="btn small" onClick={() => void store.loadStatistics()}>
            ↻ Reload
          </button>
        </div>
      )}

      <div style={{ padding: '8px 16px', background: 'var(--bg-tertiary-grouped)' }}>
        <Segmented
          options={[
            { value: 'routes', label: 'Routes' },
            { value: 'analytics', label: 'Analytics' },
          ]}
          value={tab}
          onChange={setTab}
        />
      </div>
      <Divider />

      {tab === 'routes' ? (
        <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
          <div className="row" style={{ padding: '8px 16px', gap: 12 }}>
            <div className="search-row" style={{ flex: 1, maxWidth: 360 }}>
              <span aria-hidden className="fg-secondary">
                🔍
              </span>
              <input
                value={search}
                placeholder="Filter paths"
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button className="fg-secondary" onClick={() => setSearch('')}>
                  ⊗
                </button>
              )}
            </div>
            <span className="t-caption fg-secondary">
              {sorted.length.toLocaleString()} route
              {sorted.length === 1 ? '' : 's'}
              {stats?.isTruncated && ' (truncated)'}
            </span>
            <span className="spacer" />
            <button className="btn small" onClick={() => void store.loadStatistics()}>
              ↻ Reload
            </button>
          </div>
          <Divider />

          <div className="scroll-view" style={{ paddingTop: 0 }}>
            {stats && stats.timeSeries.length > 0 && (
              <div className="panel">
                <div className="panel-head">
                  Journeys over time
                  <span className="spacer" />
                  <span className="t-caption fg-secondary">
                    {stats.timeGranularity === 'day'
                      ? 'Daily'
                      : stats.timeGranularity === 'week'
                        ? 'Weekly'
                        : 'Monthly'}
                  </span>
                </div>
                <div className="panel-body" style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={stats.timeSeries.map((p) => ({
                        date: formatDateShort(p.date),
                        count: p.count,
                      }))}
                    >
                      <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={24} />
                      <YAxis tick={{ fontSize: 10 }} width={48} />
                      <Tooltip />
                      <Line
                        type="monotone"
                        dataKey="count"
                        stroke="var(--accent)"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {header('path', 'Journey Path')}
                    {header('journeys', 'Journeys', true)}
                    {header('steps', 'Steps', true)}
                    {header('score', 'Score/J', true)}
                    {header('total', 'Total', true)}
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((p, index) => (
                    <tr key={`${p.path}-${index}`}>
                      <td style={{ wordBreak: 'break-word' }}>{p.path}</td>
                      <td className="num">{p.journeyCount.toLocaleString()}</td>
                      <td className="num">{p.stepCount}</td>
                      <td className="num">{p.totalScore}</td>
                      <td className="num">
                        {(p.totalScore * p.journeyCount).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <Divider />
          <div className="row" style={{ padding: '8px 16px', gap: 10 }}>
            <button
              className="btn small"
              disabled={page === 0}
              onClick={() => setPage(0)}
            >
              ⇤
            </button>
            <button
              className="btn small"
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
            >
              ‹
            </button>
            <span className="t-caption fg-secondary tnum">
              Page {page + 1} of {totalPages}
            </span>
            <button
              className="btn small"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(page + 1)}
            >
              ›
            </button>
            <button
              className="btn small"
              disabled={page >= totalPages - 1}
              onClick={() => setPage(totalPages - 1)}
            >
              ⇥
            </button>
            <span className="spacer" />
            <span className="t-caption fg-secondary">Rows</span>
            <select
              className="select-input"
              style={{ width: 'auto' }}
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
            >
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : (
        <AnalyticsTab />
      )}
    </div>
  )
}

function AnalyticsTab() {
  const store = useStore()
  const stats = store.statistics
  if (!stats) return null

  const graph = stats.processGraph

  // Step traffic: visits per node = max(incoming, outgoing).
  const traffic = useMemo(() => {
    const incoming: Record<string, number> = {}
    const outgoing: Record<string, number> = {}
    for (const t of graph.transitions) {
      incoming[t.toStep] = (incoming[t.toStep] ?? 0) + t.occurrences
      outgoing[t.fromStep] = (outgoing[t.fromStep] ?? 0) + t.occurrences
    }
    return Object.keys(graph.steps)
      .map((name) => ({
        step: name,
        visits: Math.max(incoming[name] ?? 0, outgoing[name] ?? 0),
      }))
      .sort((a, b) => b.visits - a.visits)
      .slice(0, 25)
  }, [graph])

  const maxOccurrences = Math.max(
    1,
    ...graph.transitions.map((t) => t.occurrences),
  )
  const heatSteps = useMemo(() => Object.keys(graph.steps).sort(), [graph.steps])
  const heatLookup = useMemo(() => {
    const map = new Map<string, number>()
    for (const t of graph.transitions) map.set(`${t.fromStep}→${t.toStep}`, t.occurrences)
    return map
  }, [graph.transitions])

  return (
    <div className="scroll-view">
      <div className="panel">
        <div className="panel-head">Journey duration distribution</div>
        <div className="panel-body" style={{ height: 260 }}>
          {stats.durationBuckets.length === 0 ? (
            <span className="t-footnote fg-secondary">No duration data.</span>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.durationBuckets}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 9 }}
                  interval={0}
                  angle={-35}
                  textAnchor="end"
                  height={60}
                />
                <YAxis tick={{ fontSize: 10 }} width={48} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          Step traffic
          <span className="spacer" />
          <span className="t-caption fg-secondary">Top 25 by visits</span>
        </div>
        <div className="panel-body" style={{ height: Math.max(220, traffic.length * 22) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={traffic} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
              <XAxis type="number" tick={{ fontSize: 10 }} />
              <YAxis
                type="category"
                dataKey="step"
                tick={{ fontSize: 10 }}
                width={150}
              />
              <Tooltip />
              <Bar dataKey="visits" radius={[0, 3, 3, 0]}>
                {traffic.map((entry, index) => (
                  <Cell key={entry.step} fill={index === 0 ? 'var(--accent)' : '#5E9BEA'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          Transition heat map
          <span className="spacer" />
          <span className="t-caption fg-secondary">rows = from · columns = to</span>
        </div>
        <div className="panel-body" style={{ overflow: 'auto' }}>
          {heatSteps.length === 0 ? (
            <span className="t-footnote fg-secondary">No transitions.</span>
          ) : (
            <table className="data-table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th />
                  {heatSteps.map((to) => (
                    <th key={to} style={{ writingMode: 'vertical-rl', height: 110 }}>
                      {to}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatSteps.map((from) => (
                  <tr key={from}>
                    <th style={{ position: 'sticky', left: 0 }}>{from}</th>
                    {heatSteps.map((to) => {
                      const count = heatLookup.get(`${from}→${to}`) ?? 0
                      const intensity = count / maxOccurrences
                      return (
                        <td
                          key={to}
                          className="num"
                          title={`${from} → ${to}: ${count.toLocaleString()}`}
                          style={{
                            background:
                              count > 0
                                ? `rgba(10, 132, 255, ${0.12 + intensity * 0.78})`
                                : undefined,
                            color: intensity > 0.55 ? '#fff' : undefined,
                            minWidth: 44,
                            textAlign: 'center',
                          }}
                        >
                          {count > 0 ? count.toLocaleString() : ''}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">Duration KPIs</div>
        <div className="panel-body">
          <div className="row wrap" style={{ gap: 24 }}>
            {(
              [
                ['Shortest', stats.durations.minSecs],
                ['Average', stats.durations.avgSecs],
                ['Std deviation', stats.durations.stdDevSecs],
                ['Longest', stats.durations.maxSecs],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="col" style={{ gap: 2 }}>
                <span className="t-caption fg-secondary">{label}</span>
                <span className="t-headline tnum">{formatDurationLong(value)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
