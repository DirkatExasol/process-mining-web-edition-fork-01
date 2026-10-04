/** The Dashboard — the landing surface on a direct login (a process launched from /home
 *  jumps straight to its map instead). A cross-connection overview of every process visible
 *  to the user: one card per process with its event count, last-ingest time and a weekly
 *  ingest sparkline, plus an overall card (processes / connections / total events). Clicking
 *  a process connects to it and opens its A-Chart. Users can add up to three extra metrics,
 *  shown on every card and reorderable; the choice is stored per user. */

import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Unavailable } from '../components/ui'
import { relativeTime } from '../components/IntegrationKpis'
import { Sparkline } from '../components/Sparkline'
import { useSetting } from '../settings'
import { useStore } from '../store'
import {
  DASHBOARD_METRICS,
  DASHBOARD_METRIC_LABELS,
  NOTE_SEVERITIES,
  type AssignedConnection,
  type DashboardConnection,
  type DashboardMetric,
  type DashboardProcess,
} from '../types'

const STYLE = `
.dash{flex:1;min-height:0;overflow:auto;padding:14px 16px 24px;color:var(--primary)}
.dash-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin-bottom:10px}
.dash-h1{font-size:18px;font-weight:800;letter-spacing:-.01em;margin:0}
.dash-sub{color:var(--secondary);font-size:12px;margin:0}
.dash-tools{margin-left:auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.dash-tools .lbl{font-size:11.5px;color:var(--secondary)}
.dash-chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--separator);
  background:var(--bg-fill);border-radius:999px;padding:3px 9px;font-size:11.5px;cursor:pointer;
  color:var(--primary);transition:background .15s,border-color .15s}
.dash-chip:hover{background:var(--bg-fill-strong)}
.dash-chip.on{border-color:var(--accent-border);background:var(--accent-soft)}
.dash-chip[disabled]{opacity:.4;cursor:not-allowed}
.dash-chip .mv{border:none;background:none;cursor:pointer;color:var(--secondary);font-size:10px;padding:0 1px;line-height:1}
.dash-chip .mv:hover{color:var(--primary)}
/* Overview = a compact full-width strip, not a grid cell (no wasted row space). */
.dash-overview{display:flex;align-items:center;gap:18px;flex-wrap:wrap;
  border:1px solid var(--accent-border);background:var(--accent-soft);
  border-radius:var(--radius);padding:9px 14px;margin-bottom:6px}
.dash-ostats{display:flex;align-items:center;gap:20px}
.dash-ostat{display:flex;flex-direction:column;line-height:1.1}
.dash-ov{font-size:18px;font-weight:800}
.dash-ol{font-size:10px;color:var(--secondary);text-transform:uppercase;letter-spacing:.04em}
.dash-ospark{margin-left:auto;display:flex;align-items:center;gap:8px}
.dash-ospark .cap{font-size:10px;color:var(--secondary);white-space:nowrap}
.dash-ospark .spark{width:min(220px,42vw);flex:none}
/* Wide, flat cards (landscape rectangles, not squares) pack more rows in less height. */
.dash-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:9px;margin-top:7px}
.dash-group{margin-top:12px}
.dash-ghead{display:flex;align-items:center;gap:9px;margin-bottom:0}
.dash-gname{font-size:12.5px;font-weight:700}
.dash-gschema{font:700 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  border:1px solid var(--separator);border-radius:999px;padding:2px 8px}
.dash-gline{flex:1;height:1px;background:var(--separator-soft)}
.dash-gerr{color:var(--orange);font-size:12px;padding:3px 0}
.dash-card{display:flex;flex-direction:row;align-items:center;gap:12px;border:1px solid var(--separator);
  border-left-width:3px;border-radius:var(--radius);background:var(--bg-elevated);box-shadow:var(--shadow-sm);
  padding:8px 11px 8px 9px;text-align:left;cursor:pointer;color:var(--primary);width:100%;
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}
.dash-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-md)}
.dash-card:disabled{cursor:progress;opacity:.75}
.dash-cmain{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}
.dash-ctop{display:flex;align-items:baseline;gap:8px}
.dash-cname{font-size:13px;font-weight:700;letter-spacing:-.01em;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dash-ccode{margin-left:auto;font:600 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--secondary);border:1px solid var(--separator);border-radius:5px;padding:2px 5px;white-space:nowrap}
.dash-metrics{display:flex;flex-wrap:wrap;gap:2px 14px}
.dash-metric{display:flex;align-items:baseline;gap:4px}
.dash-mv{font-size:13px;font-weight:700;line-height:1.2}
.dash-ml{font-size:9.5px;color:var(--secondary);text-transform:uppercase;letter-spacing:.02em}
.dash-notes{display:inline-flex;align-items:center;gap:7px}
.dash-notes .note-sev{display:inline-flex;align-items:center;gap:3px}
.dash-notes .note-sev .dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dash-notes0{color:var(--secondary)}
.dash-spark{width:116px;flex:none;align-self:stretch;display:flex;align-items:center}
.dash-spark .spark{width:116px}
.spark{display:block}
.spark .spark-base{stroke:var(--separator-soft);stroke-width:1;vector-effect:non-scaling-stroke}
.spark .spark-area{fill:var(--accent-soft);stroke:none}
.spark .spark-line{stroke:var(--accent);stroke-width:1.6;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.spark .spark-gap{stroke:var(--tertiary);stroke-width:1.4;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
.spark .spark-dot{fill:var(--accent)}
`

function daysBetween(aIso: string | null, bMs: number): number | null {
  if (!aIso) return null
  const t = Date.parse(aIso)
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.round((bMs - t) / 86_400_000))
}

function spanDays(firstIso: string | null, lastIso: string | null): number | null {
  if (!firstIso || !lastIso) return null
  const a = Date.parse(firstIso)
  const b = Date.parse(lastIso)
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  return Math.max(0, Math.round((b - a) / 86_400_000))
}

// A distinct pastel per connection group — the schema badge is tinted with it and each of
// the group's cards gets a matching coloured left edge, so groups read apart at a glance.
const GROUP_HUES = ['#3a9bff', '#30c48d', '#ff9f43', '#a66cff', '#ff6b8b', '#2bb9d4', '#e0b000', '#6b7bff']
const hexA = (hex: string, a: number): string => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}
const groupHue = (i: number): string => GROUP_HUES[i % GROUP_HUES.length]

function metricValue(m: DashboardMetric, p: DashboardProcess, now: number): string {
  switch (m) {
    case 'journeys':
      return p.journeys.toLocaleString()
    case 'daysSinceLast': {
      const d = daysBetween(p.lastEventAt, now)
      return d == null ? '—' : d === 0 ? 'today' : `${d}d`
    }
    case 'spanDays': {
      const d = spanDays(p.firstEventAt, p.lastEventAt)
      return d == null ? '—' : `${d}d`
    }
    case 'avgEvents':
      return p.journeys > 0 ? (p.events / p.journeys).toFixed(1) : '—'
    case 'openNotes':
      return '' // rendered as severity chips by <OpenNotes>, never through this path
  }
}

/** Open notes rendered as a row of coloured per-severity count chips (highest first),
 *  showing only the severities that have open notes; a muted 0 when there are none. */
function OpenNotes({ counts }: { counts: Record<string, number> }) {
  const chips = NOTE_SEVERITIES.map((s) => ({ ...s, n: counts?.[s.key] || 0 })).filter((s) => s.n > 0)
  if (chips.length === 0) return <span className="dash-notes0">0</span>
  return (
    <span className="dash-notes">
      {chips.map((s) => (
        <span key={s.key} className="note-sev" title={`${s.n} open · ${s.label}`}>
          <i className="dot" style={{ background: s.color }} />
          {s.n}
        </span>
      ))}
    </span>
  )
}

export function DashboardView() {
  const store = useStore()
  const [groups, setGroups] = useState<DashboardConnection[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [opening, setOpening] = useState<number | null>(null)
  const [extras, setExtras] = useSetting<DashboardMetric[]>('dashboard.extraMetrics')

  useEffect(() => {
    let alive = true
    api
      .dashboard()
      .then((r) => alive && setGroups(r.connections))
      .catch((e) => alive && setError(e?.message || 'Could not load the dashboard.'))
    return () => {
      alive = false
    }
  }, [])

  const now = Date.now()
  const chosen = (extras || []).filter((m) => DASHBOARD_METRICS.includes(m))

  // Overall totals + aggregate ingest timeline (sum per aligned week bucket).
  const overview = useMemo(() => {
    const all = (groups || []).flatMap((g) => g.projects)
    const weeks = all[0]?.timeline.length ?? 0
    const agg = new Array(weeks).fill(0)
    let events = 0
    for (const p of all) {
      events += p.events
      p.timeline.forEach((w, i) => (agg[i] += w.events))
    }
    const connCount = (groups || []).length
    return { processes: all.length, connections: connCount, events, timeline: agg, weeks }
  }, [groups])

  const openProcess = async (connId: string, p: DashboardProcess) => {
    if (opening != null) return
    setOpening(p.projectId)
    try {
      const existing = useStore.getState().connections.find((c) => c.id === connId)
      const ok = await store.connectConnection(existing ?? ({ id: connId } as AssignedConnection))
      if (ok) {
        const project = useStore.getState().projects.find((pr) => pr.projectId === p.projectId)
        if (project) await useStore.getState().selectProject(project)
      }
    } finally {
      setOpening(null)
    }
  }

  const toggleMetric = (m: DashboardMetric) => {
    setExtras((prev) => {
      const cur = (prev || []).filter((x) => DASHBOARD_METRICS.includes(x))
      if (cur.includes(m)) return cur.filter((x) => x !== m)
      if (cur.length >= 3) return cur
      return [...cur, m]
    })
  }
  const moveMetric = (m: DashboardMetric, dir: -1 | 1) => {
    setExtras((prev) => {
      const cur = [...(prev || []).filter((x) => DASHBOARD_METRICS.includes(x))]
      const i = cur.indexOf(m)
      const j = i + dir
      if (i < 0 || j < 0 || j >= cur.length) return cur
      ;[cur[i], cur[j]] = [cur[j], cur[i]]
      return cur
    })
  }

  if (error) {
    return (
      <>
        <style>{STYLE}</style>
        <div className="dash">
          <Unavailable glyph="⚠️" title="Dashboard unavailable" description={error} />
        </div>
      </>
    )
  }
  if (groups == null) {
    return (
      <div className="center-fill" style={{ flex: 1 }}>
        <span className="spinner large" />
        <span>Loading dashboard…</span>
      </div>
    )
  }

  const hasAny = groups.some((g) => g.projects.length > 0)

  return (
    <>
      <style>{STYLE}</style>
      <div className="dash">
        <div className="dash-head">
          <div>
            <h1 className="dash-h1">Dashboard</h1>
            <p className="dash-sub">Every process available to you, at a glance.</p>
          </div>
          <div className="dash-tools">
            <span className="lbl">Metrics:</span>
            {/* selected (ordered, reorderable) */}
            {chosen.map((m) => (
              <span key={m} className="dash-chip on" title={DASHBOARD_METRIC_LABELS[m]}>
                <button className="mv" onClick={() => moveMetric(m, -1)} title="Move left" aria-label="Move left">
                  ◀
                </button>
                <span>{DASHBOARD_METRIC_LABELS[m]}</span>
                <button className="mv" onClick={() => moveMetric(m, 1)} title="Move right" aria-label="Move right">
                  ▶
                </button>
                <button className="mv" onClick={() => toggleMetric(m)} title="Remove" aria-label="Remove">
                  ✕
                </button>
              </span>
            ))}
            {/* available to add (up to 3 total) */}
            {DASHBOARD_METRICS.filter((m) => !chosen.includes(m)).map((m) => (
              <button
                key={m}
                className="dash-chip"
                disabled={chosen.length >= 3}
                onClick={() => toggleMetric(m)}
                title={chosen.length >= 3 ? 'Up to three extra metrics' : `Add ${DASHBOARD_METRIC_LABELS[m]}`}
              >
                + {DASHBOARD_METRIC_LABELS[m]}
              </button>
            ))}
          </div>
        </div>

        {/* Overall overview — a compact full-width strip */}
        <div className="dash-overview">
          <div className="dash-ostats">
            <div className="dash-ostat">
              <span className="dash-ov">{overview.processes}</span>
              <span className="dash-ol">Processes</span>
            </div>
            <div className="dash-ostat">
              <span className="dash-ov">{overview.connections}</span>
              <span className="dash-ol">Connections</span>
            </div>
            <div className="dash-ostat">
              <span className="dash-ov">{overview.events.toLocaleString()}</span>
              <span className="dash-ol">Total events</span>
            </div>
          </div>
          {overview.weeks > 0 && (
            <div className="dash-ospark">
              <span className="cap">ingests · {overview.weeks}w → now</span>
              <Sparkline values={overview.timeline} width={220} height={34} label="All ingests over the shown weeks" />
            </div>
          )}
        </div>

        {!hasAny && (
          <Unavailable
            glyph="🗺"
            title="No processes yet"
            description="You have no processes to show. Ask an administrator to assign a connection, or generate demo data."
          />
        )}

        {groups.map((g, gi) => {
          const hue = groupHue(gi)
          return (
            <div key={g.id} className="dash-group">
              <div className="dash-ghead">
                <span className="dash-gname">{g.name}</span>
                {g.schema && (
                  <span
                    className="dash-gschema"
                    style={{ color: hue, background: hexA(hue, 0.14), borderColor: hexA(hue, 0.3) }}
                  >
                    {g.schema}
                  </span>
                )}
                <span className="dash-gline" />
              </div>
              {g.error && <div className="dash-gerr">⚠ {g.error}</div>}
              {g.projects.length > 0 && (
                <div className="dash-grid">
                  {g.projects.map((p) => (
                    <button
                      key={p.projectId}
                      className="dash-card"
                      style={{ borderLeftColor: hue }}
                      disabled={opening != null}
                      onClick={() => void openProcess(g.id, p)}
                      title={`Open ${p.title}`}
                    >
                      <div className="dash-cmain">
                        <div className="dash-ctop">
                          <span className="dash-cname">{p.title}</span>
                          {p.titleShort && <span className="dash-ccode">{p.titleShort}</span>}
                        </div>
                        <div className="dash-metrics">
                          <div className="dash-metric">
                            <span className="dash-mv">{p.events.toLocaleString()}</span>
                            <span className="dash-ml">Events</span>
                          </div>
                          <div className="dash-metric">
                            <span className="dash-mv">{relativeTime(p.lastEventAt)}</span>
                            <span className="dash-ml">Last log</span>
                          </div>
                          {chosen.map((m) =>
                            m === 'openNotes' ? (
                              <div key={m} className="dash-metric">
                                <span className="dash-mv">
                                  <OpenNotes counts={p.openNotes} />
                                </span>
                                <span className="dash-ml">{DASHBOARD_METRIC_LABELS[m]}</span>
                              </div>
                            ) : (
                              <div key={m} className="dash-metric">
                                <span className="dash-mv">{metricValue(m, p, now)}</span>
                                <span className="dash-ml">{DASHBOARD_METRIC_LABELS[m]}</span>
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                      <div className="dash-spark">
                        <Sparkline
                          values={p.timeline.map((w) => w.events)}
                          width={116}
                          height={34}
                          label={`Ingests for ${p.title} over the last ${p.timeline.length} weeks (to now)`}
                        />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}
