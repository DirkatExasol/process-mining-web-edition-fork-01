/** KPI tiles — port of the `kpiPanel` / `singleChartKPITile` / `abPanelKPITile`
 *  section of ProcessMapView.swift. Order and visibility come from settings. */

import { useMemo } from 'react'
import { formatDateShort, formatDurationLong } from '../graph/format'
import { readSetting, useSetting } from '../settings'
import { useStore, type ABSide } from '../store'
import {
  KPI_DEFAULT_ORDER,
  KPI_META,
  sampleShortLabel,
  type DurationStats,
  type ProcessGraph,
} from '../types'
import { Spinner } from './ui'

/** Σ (score × visits) over scored nodes; visits = max(incoming, outgoing). */
export function graphValue(graph: ProcessGraph): number | null {
  if (graph.transitions.length === 0) return null
  const incoming: Record<string, number> = {}
  const outgoing: Record<string, number> = {}
  for (const t of graph.transitions) {
    incoming[t.toStep] = (incoming[t.toStep] ?? 0) + t.occurrences
    outgoing[t.fromStep] = (outgoing[t.fromStep] ?? 0) + t.occurrences
  }
  let total = 0
  let hasScore = false
  for (const [name, step] of Object.entries(graph.steps)) {
    if (step.score == null) continue
    const visits = Math.max(incoming[name] ?? 0, outgoing[name] ?? 0)
    if (visits <= 0) continue
    total += step.score * visits
    hasScore = true
  }
  return hasScore ? total : null
}

function signed(value: number, digits = 0): string {
  const formatted =
    digits > 0 ? Math.abs(value).toFixed(digits) : Math.abs(value).toLocaleString()
  return `${value < 0 ? '−' : '+'}${formatted}`
}

export function KpiTile({
  label,
  icon,
  value,
  loading = false,
  color,
}: {
  label: string
  icon: string
  value: string
  loading?: boolean
  color?: string
}) {
  return (
    <div
      className="kpi-tile"
      style={color ? { borderColor: color, borderWidth: 1.5 } : undefined}
    >
      <div className="kpi-label">
        <span aria-hidden style={{ color: color ?? 'var(--accent)' }}>
          {icon}
        </span>
        <span className="truncate">{label}</span>
      </div>
      {loading ? (
        <div style={{ height: 22, display: 'flex', alignItems: 'center' }}>
          <Spinner />
        </div>
      ) : (
        <span className="kpi-value truncate" style={color ? { color } : undefined}>
          {value}
        </span>
      )}
    </div>
  )
}

export function useOrderedKpiIds(): string[] {
  const [order] = useSetting<string>('kpi.order')
  return useMemo(() => {
    const stored = order.split(',').filter(Boolean)
    const all = KPI_DEFAULT_ORDER.split(',')
    return [...stored, ...all.filter((id) => !stored.includes(id))]
  }, [order])
}

interface TileInputs {
  graph: ProcessGraph
  journeyCount: number | null
  durations: DurationStats
  goodness: number | null
  /** Present in A/B mode — drives the green/red comparison colour. */
  otherGoodness?: number | null
  side?: ABSide
  loading: boolean
}

/** Renders one KPI by id, honouring its `kpi.show.<id>` visibility flag. */
function Tile({ id, inputs }: { id: string; inputs: TileInputs }) {
  const store = useStore()
  const [visible] = useSetting<boolean>(`kpi.show.${id}`, true)
  const meta = KPI_META[id]
  if (!visible || !meta) return null

  const { graph, journeyCount, durations, goodness, otherGoodness, side, loading } =
    inputs

  switch (id) {
    case 'totalJourneys':
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={store.totalJourneyCount?.toLocaleString() ?? '—'}
          loading={loading && store.totalJourneyCount == null}
        />
      )
    case 'filteredJourneys':
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={journeyCount?.toLocaleString() ?? '—'}
          loading={loading}
        />
      )
    case 'shortestJourney':
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={formatDurationLong(durations.minSecs)}
          loading={loading}
        />
      )
    case 'avgJourney':
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={formatDurationLong(durations.avgSecs)}
          loading={loading}
        />
      )
    case 'stdDev':
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={formatDurationLong(durations.stdDevSecs)}
          loading={loading}
        />
      )
    case 'longestJourney':
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={formatDurationLong(durations.maxSecs)}
          loading={loading}
        />
      )
    case 'graphValue': {
      const value = graphValue(graph)
      if (value == null) return null
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={signed(value)}
          loading={loading}
        />
      )
    }
    case 'processGoodness': {
      if (goodness == null) return null
      let color: string | undefined
      if (otherGoodness != null) {
        color =
          Math.abs(goodness - otherGoodness) < 0.005
            ? 'var(--blue)'
            : goodness > otherGoodness
              ? 'var(--green)'
              : 'var(--red)'
      }
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={signed(goodness, 2)}
          loading={loading}
          color={color}
        />
      )
    }
    case 'processSimilarity': {
      if (store.abSimilarityScore == null) return null
      const q = store.abSimilarityScore
      return (
        <KpiTile
          label={meta.label}
          icon={meta.icon}
          value={q.toFixed(2)}
          color={q >= 0.7 ? 'var(--green)' : q <= 0.3 ? 'var(--red)' : 'var(--blue)'}
        />
      )
    }
    case 'activeSample': {
      // Reflect the side's actual data source: a sample set, or a Sim-A/Sim-B
      // simulation (which otherwise leaves the stale sample-set label showing).
      const source = (side ?? 'a') === 'a' ? store.abDataSourceA : store.abDataSourceB
      if (source.kind === 'simulation') {
        const result = source.slot === 'Sim-A' ? store.simResultA : store.simResultB
        return (
          <KpiTile
            label={source.slot}
            icon={meta.icon}
            value={result?.totalJourneys?.toLocaleString() ?? '—'}
          />
        )
      }
      const count = store.sampleCounts[source.sampleSet] ?? store.totalJourneyCount
      return (
        <KpiTile
          label={sampleShortLabel(source.sampleSet)}
          icon={meta.icon}
          value={count?.toLocaleString() ?? '—'}
        />
      )
    }
    default:
      return null
  }
}

export function KpiStrip(inputs: TileInputs) {
  const ids = useOrderedKpiIds()
  return (
    <div className="kpi-strip">
      {ids.map((id) => (
        <Tile key={id} id={id} inputs={inputs} />
      ))}
    </div>
  )
}

/** Individual-Journey mode replaces the standard tiles with journey facts. */
export function JourneyKpiStrip() {
  const store = useStore()
  const graph = store.processGraph

  const durationSecs =
    store.journeyDate && store.journeyEndDate
      ? (new Date(store.journeyEndDate).getTime() -
          new Date(store.journeyDate).getTime()) /
        1000
      : null

  const scoreSum = useMemo(() => {
    let total = 0
    let hasScore = false
    for (const step of Object.values(graph.steps)) {
      if (step.score == null) continue
      total += step.score
      hasScore = true
    }
    return hasScore ? total : null
  }, [graph])

  const stepStats = useMemo(() => {
    const distinct = Object.keys(graph.steps).length
    const total = graph.transitions.reduce((sum, t) => sum + t.occurrences, 0) + 1
    return { total, distinct }
  }, [graph])

  const metaTiles: { label: string; value: string }[] = []
  if (store.meta1Title && store.journeyMeta1)
    metaTiles.push({ label: store.meta1Title, value: store.journeyMeta1 })
  if (store.meta2Title && store.journeyMeta2)
    metaTiles.push({ label: store.meta2Title, value: store.journeyMeta2 })
  if (store.meta3Title && store.journeyMeta3)
    metaTiles.push({ label: store.meta3Title, value: store.journeyMeta3 })

  return (
    <div className="kpi-strip">
      <KpiTile
        label="Date"
        icon="📅"
        value={store.journeyDate ? formatDateShort(store.journeyDate) : '—'}
        loading={store.isLoading}
      />
      <KpiTile
        label="Duration"
        icon="⏱️"
        value={formatDurationLong(durationSecs)}
        loading={store.isLoading}
      />
      <KpiTile
        label="Sum of Scores"
        icon="ƒ"
        value={scoreSum == null ? '—' : signed(scoreSum)}
        loading={store.isLoading}
      />
      <KpiTile
        label="Steps visited / distinct"
        icon="⑂"
        value={`${stepStats.total} / ${stepStats.distinct}`}
        loading={store.isLoading}
      />
      {metaTiles.map((tile) => (
        <KpiTile key={tile.label} label={tile.label} icon="🏷" value={tile.value} />
      ))}
    </div>
  )
}

export { readSetting }
