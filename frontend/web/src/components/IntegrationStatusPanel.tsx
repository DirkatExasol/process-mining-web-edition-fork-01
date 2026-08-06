/** The abstraction layer's headline panel: the live run state, where an import would
 *  land, and five KPI tiles (the same tiles the main app uses) summarising ingestion
 *  over the recorded history — manual vs watchdog imports, when the last one ran, and
 *  how many events were pushed vs skipped. The most recent run's log lines stay
 *  available underneath. Presentational: the polled status and the run history are
 *  passed in by IntegrationConsole, which also drives the pipeline canvas. */

import { useState } from 'react'
import { IntegrationKpis } from './IntegrationKpis'
import type { PipelineRun } from '../integration/runHistory'
import type { IntegrationStatus } from '../types'

const STATE_STYLE: Record<string, { label: string; color: string }> = {
  idle: { label: 'Idle', color: 'var(--secondary)' },
  running: { label: 'Running', color: 'var(--accent)' },
  completed: { label: 'Completed', color: 'var(--green)' },
  failed: { label: 'Failed', color: 'var(--red)' },
}

export function IntegrationStatusPanel({
  status,
  runs,
  error,
}: {
  status: IntegrationStatus | null
  runs: PipelineRun[]
  error: string | null
}) {
  const state = status ? STATE_STYLE[status.state] ?? STATE_STYLE.idle : STATE_STYLE.idle
  const [showLog, setShowLog] = useState(false)
  const messages = status?.messages ?? []

  return (
    <div className="card" style={{ display: 'block' }}>
      <div className="row" style={{ alignItems: 'center', gap: 10 }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>Abstraction layer</h1>
        <span className="spacer" />
        <span
          className="pill"
          style={{ background: 'color-mix(in srgb, transparent, currentColor 14%)', color: state.color }}
          title="Current run state of the abstraction layer"
        >
          ● {state.label}
        </span>
      </div>

      {/* Where an import lands, kept to one compact line under the title. */}
      <div className="t-caption2 fg-tertiary" style={{ marginTop: 4 }}>
        {status?.activeSchema ? (
          <>
            Target <code>{status.activeSchema}</code>
            {status.connectionName ? ` · ${status.connectionName}` : ''}
          </>
        ) : status?.connected ? (
          'The active connection has no target schema'
        ) : (
          'Pick a connection on the left to choose the target'
        )}
      </div>

      {error && <div className="banner warn" style={{ marginTop: 12 }}>{error}</div>}
      {status?.lastError && (
        <div className="banner warn" style={{ marginTop: 12 }}>
          Last run failed: {status.lastError}
        </div>
      )}

      <div style={{ marginTop: 14 }}>
        <IntegrationKpis runs={runs} status={status} />
      </div>

      {messages.length > 0 && (
        <div className="col" style={{ gap: 6, marginTop: 12 }}>
          <button
            className="btn small"
            style={{ alignSelf: 'flex-start' }}
            onClick={() => setShowLog((v) => !v)}
          >
            {showLog ? '▾' : '▸'} Run log ({messages.length})
          </button>
          {showLog && (
            <div
              className="col"
              style={{
                gap: 2, padding: 10, borderRadius: 8,
                background: 'var(--fill)', maxHeight: 140, overflow: 'auto',
              }}
            >
              {messages.map((m, i) => (
                <span key={i} className="t-caption2 fg-secondary" style={{ fontFamily: 'monospace' }}>
                  {m}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
