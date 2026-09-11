/** Number, duration and date formatting ported from the Swift views. */

/** `FlowChartView.formatCount` — 1234 → "1.2k". */
export function formatCount(n: number): string {
  if (n < 1_000) return `${n}`
  if (n < 1_000_000) return `${(n / 1_000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}

/** `FlowChartView.formatDuration` — edge labels. */
/** A share as a percent label: whole-number at ≥10 %, one decimal below (so a small
 *  journey share reads "3.5%" / "0.4%" rather than collapsing to "0%"). */
export function formatPercent(value: number): string {
  return value >= 10 ? `${Math.round(value)}%` : `${value.toFixed(1)}%`
}

export function formatDuration(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  if (secs < 86400) return `${(secs / 3600).toFixed(1)}h`
  return `${(secs / 86400).toFixed(1)}d`
}

/** `SidebarView.formatSecs` — filter chips and sliders. */
export function formatSecs(secs: number): string {
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  if (secs < 86400) return `${h}h ${m}m`
  const d = Math.floor(secs / 86400)
  const rh = Math.floor((secs % 86400) / 3600)
  return `${d}d ${rh}h`
}

/** KPI tiles show durations at a coarser granularity. */
export function formatDurationLong(secs: number | null | undefined): string {
  if (secs == null || !Number.isFinite(secs)) return '—'
  if (secs < 60) return `${Math.round(secs)} s`
  if (secs < 3600) return `${(secs / 60).toFixed(1)} min`
  if (secs < 86400) return `${(secs / 3600).toFixed(1)} h`
  return `${(secs / 86400).toFixed(1)} d`
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return n.toLocaleString()
}

export function formatScore(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

/** yyyy-MM-dd, the format the API and `<input type="date">` both use. */
export function toISODate(date: Date | string | null | undefined): string {
  if (!date) return ''
  const d = typeof date === 'string' ? new Date(date) : date
  if (Number.isNaN(d.getTime())) return ''
  const pad = (v: number) => String(v).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function fromISODate(value: string): Date | null {
  if (!value) return null
  const d = new Date(`${value}T00:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDateShort(date: string | Date | null | undefined): string {
  if (!date) return '—'
  const d = typeof date === 'string' ? new Date(date) : date
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatDateTime(date: string | Date | null | undefined): string {
  if (!date) return '—'
  const d = typeof date === 'string' ? new Date(date) : date
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Time-only, monospaced — used inside Individual Journey nodes. */
export function formatTimeOnly(date: string | Date | null | undefined): string {
  if (!date) return ''
  const d = typeof date === 'string' ? new Date(date) : date
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString(undefined, { hour12: false })
}

export function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / 86_400_000)
}

export function addDays(date: Date, days: number): Date {
  const copy = new Date(date)
  copy.setDate(copy.getDate() + days)
  return copy
}
