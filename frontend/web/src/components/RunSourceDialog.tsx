/** Run a File source's extraction: pick the destination (the currently-connected
 *  database + its schema) and a project id, then push the parsed JOURNEYS events through
 *  the abstraction layer. Progress + the result also show in the status panel. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { Source } from '../types'
import { Sheet } from './ui'

export function RunSourceDialog({
  source,
  onClose,
  onDone,
}: {
  source: Source
  onClose: () => void
  onDone: () => void | Promise<void>
}) {
  const store = useStore()
  const connected = store.connection.isConnected
  const activeConn = store.connections.find((c) => c.id === store.connection.activeProfileId)
  const linked = Boolean((source.config as Record<string, unknown>)?.sourceTypeId)

  const [projectId, setProjectId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ records: number; detail: string } | null>(null)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)

  // While the run is in flight, poll the live status for the progress bar.
  useEffect(() => {
    if (!busy) return
    let alive = true
    const tick = async () => {
      try {
        const s = await api.integrationStatus()
        if (alive && s.state === 'running') setProgress({ done: s.recordsDone, total: s.recordsTotal })
      } catch {
        /* ignore transient poll errors */
      }
    }
    void tick()
    const id = window.setInterval(tick, 350)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [busy])

  const run = async () => {
    if (!projectId.trim()) {
      setError('A project id is required.')
      return
    }
    setBusy(true)
    setError(null)
    setProgress({ done: 0, total: 0 })
    try {
      const r = await api.runSource(source.id, projectId.trim())
      setResult(r)
      await onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const footer = (
    <>
      <span className="spacer" />
      <button className="btn" onClick={onClose} disabled={busy}>
        {result ? 'Close' : 'Cancel'}
      </button>
      {!result && (
        <button
          className="btn prominent"
          onClick={() => void run()}
          disabled={busy || !connected || !linked}
        >
          {busy ? 'Running…' : '▷ Run extraction'}
        </button>
      )}
    </>
  )

  return (
    <Sheet title={`Run “${source.name}”`} icon="▷" onClose={onClose} footer={footer}>
      <div className="iwiz-col narrow">
      <div className="col" style={{ gap: 6 }}>
        <span className="t-caption fg-secondary">Destination</span>
        {connected ? (
          <span className="t-body">
            {activeConn?.name ?? 'Active connection'} — writes to its configured schema
          </span>
        ) : (
          <div className="banner warn">
            Connect to a destination database in the Connections section first.
          </div>
        )}
      </div>

      {!linked && (
        <div className="banner warn">
          This source has no source type linked — edit it and pick one so the lines can be parsed.
        </div>
      )}

      <label className="col" style={{ gap: 4 }}>
        <span className="t-caption fg-secondary">Project id</span>
        <input
          className="text-input"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          placeholder="e.g. RETAIL-DEMO"
          autoFocus
        />
        <span className="t-caption2 fg-tertiary">Written into JOURNEYS.PROJECT_ID for every event.</span>
      </label>

      {busy && (
        <div className="col" style={{ gap: 4 }}>
          <div className="iprogress-track">
            <div
              className={`iprogress-fill${progress && progress.total > 0 ? '' : ' indeterminate'}`}
              style={progress && progress.total > 0
                ? { width: `${Math.min(100, (progress.done / progress.total) * 100)}%` }
                : undefined}
            />
          </div>
          <span className="t-caption2 fg-secondary">
            {progress && progress.total > 0
              ? `Importing ${progress.done.toLocaleString()} / ${progress.total.toLocaleString()} log records…`
              : 'Reading the file…'}
          </span>
        </div>
      )}

      {result &&
        (result.records > 0 ? (
          <div className="t-caption" style={{ color: 'var(--green)' }}>✓ {result.detail}</div>
        ) : (
          <div className="banner warn">
            ⚠ {result.detail}. No line matched — check the linked source type's regexes fit
            this file's format (edit the source type and test against a sample line).
          </div>
        ))}
      {error && <div className="t-caption fg-red">{error}</div>}
      </div>
    </Sheet>
  )
}
