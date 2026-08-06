/** Ingestion KPI tiles — the same visual language as the main app's KPI strip
 *  (KpiTile), driven by the persisted run history rather than one live status. The
 *  counts therefore describe the whole recorded period ("behaviour over time"), and
 *  reset with the ↻ Clear button that clears the history. */

import { KpiTile } from './KpiStrip'
import type { PipelineRun } from '../integration/runHistory'
import type { IntegrationStatus } from '../types'

/** Compact relative age ("just now", "12m ago", "3d ago") plus the absolute time as
 *  a tooltip — a KPI tile has room for one short line only. */
export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const secs = Math.max(0, Math.round((now - t) / 1000))
  if (secs < 45) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function IntegrationKpis({
  runs,
  status,
}: {
  runs: PipelineRun[]
  status: IntegrationStatus | null
}) {
  const manual = runs.filter((r) => r.trigger === 'manual').length
  const watchdog = runs.filter((r) => r.trigger === 'watchdog').length
  const written = runs.reduce((sum, r) => sum + (r.eventsWritten || 0), 0)
  const skipped = runs.reduce((sum, r) => sum + (r.eventsSkipped || 0), 0)
  // runs[0] is the newest; prefer its finish time, falling back to its start.
  const last = runs[0]?.finishedAt ?? runs[0]?.startedAt ?? null
  const running = status?.state === 'running'

  // Tolerate a status payload without the newer fields (an older backend, or the brief
  // window during a rolling deploy) rather than crashing the whole console on it.
  const n = (v: number | undefined | null) => (v ?? 0).toLocaleString()

  return (
    <div className="kpi-strip ikpi-strip">
      <KpiTile label="Manual imports" icon="▷" value={n(manual)} />
      <KpiTile label="Watchdog imports" icon="👁" value={n(watchdog)} />
      <KpiTile
        label={status && !status.watchdogEnabled ? 'Watchdogs (off)' : 'Watchdogs active'}
        icon="🐕"
        value={status ? `${n(status.watchdogsActive)} / ${n(status.watchdogsTotal)}` : '—'}
        // Green while at least one is watching; orange when the whole loop is disabled
        // for the deployment, since an "on" watchdog then never actually polls.
        color={
          status && !status.watchdogEnabled
            ? 'var(--orange)'
            : status && status.watchdogsActive > 0
              ? 'var(--green)'
              : undefined
        }
      />
      <KpiTile
        label="Last import"
        icon="🕒"
        value={running ? 'running…' : relativeTime(last)}
        color={running ? 'var(--accent)' : undefined}
      />
      <KpiTile label="Events pushed" icon="▦" value={n(written)} color="var(--green)" />
      <KpiTile
        label="Events skipped"
        icon="⊘"
        value={n(skipped)}
        // Skipped events usually mean the source type's regexes don't fit the log, so
        // call attention to a non-zero count instead of letting it read as normal.
        color={skipped > 0 ? 'var(--orange)' : undefined}
      />
    </div>
  )
}
