/** Ingestion run history for the integration console. The layer's live `/status` only
 *  ever reflects the most recent run, so this hook accumulates each run into a persisted
 *  list — the console keeps every past flowchart, showing the ingestion behaviour over
 *  time, until the user clears it. Persisted in localStorage (per user) so it survives
 *  reloads and even a backend restart (which resets the in-memory status to idle). */

import { useCallback, useEffect, useState } from 'react'
import { useStore } from '../store'
import type { IntegrationStatus } from '../types'
import type { PipelineView } from '../components/IntegrationPipeline'

/** A frozen snapshot of one ingestion run — a superset of what the pipeline canvas
 *  needs (PipelineView) plus timing for the history header. */
export interface PipelineRun extends PipelineView {
  key: string // startedAt — identifies the run across polls
  extractorName: string | null
  startedAt: string | null
  finishedAt: string | null
  /** What started this run — drives the manual-vs-watchdog KPI split. */
  trigger: 'manual' | 'watchdog' | ''
  /** Journey events written vs. source items skipped (not the metadata rows). */
  eventsWritten: number
  eventsSkipped: number
}

const MAX_RUNS = 50
const keyFor = (user: string) => `pmw.integration.runHistory.${user}`

function load(user: string): PipelineRun[] {
  try {
    const raw = localStorage.getItem(keyFor(user))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function save(user: string, runs: PipelineRun[]): void {
  try {
    localStorage.setItem(keyFor(user), JSON.stringify(runs))
  } catch {
    /* quota / disabled storage — history just won't persist */
  }
}

function toRun(s: IntegrationStatus): PipelineRun {
  return {
    key: s.startedAt ?? '',
    state: s.state === 'idle' ? 'completed' : s.state,
    sourceName: s.sourceName,
    sourceTypeName: s.sourceTypeName,
    extractorName: s.extractorName,
    connectionName: s.connectionName,
    connectionId: s.connectionId,
    schema: s.schema,
    recordsPushed: s.recordsPushed ?? 0,
    recordsDone: s.recordsDone ?? 0,
    recordsTotal: s.recordsTotal ?? 0,
    lastError: s.lastError,
    startedAt: s.startedAt,
    finishedAt: s.finishedAt,
    trigger: s.trigger ?? '',
    eventsWritten: s.eventsWritten ?? 0,
    eventsSkipped: s.eventsSkipped ?? 0,
  }
}

export function useRunHistory(status: IntegrationStatus | null) {
  const user = useStore((s) => s.authUser) ?? ''
  const [runs, setRuns] = useState<PipelineRun[]>(() => load(user))

  // Reload when the signed-in user changes (different history).
  useEffect(() => {
    setRuns(load(user))
  }, [user])

  // Fold the latest status into the history: update the newest entry in place while
  // a run is in flight (same startedAt), or prepend a new one. Only runs that have
  // actually started (startedAt set) are recorded.
  useEffect(() => {
    if (!status?.startedAt) return
    if (status.state === 'idle') return
    const snap = toRun(status)
    setRuns((prev) => {
      const next =
        prev[0]?.key === snap.key
          ? [snap, ...prev.slice(1)]
          : [snap, ...prev].slice(0, MAX_RUNS)
      save(user, next)
      return next
    })
  }, [status, user])

  const clear = useCallback(() => {
    setRuns([])
    save(user, [])
  }, [user])

  return { runs, clear, atCap: runs.length >= MAX_RUNS }
}
