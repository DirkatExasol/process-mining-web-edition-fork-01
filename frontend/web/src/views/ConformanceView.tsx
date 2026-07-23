/** Conformance Check / Target Process — port of TargetProcessView.swift.
 *
 * View mode colours each edge by actual-vs-norm; Edit mode lets you click an
 * edge and type its target value. Norms are stored per project and per metric. */

import { useState } from 'react'
import { KpiStrip } from '../components/KpiStrip'
import { Chevron, Divider, Unavailable } from '../components/ui'
import { FlowChart } from '../flow/FlowChart'
import { formatDuration } from '../graph/format'
import { useSetting } from '../settings'
import { useStore } from '../store'
import {
  TRANSITION_METRICS,
  isTimeBased,
  metricValue,
  type ProcessTransition,
  type TransitionMetric,
} from '../types'

const METRIC_ICONS: Record<TransitionMetric, string> = {
  Count: '#',
  'Avg Time': '⏱',
  'Min Time': '⌄',
  'Max Time': '⌃',
  'Std Dev': '〰',
}

interface NormEditor {
  transition: ProcessTransition
  x: number
  y: number
  text: string
}

export function ConformanceView() {
  const store = useStore()
  const [editMode, setEditMode] = useState(false)
  const [kpiExpanded, setKpiExpanded] = useSetting<boolean>('compliance.kpiExpanded')
  const [normIsMinimum, setNormIsMinimum] = useSetting<boolean>(
    'compliance.normIsMinimum',
  )
  const [showGapTable, setShowGapTable] = useState(false)
  const [editor, setEditor] = useState<NormEditor | null>(null)

  const metric = store.targetMetric
  const norms = store.targetNorms[metric] ?? {}
  const graph = store.processGraph

  if (!store.selectedProject) {
    return (
      <Unavailable
        glyph="🗺"
        title="No Project Selected"
        description="Select a project from the sidebar."
      />
    )
  }

  if (graph.transitions.length === 0) {
    return (
      <Unavailable
        glyph="🛡️"
        title="No Process Data"
        description="Apply filters in the sidebar to load the process map."
        action={
          <button className="btn prominent" onClick={() => void store.reloadGraph()}>
            Load
          </button>
        }
      />
    )
  }

  const outgoing: Record<string, number> = {}
  for (const t of graph.transitions) {
    outgoing[t.fromStep] = (outgoing[t.fromStep] ?? 0) + t.occurrences
  }

  const actualFor = (t: ProcessTransition): number => {
    if (metric === 'Count') {
      const total = outgoing[t.fromStep] ?? 1
      return (t.occurrences / total) * 100
    }
    return metricValue(t, metric) ?? t.occurrences
  }

  const formatValue = (value: number): string => {
    if (metric === 'Count') return `${value.toFixed(1)}%`
    if (isTimeBased(metric)) return formatDuration(value)
    return String(Math.round(value))
  }

  const entries = graph.transitions
    .filter((t) => t.fromStep !== t.toStep)
    .map((t) => {
      const id = `${t.fromStep}->${t.toStep}`
      const actual = actualFor(t)
      const norm = norms[id] ?? null
      const delta = norm == null ? null : actual - norm
      const violation =
        norm == null ? null : normIsMinimum ? actual < norm : actual > norm
      return { t, id, actual, norm, delta, violation }
    })
    .sort((a, b) => {
      if (a.violation === true && b.violation !== true) return -1
      if (b.violation === true && a.violation !== true) return 1
      return (b.delta ?? 0) - (a.delta ?? 0)
    })

  const violations = entries.filter((e) => e.violation === true).length
  const compliant = entries.filter((e) => e.violation === false).length
  const withoutNorm = entries.filter((e) => e.norm == null).length

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      <button className="kpi-handle" onClick={() => setKpiExpanded(!kpiExpanded)}>
        <Chevron open={kpiExpanded} />
        {!kpiExpanded && (
          <span>
            {violations} violation{violations === 1 ? '' : 's'} · {compliant} compliant
          </span>
        )}
      </button>
      {kpiExpanded && (
        <KpiStrip
          graph={graph}
          journeyCount={store.journeyCount}
          durations={store.durations}
          goodness={store.processGoodnessScore}
          loading={store.isLoading}
        />
      )}

      <div
        className="row wrap"
        style={{
          padding: '7px 14px',
          gap: 8,
          background: 'var(--bg-tertiary-grouped)',
          borderBottom: '1px solid var(--separator-soft)',
        }}
      >
        {TRANSITION_METRICS.map((m) => (
          <button
            key={m}
            className={`chip${metric === m ? ' active' : ''}`}
            onClick={() => store.setTargetMetric(m)}
          >
            <span aria-hidden>{METRIC_ICONS[m]}</span> {m}
          </button>
        ))}
        <span className="spacer" />
        <label className="row t-caption fg-secondary" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={normIsMinimum}
            onChange={(e) => setNormIsMinimum(e.target.checked)}
          />
          Norm is a minimum
        </label>
        <button
          className="btn small"
          onClick={() => setShowGapTable(!showGapTable)}
          title="Toggle the gap-analysis table"
        >
          {showGapTable ? 'Hide gaps' : 'Show gaps'}
        </button>
        <button
          className={`btn small${editMode ? ' prominent' : ''}`}
          onClick={() => {
            setEditMode(!editMode)
            setEditor(null)
          }}
        >
          {editMode ? 'Done' : 'Edit norms'}
        </button>
      </div>

      <div
        className="row t-caption2 fg-secondary"
        style={{ padding: '5px 16px', gap: 10 }}
      >
        <span className="fg-red">❌ {violations} violation{violations === 1 ? '' : 's'}</span>
        <span className="fg-green">✅ {compliant} compliant</span>
        <span>— {withoutNorm} without norm</span>
        {editMode && <span className="spacer fg-accent">Click an edge to set its norm</span>}
      </div>

      <div className="row" style={{ flex: 1, minHeight: 0, gap: 0, alignItems: 'stretch' }}>
        <div style={{ flex: 1, minWidth: 0, position: 'relative', display: 'flex' }}>
          <FlowChart
            graph={graph}
            projectId={store.selectedProject.projectId}
            chartMode="Conformance"
            metric={metric}
            isLoading={store.isLoading}
            normValues={norms}
            normMetric={metric}
            showCompliance={!editMode}
            normIsMinimum={normIsMinimum}
            onEdgeTap={
              editMode
                ? (transition, screen) =>
                    setEditor({
                      transition,
                      x: screen.x,
                      y: screen.y,
                      text:
                        norms[`${transition.fromStep}->${transition.toStep}`]?.toString() ??
                        '',
                    })
                : undefined
            }
          />

          {editor && (
            <>
              <div
                style={{ position: 'fixed', inset: 0, zIndex: 199 }}
                onClick={() => setEditor(null)}
              />
              <div
                className="popover"
                style={{
                  left: Math.max(140, Math.min(window.innerWidth - 160, editor.x)),
                  top: Math.max(80, Math.min(window.innerHeight - 200, editor.y + 12)),
                  width: 260,
                  padding: 14,
                }}
              >
                <div className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
                  {editor.transition.fromStep} → {editor.transition.toStep}
                </div>
                <Divider />
                <div className="col" style={{ gap: 8, marginTop: 10 }}>
                  <span className="t-caption2 fg-tertiary">
                    Actual: {formatValue(actualFor(editor.transition))}
                    {metric === 'Count' && ' of outgoing'}
                  </span>
                  <input
                    className="text-input"
                    autoFocus
                    inputMode="decimal"
                    placeholder={metric === 'Count' ? 'Target %' : 'Target value (seconds)'}
                    value={editor.text}
                    onChange={(e) => setEditor({ ...editor, text: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key !== 'Enter') return
                      const value = Number(editor.text.trim())
                      store.saveNorm(
                        `${editor.transition.fromStep}->${editor.transition.toStep}`,
                        editor.text.trim() === '' || Number.isNaN(value) ? null : value,
                      )
                      setEditor(null)
                    }}
                  />
                  <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
                    <button
                      className="btn small destructive"
                      onClick={() => {
                        store.saveNorm(
                          `${editor.transition.fromStep}->${editor.transition.toStep}`,
                          null,
                        )
                        setEditor(null)
                      }}
                    >
                      Clear
                    </button>
                    <button
                      className="btn prominent small"
                      onClick={() => {
                        const value = Number(editor.text.trim())
                        store.saveNorm(
                          `${editor.transition.fromStep}->${editor.transition.toStep}`,
                          editor.text.trim() === '' || Number.isNaN(value) ? null : value,
                        )
                        setEditor(null)
                      }}
                    >
                      Set
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {showGapTable && (
          <div
            style={{
              width: 460,
              flexShrink: 0,
              borderLeft: '1px solid var(--separator)',
              background: 'var(--bg-secondary-grouped)',
              overflow: 'auto',
            }}
          >
            <table className="data-table">
              <thead>
                <tr>
                  <th>From</th>
                  <th>To</th>
                  <th style={{ textAlign: 'right' }}>Actual</th>
                  <th style={{ textAlign: 'right' }}>Norm</th>
                  <th style={{ textAlign: 'right' }}>Delta</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id}>
                    <td>{e.t.fromStep}</td>
                    <td>{e.t.toStep}</td>
                    <td className="num">{formatValue(e.actual)}</td>
                    <td className="num">{e.norm == null ? '—' : formatValue(e.norm)}</td>
                    <td className="num">
                      {e.delta == null ? '—' : formatValue(e.delta)}
                    </td>
                    <td
                      className={
                        e.violation == null
                          ? 'fg-secondary'
                          : e.violation
                            ? 'fg-red'
                            : 'fg-green'
                      }
                    >
                      {e.violation == null
                        ? '— No norm'
                        : e.violation
                          ? '❌ Violation'
                          : '✅ Compliant'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
