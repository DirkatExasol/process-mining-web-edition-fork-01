/** A-Chart auto-refresh. An always-mounted timer (survives collapsing the sidebar/panel)
 *  drives the reload; the interval is chosen in Configuration → Auto-refresh, while the live
 *  controls — the countdown ring and the Refresh-now button — float IN the A-Chart window
 *  whenever an interval is configured. Active ONLY in A-Chart.
 *
 *  Reloading goes through store.autoRefreshReload, which first slides the date window forward
 *  to "now" when it ends in the past — so journeys that arrived after the last load actually
 *  appear (a plain reload kept the old window and missed them). */

import { useEffect, useState } from 'react'
import { useSetting } from '../settings'
import { useStore } from '../store'

export const REFRESH_OPTIONS = [
  { value: 0, label: 'Off' },
  { value: 10, label: '10s' },
  { value: 30, label: '30s' },
  { value: 60, label: '1m' },
  { value: 120, label: '2m' },
  { value: 300, label: '5m' },
]

function kickReload() {
  void useStore.getState().autoRefreshReload()
  // Bump the kick so the controller reschedules the countdown from now.
  useStore.setState({ autoRefreshKick: useStore.getState().autoRefreshKick + 1 })
}

/** Drives the auto-refresh timer from the store + setting; renders nothing. Mounted once in
 *  the workbench (not inside the collapsible Config panel), so the schedule keeps running
 *  regardless of which sidebar section is open. Goes idle outside A-Chart. */
export function AutoRefreshController() {
  const mode = useStore((s) => s.activeChartMode)
  const connected = useStore((s) => s.connection.isConnected && s.selectedProject != null)
  const kick = useStore((s) => s.autoRefreshKick)
  const [secs] = useSetting<number>('achart.autoRefreshSecs')

  useEffect(() => {
    if (mode !== 'A-Chart' || !secs || secs <= 0 || !connected) {
      useStore.setState({ autoRefreshNextAt: null })
      return
    }
    useStore.setState({ autoRefreshNextAt: Date.now() + secs * 1000 })
    const id = window.setInterval(() => {
      void useStore.getState().autoRefreshReload()
      useStore.setState({ autoRefreshNextAt: Date.now() + secs * 1000 })
    }, secs * 1000)
    return () => {
      window.clearInterval(id)
      useStore.setState({ autoRefreshNextAt: null })
    }
  }, [mode, connected, secs, kick])

  return null
}

/** Circular countdown to the next refresh. Ticks locally (~5 fps); reads the target time
 *  from the store, which the controller updates each cycle. */
export function RefreshRing({ secs }: { secs: number }) {
  const nextAt = useStore((s) => s.autoRefreshNextAt)
  const [, force] = useState(0)
  useEffect(() => {
    if (!nextAt) return
    const id = window.setInterval(() => force((x) => (x + 1) % 1_000_000), 200)
    return () => window.clearInterval(id)
  }, [nextAt])

  const size = 24
  const r = 9
  const circ = 2 * Math.PI * r
  if (!secs || !nextAt) return null
  const remaining = Math.max(0, (nextAt - Date.now()) / 1000)
  const frac = Math.max(0, Math.min(1, remaining / secs))
  return (
    <span className="ar-ring" title={`Next refresh in ${Math.ceil(remaining)} s`} aria-hidden>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="ar-track" cx={size / 2} cy={size / 2} r={r} />
        <circle
          className="ar-prog"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - frac)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="ar-count">{Math.ceil(remaining)}</span>
    </span>
  )
}

/** The A-Chart auto-refresh pill: the countdown ring + a Refresh button. Shown only when an
 *  interval is configured; it sits in the A-Chart's control cluster, between the ▦ Transitions
 *  button and the zoom controls (rendered by FlowChart). */
export function AutoRefreshOverlay() {
  const [secs] = useSetting<number>('achart.autoRefreshSecs')
  if (!secs || secs <= 0) return null
  return (
    <div className="ar-pill" role="group" aria-label="Auto-refresh">
      <RefreshRing secs={secs} />
      <button className="ar-now" onClick={kickReload} title="Reload the A-Chart now">
        ↻ Refresh
      </button>
    </div>
  )
}

/** The Configuration-panel UI (shown only in A-Chart): the interval dropdown. The live
 *  indicator + Refresh button live in the A-Chart itself (AutoRefreshOverlay). */
export function AutoRefreshConfig() {
  const [secs, setSecs] = useSetting<number>('achart.autoRefreshSecs')
  return (
    <div className="col" style={{ padding: '8px 20px', gap: 6 }}>
      <div className="row" style={{ gap: 10, alignItems: 'center' }}>
        <span aria-hidden className="fg-secondary">
          ↻
        </span>
        <span className="t-caption fg-secondary spacer">Refresh every</span>
        <select
          className="text-input"
          style={{ width: 82 }}
          value={secs}
          onChange={(e) => setSecs(Number(e.target.value))}
          aria-label="Auto-refresh interval"
        >
          {REFRESH_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <span className="t-caption2 fg-tertiary">
        {secs > 0
          ? 'A countdown and a Refresh button appear on the A-Chart. The window follows "now" so new journeys show.'
          : 'Reloads the A-Chart on a timer. The controls appear on the chart when on.'}
      </span>
    </div>
  )
}
