/** WorkBench Mobile — the phone-only shell (iPhone / Android handset). It reuses the same
 *  Zustand store and the existing view components, and only reorganises the chrome for a small
 *  touch screen: a top bar with a ☰ hamburger (opens the controls as a slide-over drawer
 *  instead of a fixed sidebar), a view switcher (bottom sheet), and a full-screen view area.
 *
 *  Supported views on a phone: Dashboard, A-Chart, Individual Journey, Notes, AI supported
 *  Documentation. Any other mode (A/B Comparison, B-Chart, Statistics, Conformance, Happy Path,
 *  Simulation) redirects to the Dashboard with a short note — those are desktop/tablet only.
 *  Works in portrait and landscape. iPads/tablets never reach this shell (see device.ts). */

import { useEffect, useRef, useState } from 'react'
import { AutoRefreshController } from '../components/AutoRefresh'
import { JourneyKpiStrip, KpiStrip } from '../components/KpiStrip'
import { Sidebar } from '../components/Sidebar'
import { Chevron, Unavailable } from '../components/ui'
import { useSetting } from '../settings'
import { useStore } from '../store'
import { VIEW_MODE_ICONS, type DetailViewMode } from '../types'
import { AIDocumentationView } from '../views/AIDocumentationView'
import { ChartView } from '../views/ChartView'
import { DashboardView } from '../views/DashboardView'
import { IndividualJourneyView } from '../views/DetailPane'
import { NotesView } from '../views/NotesView'

/** The view modes WorkBench Mobile can show on a phone. */
const MOBILE_MODES: DetailViewMode[] = [
  'Dashboard',
  'A-Chart',
  'Individual Journey',
  'Notes',
  'AI supported Documentation',
]

const STYLE = `
.mwb{display:flex;flex-direction:column;height:100%;min-height:0;background:var(--bg);color:var(--primary)}
.mwb-top{display:flex;align-items:center;gap:8px;padding:8px 10px;
  border-bottom:1px solid var(--separator);background:var(--bg-elevated);flex:none}
.mwb-ic{width:38px;height:38px;flex:none;display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--separator);background:var(--bg-fill);color:var(--primary);border-radius:10px;
  font-size:17px;cursor:pointer}
.mwb-ic:active{background:var(--bg-fill-strong)}
.mwb-ttl{flex:1;min-width:0;display:flex;flex-direction:column;line-height:1.15}
.mwb-ttl .nm{font-size:14px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mwb-ttl .md{font-size:11px;color:var(--secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mwb-note{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:12.5px;flex:none;
  background:var(--accent-soft);border-bottom:1px solid var(--accent-border);color:var(--primary)}
.mwb-note button{margin-left:auto;border:none;background:none;color:var(--accent);font-weight:700;cursor:pointer;font-size:14px}
.mwb-kpi-handle{display:flex;align-items:center;gap:8px;padding:5px 12px;font-size:12px;color:var(--secondary);
  border-bottom:1px solid var(--separator);background:var(--bg-elevated);cursor:pointer;flex:none}
.mwb-body{flex:1;min-height:0;display:flex;flex-direction:column;position:relative;overflow:hidden}
/* Slide-over drawer (the hamburger). Full-height, from the left, over a scrim. */
.mwb-scrim{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:300}
.mwb-drawer{position:fixed;top:0;left:0;bottom:0;width:min(86vw,360px);z-index:301;
  background:var(--bg);box-shadow:2px 0 16px rgba(0,0,0,.25);display:flex;flex-direction:column;
  animation:mwb-slide .18s ease-out}
@keyframes mwb-slide{from{transform:translateX(-100%)}to{transform:translateX(0)}}
/* The reused Sidebar fills the drawer (its fixed desktop width is overridden here). */
.mwb-drawer .sidebar{width:100%;min-width:0;max-width:none;height:100%;border:none}
/* Bottom sheet for the view switcher. */
.mwb-sheet{position:fixed;left:0;right:0;bottom:0;z-index:301;background:var(--bg-elevated);
  border-top-left-radius:16px;border-top-right-radius:16px;box-shadow:0 -6px 24px rgba(0,0,0,.2);
  padding:8px 8px calc(8px + env(safe-area-inset-bottom));animation:mwb-up .18s ease-out}
@keyframes mwb-up{from{transform:translateY(100%)}to{transform:translateY(0)}}
.mwb-sheet-h{font-size:11px;font-weight:700;color:var(--secondary);text-transform:uppercase;
  letter-spacing:.03em;padding:8px 12px 4px}
.mwb-vitem{display:flex;align-items:center;gap:12px;width:100%;text-align:left;border:none;
  background:none;color:var(--primary);font-size:15px;padding:12px;border-radius:10px;cursor:pointer}
.mwb-vitem:active{background:var(--bg-fill)}
.mwb-vitem.sel{background:var(--accent-soft)}
.mwb-vitem .ic{width:22px;text-align:center}
.mwb-vitem .sp{flex:1}
`

export function MobileWorkbench({ onShowHelp }: { onShowHelp: () => void }) {
  const store = useStore()
  const [drawer, setDrawer] = useState(false)
  const [sheet, setSheet] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [kpiExpanded, setKpiExpanded] = useSetting<boolean>('processmap.kpiExpanded')
  const noteTimer = useRef<number | undefined>(undefined)

  const mode = store.activeChartMode
  const connected = store.connection.isConnected && store.selectedProject != null

  // Redirect any desktop-only view to the Dashboard with a note. Runs whenever the mode lands
  // on something this shell can't show (e.g. a resumed session, or a deep link).
  useEffect(() => {
    if (MOBILE_MODES.includes(mode)) return
    const label = mode
    store.switchChartMode('Dashboard')
    setNote(`“${label}” isn’t available on mobile — open it on a larger screen.`)
    window.clearTimeout(noteTimer.current)
    noteTimer.current = window.setTimeout(() => setNote(null), 6000)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  const pickView = (m: DetailViewMode) => {
    setSheet(false)
    if (m !== mode) store.switchChartMode(m)
  }

  // The collapsible KPI strip, shown only where it is meaningful (A-Chart / Individual Journey).
  const showKpi =
    connected &&
    ((mode === 'A-Chart' && store.processGraph.transitions.length > 0) ||
      (mode === 'Individual Journey' && store.journeyDate != null))

  return (
    <div className="mwb">
      <style>{STYLE}</style>
      <header className="mwb-top">
        <button className="mwb-ic" onClick={() => setDrawer(true)} aria-label="Open controls" title="Controls">
          ☰
        </button>
        <div className="mwb-ttl">
          <span className="nm">
            {store.selectedProject?.title ?? (mode === 'Dashboard' ? 'Dashboard' : 'Process Mining')}
          </span>
          <span className="md">{mode}</span>
        </div>
        <button className="mwb-ic" onClick={() => setSheet(true)} aria-label="Switch view" title="Switch view">
          {VIEW_MODE_ICONS[mode] ?? '☷'}
        </button>
        <button className="mwb-ic" onClick={onShowHelp} aria-label="Help" title="Help">
          ？
        </button>
      </header>

      {note && (
        <div className="mwb-note" role="status">
          <span>{note}</span>
          <button onClick={() => setNote(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      {showKpi && (
        <button className="mwb-kpi-handle" onClick={() => setKpiExpanded(!kpiExpanded)}>
          <Chevron open={kpiExpanded} />
          {!kpiExpanded && store.journeyCount != null ? (
            <span>
              {store.journeyCount.toLocaleString()}
              {store.totalJourneyCount != null && ` / ${store.totalJourneyCount.toLocaleString()}`} Journeys
            </span>
          ) : (
            <span>Key figures</span>
          )}
        </button>
      )}
      {showKpi && kpiExpanded && (
        mode === 'Individual Journey' ? (
          <JourneyKpiStrip />
        ) : (
          <KpiStrip
            side="a"
            graph={store.processGraph}
            journeyCount={store.journeyCount}
            durations={store.durations}
            goodness={store.processGoodnessScore}
            loading={store.isLoading}
          />
        )
      )}

      <main className="mwb-body">
        <MobileActiveView />
      </main>
      {/* Keep the A-Chart auto-refresh schedule alive across drawer/sheet toggles. */}
      <AutoRefreshController />

      {drawer && (
        <>
          <div className="mwb-scrim" onClick={() => setDrawer(false)} />
          <div className="mwb-drawer" role="dialog" aria-label="Controls">
            <Sidebar onCollapse={() => setDrawer(false)} />
          </div>
        </>
      )}

      {sheet && (
        <>
          <div className="mwb-scrim" onClick={() => setSheet(false)} />
          <div className="mwb-sheet" role="dialog" aria-label="Switch view">
            <div className="mwb-sheet-h">View</div>
            {MOBILE_MODES.map((m) => (
              <button key={m} className={`mwb-vitem${m === mode ? ' sel' : ''}`} onClick={() => pickView(m)}>
                <span className="ic" aria-hidden>
                  {VIEW_MODE_ICONS[m]}
                </span>
                <span className="sp">{m}</span>
                {m === mode && <span className="fg-accent">✓</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

/** Renders the active view — only the phone-supported modes; others never reach here because
 *  the redirect effect above sends them to the Dashboard. */
function MobileActiveView() {
  const store = useStore()
  const mode = store.activeChartMode

  if (mode === 'Dashboard') return <DashboardView />

  if (!store.connection.isConnected) {
    return (
      <Unavailable
        glyph="⛁"
        title="Not Connected"
        description="Open the ☰ menu and pick a connection and process to begin."
      />
    )
  }

  switch (mode) {
    case 'A-Chart':
      return <ChartView side="a" />
    case 'Individual Journey':
      return <IndividualJourneyView />
    case 'Notes':
      return <NotesView />
    case 'AI supported Documentation':
      return <AIDocumentationView />
    default:
      return <DashboardView />
  }
}
