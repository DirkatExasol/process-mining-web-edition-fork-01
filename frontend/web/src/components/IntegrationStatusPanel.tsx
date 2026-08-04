/** Live status of the integration abstraction layer: current run state, the target
 *  schema an extraction would land in, how many extractors are plugged in, and the
 *  most recent run's progress. Polls `/api/integration/status` (+ the extractor
 *  list). Extractor selection / triggering a run is a later stage. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { ExtractorInfo, IntegrationStatus } from '../types'

const STATE_STYLE: Record<string, { label: string; color: string }> = {
  idle: { label: 'Idle', color: 'var(--secondary)' },
  running: { label: 'Running', color: 'var(--accent)' },
  completed: { label: 'Completed', color: 'var(--green)' },
  failed: { label: 'Failed', color: 'var(--red)' },
}

export function IntegrationStatusPanel() {
  const store = useStore()
  const [status, setStatus] = useState<IntegrationStatus | null>(null)
  const [extractors, setExtractors] = useState<ExtractorInfo[]>([])
  const [error, setError] = useState<string | null>(null)

  // Poll while mounted; also re-poll immediately when the active connection changes
  // (the target schema follows it).
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const [s, e] = await Promise.all([api.integrationStatus(), api.integrationExtractors()])
        if (!alive) return
        setStatus(s)
        setExtractors(e)
        setError(null)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : String(err))
      }
    }
    void tick()
    const id = window.setInterval(tick, 4000)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [store.connection.isConnected, store.connection.activeProfileId])

  const state = status ? STATE_STYLE[status.state] ?? STATE_STYLE.idle : STATE_STYLE.idle

  return (
    <div className="col" style={{ gap: 16, width: '100%', maxWidth: 640 }}>
      <div className="card" style={{ display: 'block' }}>
        <div className="row" style={{ alignItems: 'center', gap: 10, marginBottom: 12 }}>
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

        {error && <div className="banner warn" style={{ marginBottom: 12 }}>{error}</div>}

        <div className="col" style={{ gap: 8 }}>
          <StatRow label="Target schema">
            {status?.activeSchema ? (
              <code>{status.activeSchema}</code>
            ) : (
              <span className="fg-tertiary">
                {status?.connected ? '(connection has no schema)' : 'Pick a connection on the left'}
              </span>
            )}
          </StatRow>
          <StatRow label="Registered extractors">
            {status ? status.registeredExtractors : '—'}
          </StatRow>
          {status && status.state !== 'idle' && (
            <>
              <StatRow label="Extractor">{status.extractorName ?? status.extractorId ?? '—'}</StatRow>
              <StatRow label="Records pushed">{status.recordsPushed.toLocaleString()}</StatRow>
              {status.tablesTouched.length > 0 && (
                <StatRow label="Tables">{status.tablesTouched.join(', ')}</StatRow>
              )}
              {status.finishedAt && <StatRow label="Finished">{status.finishedAt}</StatRow>}
              {status.lastError && (
                <StatRow label="Error">
                  <span className="fg-red">{status.lastError}</span>
                </StatRow>
              )}
            </>
          )}
        </div>

        {status && status.messages.length > 0 && (
          <div
            className="col"
            style={{
              gap: 2, marginTop: 12, padding: 10, borderRadius: 8,
              background: 'var(--fill)', maxHeight: 140, overflow: 'auto',
            }}
          >
            {status.messages.map((m, i) => (
              <span key={i} className="t-caption2 fg-secondary" style={{ fontFamily: 'monospace' }}>
                {m}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{ display: 'block' }}>
        <h2 style={{ marginTop: 0, fontSize: 15 }}>Extractors</h2>
        {extractors.length === 0 ? (
          <p className="fg-secondary" style={{ margin: 0 }}>
            No extractors are plugged in yet. The first extractor and the controls to run
            one are coming next — this panel already reflects the layer’s live status.
          </p>
        ) : (
          <div className="col" style={{ gap: 8 }}>
            {extractors.map((e) => (
              <div key={e.id} className="row" style={{ gap: 8, alignItems: 'baseline' }}>
                <strong>{e.name}</strong>
                <span className="t-caption2 fg-tertiary">v{e.version}</span>
                <span className="t-caption fg-secondary">{e.description}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="row" style={{ gap: 10, alignItems: 'baseline' }}>
      <span className="t-caption fg-tertiary" style={{ minWidth: 150 }}>
        {label}
      </span>
      <span className="t-body">{children}</span>
    </div>
  )
}
