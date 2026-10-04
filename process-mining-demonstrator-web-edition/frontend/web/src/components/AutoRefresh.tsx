/** A-Chart auto-refresh: an always-mounted timer (so it survives collapsing the sidebar or
 *  the Configuration panel) plus the Configuration-panel controls — an interval dropdown, a
 *  "Refresh now" button and a circular countdown to the next refresh. Active ONLY in A-Chart. */

import { useEffect, useState } from 'react'
import { useSetting } from '../settings'
import { useStore } from '../store'

export const REFRESH_OPTIONS = [
  { value: 0, label: 'Off' },
  { value: 5, label: '5s' },
  { value: 10, label: '10s' },
  { value: 30, label: '30s' },
  { value: 60, label: '1m' },
  { value: 120, label: '2m' },
  { value: 300, label: '5m' },
]

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
      void useStore.getState().reloadGraph()
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
function RefreshRing({ secs }: { secs: number }) {
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

/** The Configuration-panel UI (shown only in A-Chart): interval dropdown + Refresh now + ring. */
export function AutoRefreshConfig() {
  const [secs, setSecs] = useSetting<number>('achart.autoRefreshSecs')
  const store = useStore()
  const canRefresh = store.connection.isConnected && store.selectedProject != null

  return (
    <div className="col" style={{ padding: '8px 20px', gap: 8 }}>
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
        <RefreshRing secs={secs} />
      </div>
      <div className="row" style={{ gap: 10, alignItems: 'center' }}>
        <button
          className="btn small"
          disabled={!canRefresh}
          onClick={() => {
            void store.reloadGraph()
            // Bump the kick so the controller reschedules the countdown from now.
            useStore.setState({ autoRefreshKick: useStore.getState().autoRefreshKick + 1 })
          }}
        >
          ↻ Refresh now
        </button>
        <span className="t-caption2 fg-tertiary spacer">
          {secs > 0 ? 'Reloads the A-Chart on the interval.' : 'Manual refresh only (auto is off).'}
        </span>
      </div>
    </div>
  )
}
