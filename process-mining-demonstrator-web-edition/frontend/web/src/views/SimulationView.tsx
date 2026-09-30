/** Monte Carlo simulation — port of SimulationView.swift.
 *
 * Left: configuration. Right: results (flow chart, variants, charts, event log)
 * with CSV export. Results are stored per slot so A/B can compare them. */

import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { KpiTile } from '../components/KpiStrip'
import { Chevron, Divider, Segmented, Unavailable } from '../components/ui'
import { FlowChart } from '../flow/FlowChart'
import { formatDateTime, formatDurationLong } from '../graph/format'
import { useStore } from '../store'
import type {
  EdgeDurationOverride,
  EdgeOverrideDraft,
  ProcessGraph,
  SimSlot,
  SimulationResult,
} from '../types'

type ResultsTab = 'flow' | 'variants' | 'charts' | 'events'

export function SimulationView() {
  const store = useStore()
  // The form lives in the store so it survives navigating away from this view and back.
  const form = store.simForm
  const setForm = store.setSimForm
  const [tab, setTab] = useState<ResultsTab>('flow')

  const result = form.slot === 'Sim-A' ? store.simResultA : store.simResultB
  const baseGraph =
    store.savedChartStates['A-Chart']?.processGraph ?? store.processGraph
  const canSimulate = baseGraph.transitions.length > 0

  // Raw-text lever inputs are parsed here, at run time: a blank / 1 / non-positive /
  // non-finite value is a no-op and dropped, so only real changes reach the engine.
  const parsedFactors = useMemo(() => {
    const out: Record<string, number> = {}
    for (const [name, raw] of Object.entries(form.stepResourceFactors)) {
      const n = Number(raw)
      if (raw.trim() !== '' && Number.isFinite(n) && n > 0 && n !== 1) out[name] = n
    }
    return out
  }, [form.stepResourceFactors])

  const parsedOverrides = useMemo(() => {
    const out: EdgeDurationOverride[] = []
    for (const o of form.edgeOverrides) {
      const n = Number(o.value)
      if (!o.fromStep || !o.toStep || o.value.trim() === '' || !Number.isFinite(n) || n <= 0)
        continue
      out.push(
        o.mode === 'abs'
          ? { fromStep: o.fromStep, toStep: o.toStep, meanSecs: n * 60 }
          : { fromStep: o.fromStep, toStep: o.toStep, multiplier: n },
      )
    }
    return out
  }, [form.edgeOverrides])

  const leverCount = Object.keys(parsedFactors).length + parsedOverrides.length

  const run = () =>
    void store.runSimulation(form.slot, {
      journeyCount: form.journeyCount,
      startDate: `${form.startDate}T00:00:00`,
      avgInterArrivalHours: form.avgInterArrivalHours,
      excludedSteps: form.excludedSteps,
      requiredSteps: form.requiredSteps,
      maxStepsPerJourney: form.maxStepsPerJourney,
      stepResourceFactors: parsedFactors,
      edgeOverrides: parsedOverrides,
    })

  if (!store.selectedProject) {
    return (
      <Unavailable
        glyph="🗺"
        title="No Project Selected"
        description="Select a project from the sidebar."
      />
    )
  }

  return (
    <div className="row" style={{ flex: 1, minHeight: 0, gap: 0, alignItems: 'stretch' }}>
      {/* ── Configuration ─────────────────────────────────────────────── */}
      <div
        className="col"
        style={{
          width: 340,
          flexShrink: 0,
          borderRight: '1px solid var(--separator)',
          background: 'var(--bg-secondary-grouped)',
          overflowY: 'auto',
          gap: 0,
        }}
      >
        <div className="row t-caption fg-secondary" style={{ padding: '10px 14px', gap: 6 }}>
          <span aria-hidden>🎲</span> Simulation configuration
        </div>
        <Divider />

        <div className="col" style={{ padding: 14, gap: 12 }}>
          <div className="field">
            <span className="field-label">Target slot</span>
            <Segmented
              options={[
                { value: 'Sim-A', label: 'Sim-A' },
                { value: 'Sim-B', label: 'Sim-B' },
              ]}
              value={form.slot}
              onChange={(slot) => setForm({ slot })}
            />
          </div>

          <div className="field">
            <span className="field-label">Journey count</span>
            <input
              className="text-input"
              type="number"
              min={1}
              value={form.journeyCount}
              onChange={(e) => setForm({ journeyCount: Number(e.target.value) })}
            />
          </div>

          <div className="field">
            <span className="field-label">Start date</span>
            <input
              className="text-input"
              type="date"
              value={form.startDate}
              onChange={(e) => setForm({ startDate: e.target.value })}
            />
          </div>

          <div className="field">
            <span className="field-label">Average inter-arrival (hours)</span>
            <input
              className="text-input"
              type="number"
              min={0.1}
              step={0.1}
              value={form.avgInterArrivalHours}
              onChange={(e) => setForm({ avgInterArrivalHours: Number(e.target.value) })}
            />
          </div>

          <div className="field">
            <span className="field-label">Max steps per journey</span>
            <input
              className="text-input"
              type="number"
              min={2}
              value={form.maxStepsPerJourney}
              onChange={(e) => setForm({ maxStepsPerJourney: Number(e.target.value) })}
            />
          </div>
        </div>

        <Divider />
        <StepPicker
          title="Excluded steps"
          hint="Removed before the Markov model is built."
          open={form.excludedOpen}
          onToggle={() => setForm({ excludedOpen: !form.excludedOpen })}
          steps={store.allSteps}
          selected={form.excludedSteps}
          onChange={(excludedSteps) => setForm({ excludedSteps })}
        />
        <Divider />
        <StepPicker
          title="Required steps"
          hint="Journeys not visiting all of these are discarded."
          open={form.requiredOpen}
          onToggle={() => setForm({ requiredOpen: !form.requiredOpen })}
          steps={store.allSteps}
          selected={form.requiredSteps}
          onChange={(requiredSteps) => setForm({ requiredSteps })}
        />
        <Divider />
        <ResourceFactors
          open={form.resourcesOpen}
          onToggle={() => setForm({ resourcesOpen: !form.resourcesOpen })}
          steps={store.allSteps}
          factors={form.stepResourceFactors}
          onChange={(stepResourceFactors) => setForm({ stepResourceFactors })}
        />
        <Divider />
        <EdgeOverrides
          open={form.overridesOpen}
          onToggle={() => setForm({ overridesOpen: !form.overridesOpen })}
          graph={baseGraph}
          factors={parsedFactors}
          overrides={form.edgeOverrides}
          onChange={(edgeOverrides) => setForm({ edgeOverrides })}
        />
        <Divider />

        <div className="col" style={{ padding: 14, gap: 8 }}>
          {leverCount > 0 && (
            <span className="t-caption2 fg-tertiary">
              {leverCount} what-if resource lever{leverCount === 1 ? '' : 's'} active — run into{' '}
              <b>Sim-B</b> and compare against a clean <b>Sim-A</b> in the Sampling A/B section.
            </span>
          )}
          {!canSimulate && (
            <span className="t-caption2 fg-orange">
              Load the A-Chart first — simulation needs an observed process graph.
            </span>
          )}
          {store.simulationError && (
            <span className="t-caption2 fg-red">{store.simulationError}</span>
          )}
          <button
            className="btn prominent"
            disabled={!canSimulate || store.isSimulating}
            onClick={run}
          >
            {store.isSimulating && <span className="spinner" />} Run simulation
          </button>
        </div>
      </div>

      {/* ── Results ───────────────────────────────────────────────────── */}
      <div className="col" style={{ flex: 1, minWidth: 0, gap: 0 }}>
        {!result ? (
          <Unavailable
            glyph="🎲"
            title={`${form.slot} — no results yet`}
            description="Configure the parameters and run the simulation. Results can then be selected as an A/B data source in the Sampling section."
          />
        ) : (
          <SimulationResults
            result={result}
            slot={form.slot}
            tab={tab}
            onTabChange={setTab}
            projectId={store.selectedProject.projectId}
          />
        )}
      </div>
    </div>
  )
}

function StepPicker({
  title,
  hint,
  open,
  onToggle,
  steps,
  selected,
  onChange,
}: {
  title: string
  hint: string
  open: boolean
  onToggle: () => void
  steps: string[]
  selected: string[]
  onChange: (value: string[]) => void
}) {
  return (
    <div className="col" style={{ gap: 0 }}>
      <div className="sub-header">
        <button onClick={onToggle}>
          <Chevron open={open} />
          <span className="sub-title">{title}</span>
        </button>
        {selected.length > 0 && <span className="badge-pill">{selected.length}</span>}
        {selected.length > 0 && (
          <button
            className="icon-btn"
            style={{ width: 20, height: 20, color: 'var(--secondary)' }}
            onClick={() => onChange([])}
            title={`Clear ${title}`}
          >
            ⊗
          </button>
        )}
      </div>
      {open && (
        <div className="col" style={{ padding: '0 14px 12px', gap: 6 }}>
          <span className="t-caption2 fg-tertiary">{hint}</span>
          <div className="step-list" style={{ maxHeight: 180 }}>
            {steps.map((step) => {
              const isSelected = selected.includes(step)
              return (
                <button
                  key={step}
                  className={`step-row${isSelected ? ' selected' : ''}`}
                  onClick={() =>
                    onChange(
                      isSelected
                        ? selected.filter((s) => s !== step)
                        : [...selected, step],
                    )
                  }
                >
                  <span className="mark">{isSelected ? '◉' : '○'}</span>
                  <span className="truncate">{step}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

/** Per-step resource factor: a multiplier applied to every transition leaving the step.
 *  <1 = more resources (faster), >1 = fewer (slower), 1 = unchanged. The value is kept as
 *  raw text so any number can be typed freely (e.g. "1.5", "12"); it is parsed on run. */
function ResourceFactors({
  open,
  onToggle,
  steps,
  factors,
  onChange,
}: {
  open: boolean
  onToggle: () => void
  steps: string[]
  factors: Record<string, string>
  onChange: (value: Record<string, string>) => void
}) {
  const active = Object.values(factors).filter((raw) => {
    const n = Number(raw)
    return raw.trim() !== '' && Number.isFinite(n) && n > 0 && n !== 1
  })
  const set = (step: string, raw: string) => {
    const next = { ...factors }
    if (raw === '') delete next[step]
    else next[step] = raw
    onChange(next)
  }
  return (
    <div className="col" style={{ gap: 0 }}>
      <div className="sub-header">
        <button onClick={onToggle}>
          <Chevron open={open} />
          <span className="sub-title">Resources per step</span>
        </button>
        {active.length > 0 && <span className="badge-pill">{active.length}</span>}
        {active.length > 0 && (
          <button
            className="icon-btn"
            style={{ width: 20, height: 20, color: 'var(--secondary)' }}
            onClick={() => onChange({})}
            title="Clear resource factors"
          >
            ⊗
          </button>
        )}
      </div>
      {open && (
        <div className="col" style={{ padding: '0 14px 12px', gap: 6 }}>
          <span className="t-caption2 fg-tertiary">
            A factor on the time of every transition <b>leaving</b> a step. &lt;1 = more
            resources (faster), &gt;1 = fewer (slower).
          </span>
          <div className="step-list" style={{ maxHeight: 220 }}>
            {steps.map((step) => (
              <div
                key={step}
                className="row"
                style={{ gap: 8, alignItems: 'center', padding: '3px 6px' }}
              >
                <span className="truncate" style={{ flex: 1, fontSize: 13 }}>
                  {step}
                </span>
                <span className="fg-tertiary" style={{ fontSize: 12 }}>
                  ×
                </span>
                <input
                  className="text-input"
                  type="text"
                  inputMode="decimal"
                  placeholder="1.0"
                  value={factors[step] ?? ''}
                  onChange={(e) => set(step, e.target.value)}
                  style={{ width: 68 }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Per-transition duration what-ifs: pick a from→to edge, then scale it (×) or set an
 *  absolute mean (=). Values are raw text (parsed on run) so any number types freely.
 *  Shows the observed time and the resulting target time. */
function EdgeOverrides({
  open,
  onToggle,
  graph,
  factors,
  overrides,
  onChange,
}: {
  open: boolean
  onToggle: () => void
  graph: ProcessGraph
  factors: Record<string, number>
  overrides: EdgeOverrideDraft[]
  onChange: (value: EdgeOverrideDraft[]) => void
}) {
  const adjacency = useMemo(() => {
    const map = new Map<string, { to: string; avgSecs: number | null }[]>()
    for (const t of graph.transitions) {
      const list = map.get(t.fromStep) ?? []
      list.push({ to: t.toStep, avgSecs: t.avgSecs })
      map.set(t.fromStep, list)
    }
    for (const list of map.values()) list.sort((a, b) => a.to.localeCompare(b.to))
    return map
  }, [graph])
  const fromSteps = useMemo(() => [...adjacency.keys()].sort((a, b) => a.localeCompare(b)), [adjacency])

  const observedAvg = (from: string, to: string): number | null =>
    adjacency.get(from)?.find((e) => e.to === to)?.avgSecs ?? null

  const update = (index: number, patch: Partial<EdgeOverrideDraft>) =>
    onChange(overrides.map((o, i) => (i === index ? { ...o, ...patch } : o)))
  const remove = (index: number) => onChange(overrides.filter((_, i) => i !== index))
  const add = () => {
    const from = fromSteps[0] ?? ''
    const to = adjacency.get(from)?.[0]?.to ?? ''
    onChange([...overrides, { fromStep: from, toStep: to, mode: 'mult', value: '0.5' }])
  }

  return (
    <div className="col" style={{ gap: 0 }}>
      <div className="sub-header">
        <button onClick={onToggle}>
          <Chevron open={open} />
          <span className="sub-title">Transition time overrides</span>
        </button>
        {overrides.length > 0 && <span className="badge-pill">{overrides.length}</span>}
        {overrides.length > 0 && (
          <button
            className="icon-btn"
            style={{ width: 20, height: 20, color: 'var(--secondary)' }}
            onClick={() => onChange([])}
            title="Clear transition overrides"
          >
            ⊗
          </button>
        )}
      </div>
      {open && (
        <div className="col" style={{ padding: '0 14px 12px', gap: 10 }}>
          <span className="t-caption2 fg-tertiary">
            Change one transition's time. <b>×</b> scales the observed mean; <b>=</b> sets an
            absolute mean (minutes). A step's resource factor still applies on top.
          </span>
          {overrides.map((o, i) => {
            const neighbors = adjacency.get(o.fromStep) ?? []
            const base = observedAvg(o.fromStep, o.toStep)
            const isAbs = o.mode === 'abs'
            const stepFactor =
              Number.isFinite(factors[o.fromStep]) && factors[o.fromStep] > 0
                ? factors[o.fromStep]
                : 1
            const n = Number(o.value)
            const valid = o.value.trim() !== '' && Number.isFinite(n) && n > 0
            let target: number | null = null
            if (valid && isAbs) target = n * 60 * stepFactor
            else if (valid && base != null) target = base * n * stepFactor
            return (
              <div
                key={i}
                className="col"
                style={{
                  gap: 6,
                  padding: 8,
                  border: '1px solid var(--separator-soft)',
                  borderRadius: 8,
                }}
              >
                <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                  <select
                    className="text-input"
                    value={o.fromStep}
                    onChange={(e) => {
                      const from = e.target.value
                      const to = adjacency.get(from)?.[0]?.to ?? ''
                      update(i, { fromStep: from, toStep: to })
                    }}
                    style={{ flex: 1, minWidth: 0 }}
                  >
                    {fromSteps.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <span className="fg-tertiary">→</span>
                  <select
                    className="text-input"
                    value={o.toStep}
                    onChange={(e) => update(i, { toStep: e.target.value })}
                    style={{ flex: 1, minWidth: 0 }}
                  >
                    {neighbors.map((nb) => (
                      <option key={nb.to} value={nb.to}>
                        {nb.to}
                      </option>
                    ))}
                  </select>
                  <button
                    className="icon-btn"
                    style={{ width: 22, height: 22, color: 'var(--secondary)' }}
                    onClick={() => remove(i)}
                    title="Remove override"
                  >
                    ⊗
                  </button>
                </div>
                <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                  <Segmented
                    options={[
                      { value: 'mult', label: '×' },
                      { value: 'abs', label: '=' },
                    ]}
                    value={o.mode}
                    onChange={(mode) => {
                      if (mode === o.mode) return
                      if (mode === 'abs') {
                        const mult = valid ? n : 1
                        const minutes = base != null ? Math.round((base * mult) / 60) : 60
                        update(i, { mode: 'abs', value: String(minutes) })
                      } else {
                        update(i, { mode: 'mult', value: '0.5' })
                      }
                    }}
                  />
                  <input
                    className="text-input"
                    type="text"
                    inputMode="decimal"
                    value={o.value}
                    onChange={(e) => update(i, { value: e.target.value })}
                    style={{ width: 84 }}
                  />
                  <span className="fg-tertiary" style={{ fontSize: 12 }}>
                    {isAbs ? 'min' : '× time'}
                  </span>
                </div>
                <span className="t-caption2 fg-tertiary">
                  observed {base != null ? formatDurationLong(base) : '—'}
                  {target != null && (
                    <>
                      {' → '}
                      <b>{formatDurationLong(target)}</b>
                    </>
                  )}
                </span>
              </div>
            )
          })}
          <button className="btn small" onClick={add} disabled={fromSteps.length === 0}>
            ＋ Add transition override
          </button>
        </div>
      )}
    </div>
  )
}

function cycleTimeBuckets(times: number[], binCount = 12) {
  if (times.length === 0) return []
  const min = Math.min(...times)
  const max = Math.max(...times)
  const width = max > min ? (max - min) / binCount : Math.max(max, 1)
  const counts = new Array(binCount).fill(0)
  for (const t of times) {
    const index = Math.min(binCount - 1, Math.floor((t - min) / width))
    counts[index] += 1
  }
  return counts.map((count, index) => ({
    label: formatDurationLong(min + index * width),
    count,
  }))
}

function toCSV(result: SimulationResult): string {
  const rows = [['journeyId', 'step', 'timestamp'].join(',')]
  for (const event of result.events) {
    rows.push(
      [event.journeyId, `"${event.step.replace(/"/g, '""')}"`, event.timestamp].join(','),
    )
  }
  return rows.join('\n')
}

function SimulationResults({
  result,
  slot,
  tab,
  onTabChange,
  projectId,
}: {
  result: SimulationResult
  slot: SimSlot
  tab: ResultsTab
  onTabChange: (tab: ResultsTab) => void
  projectId: number
}) {
  const store = useStore()
  const buckets = useMemo(() => cycleTimeBuckets(result.cycleTimes), [result.cycleTimes])

  const exportCSV = () => {
    const blob = new Blob([toCSV(result)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${slot}-event-log.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <div className="kpi-strip">
        <KpiTile
          label="Journeys"
          icon="👥"
          value={result.totalJourneys.toLocaleString()}
        />
        <KpiTile
          label="Avg cycle time"
          icon="⏱️"
          value={formatDurationLong(result.avgCycleTimeSecs)}
        />
        <KpiTile
          label="Shortest"
          icon="🐇"
          value={formatDurationLong(result.minCycleTimeSecs)}
        />
        <KpiTile
          label="Longest"
          icon="🐢"
          value={formatDurationLong(result.maxCycleTimeSecs)}
        />
        <KpiTile
          label="Std dev"
          icon="〰️"
          value={formatDurationLong(result.stdDevCycleTimeSecs)}
        />
        <KpiTile
          label="Variants"
          icon="⑂"
          value={result.variants.length.toLocaleString()}
        />
      </div>

      <div
        className="row"
        style={{
          padding: '8px 16px',
          gap: 10,
          background: 'var(--bg-tertiary-grouped)',
          borderBottom: '1px solid var(--separator-soft)',
        }}
      >
        <Segmented
          options={[
            { value: 'flow', label: 'Flow' },
            { value: 'variants', label: 'Variants' },
            { value: 'charts', label: 'Charts' },
            { value: 'events', label: 'Event log' },
          ]}
          value={tab}
          onChange={onTabChange}
        />
        <span className="spacer" />
        <button className="btn small" onClick={exportCSV}>
          ⤓ Export CSV
        </button>
      </div>

      {tab === 'flow' && (
        <FlowChart
          key={result.runId}
          graph={result.simProcessGraph}
          projectId={projectId}
          chartMode={`sim_${slot}`}
          metric={store.transitionMetric}
          journeyTotal={result.totalJourneys}
        />
      )}

      {tab === 'variants' && (
        <div className="scroll-view">
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Path</th>
                  <th style={{ textAlign: 'right' }}>Count</th>
                  <th style={{ textAlign: 'right' }}>Share</th>
                  <th style={{ textAlign: 'right' }}>Avg cycle time</th>
                </tr>
              </thead>
              <tbody>
                {result.variants.map((variant, index) => (
                  <tr key={`${variant.path}-${index}`}>
                    <td style={{ wordBreak: 'break-word' }}>{variant.path}</td>
                    <td className="num">{variant.count.toLocaleString()}</td>
                    <td className="num">{variant.percentage.toFixed(1)}%</td>
                    <td className="num">
                      {formatDurationLong(variant.avgCycleTimeSecs)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'charts' && (
        <div className="scroll-view">
          <div className="panel">
            <div className="panel-head">Cycle-time distribution</div>
            <div className="panel-body" style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={buckets}>
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
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">Top variants</div>
            <div className="panel-body" style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={result.variants.slice(0, 12).map((v, i) => ({
                    name: `V${i + 1}`,
                    count: v.count,
                    path: v.path,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={48} />
                  <Tooltip
                    formatter={(value: number) => value.toLocaleString()}
                    labelFormatter={(_, payload) =>
                      (payload?.[0]?.payload as { path?: string })?.path ?? ''
                    }
                  />
                  <Bar dataKey="count" fill="#5E5CE6" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {tab === 'events' && (
        <div className="scroll-view">
          <span className="t-caption fg-secondary">
            Showing the first 1 000 of {result.events.length.toLocaleString()} events.
            Use “Export CSV” for the full log.
          </span>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Journey</th>
                  <th>Step</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {result.events.slice(0, 1000).map((event, index) => (
                  <tr key={index}>
                    <td>{event.journeyId}</td>
                    <td>{event.step}</td>
                    <td className="tnum">{formatDateTime(event.timestamp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
