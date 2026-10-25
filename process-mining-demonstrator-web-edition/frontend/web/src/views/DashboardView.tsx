/** The Dashboard — the landing surface on a direct login (a process launched from /home
 *  jumps straight to its map instead). A flat, freely-rearrangeable set of process tiles
 *  across every connection visible to the user: each tile carries its connection as a pill
 *  (upper-left), the event count, last-ingest time, a weekly ingest sparkline and any extra
 *  metrics. Drag a tile by anywhere on it to reorder; the order is saved per user. An overall
 *  card tops the view (processes / connections / total events). Clicking a tile connects to
 *  that process and opens its A-Chart. */

import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Unavailable } from '../components/ui'
import { relativeTime } from '../components/IntegrationKpis'
import { Sparkline } from '../components/Sparkline'
import { NotificationWizard } from '../components/NotificationWizard'
import { NotificationCard } from '../components/NotificationCard'
import { REFRESH_OPTIONS } from '../components/AutoRefresh'
import { useSetting } from '../settings'
import { useStore } from '../store'
import {
  DASHBOARD_METRICS,
  DASHBOARD_METRIC_LABELS,
  NOTE_IMPORTANCE_LEVELS,
  NOTE_IMPORTANCE_META,
  NOTE_SEVERITIES,
  NOTIFICATION_SEVERITIES,
  NOTIFICATION_SEVERITY_RANK,
  type AssignedConnection,
  type DashboardConnection,
  type DashboardMetric,
  type DashboardProcess,
  type NotificationRule,
} from '../types'

const STYLE = `
.dash{flex:1;min-height:0;overflow:auto;padding:14px 16px 24px;color:var(--primary)}
.dash-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;margin-bottom:10px}
.dash-h1{font-size:18px;font-weight:800;letter-spacing:-.01em;margin:0}
.dash-sub{color:var(--secondary);font-size:12px;margin:0}
.dash-tools{margin-left:auto;display:flex;flex-wrap:wrap;align-items:center;gap:7px}
.dash-tools .lbl{font-size:13px;color:var(--secondary)}
/* Auto-refresh control (whole-dashboard timer): countdown ring + interval + manual refresh */
.dash-ar{display:inline-flex;align-items:center;gap:7px}
/* Countdown: a small progress ring + the remaining time as readable text beside it. */
.dash-ar-clock{display:inline-flex;align-items:center;gap:5px}
.dash-ar-clock svg{display:block}
.dash-ar-track{fill:none;stroke:var(--separator);stroke-width:2.5}
.dash-ar-prog{fill:none;stroke:var(--accent);stroke-width:2.5;stroke-linecap:round;
  transition:stroke-dashoffset .2s linear}
.dash-ar-eta{font-size:13px;font-weight:700;color:var(--secondary);
  font-variant-numeric:tabular-nums;min-width:30px}
.dash-ar-sel{font-size:13px;color:var(--primary);background:var(--bg-elevated);
  border:1px solid var(--separator);border-radius:8px;padding:4px 8px;cursor:pointer}
.dash-ar-now{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--separator);
  background:var(--bg-fill);color:var(--primary);border-radius:999px;padding:4px 12px;
  font-size:13px;font-weight:600;cursor:pointer}
.dash-ar-now:hover{background:var(--bg-fill-strong)}
.dash-ar-now[disabled]{opacity:.6;cursor:progress}
.dash-ar-now .ic{display:inline-block;font-size:14px;line-height:1}
.dash-ar-now .ic.spin{animation:nc-spin .8s linear infinite}
.dash-ar-sep{width:1px;align-self:stretch;min-height:24px;background:var(--separator);margin:0 5px}
.dash-chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--separator);
  background:var(--bg-fill);border-radius:999px;padding:4px 11px;font-size:13px;cursor:pointer;
  color:var(--primary);transition:background .15s,border-color .15s}
.dash-chip:hover{background:var(--bg-fill-strong)}
.dash-chip.on{border-color:var(--accent-border);background:var(--accent-soft)}
.dash-chip[disabled]{opacity:.4;cursor:not-allowed}
.dash-chip .mv{border:none;background:none;cursor:pointer;color:var(--secondary);font-size:12px;padding:0 1px;line-height:1}
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
/* Flat, drag-to-reorder tiles (landscape rectangles). */
/* Same grid sizing as the notification tiles (.dash-ngrid): matching min-width, gap, and
   equal-height rows so the two sections line up. */
.dash-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,460px),1fr));
  grid-auto-rows:1fr;gap:12px;margin-top:8px}
.dash-errnote{color:var(--orange);font-size:12px;margin-top:10px}
.dash-card{display:flex;flex-direction:row;align-items:center;gap:12px;border:1px solid var(--separator);
  border-left-width:3px;border-radius:var(--radius);background:var(--bg-elevated);box-shadow:var(--shadow-sm);
  padding:12px 13px 12px 11px;min-height:112px;text-align:left;color:var(--primary);width:100%;cursor:pointer;
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease,opacity .15s ease}
.dash-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-md)}
.dash-card.opening{cursor:progress;opacity:.75}
.dash-card.dragging{opacity:.35}
.dash-card.drag-over{outline:2px dashed var(--accent);outline-offset:1px}
.dash-cmain{flex:1;min-width:0;display:flex;flex-direction:column;gap:7px}
.dash-ctop{display:flex;align-items:center;gap:8px}
.dash-conn-pill{display:inline-flex;align-items:center;gap:4px;flex:none;max-width:46%;
  font-size:10.5px;font-weight:700;border:1px solid var(--separator);border-radius:999px;
  padding:2px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dash-grip{color:var(--tertiary);font-size:13px;line-height:1;cursor:grab;letter-spacing:-1px;flex:none}
.dash-grip:active{cursor:grabbing}
.dash-cname{flex:1;min-width:0;font-size:14px;font-weight:700;letter-spacing:-.01em;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dash-ccode{flex:none;font:600 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  color:var(--secondary);border:1px solid var(--separator);border-radius:5px;padding:2px 5px;white-space:nowrap}
.dash-metrics{display:flex;flex-wrap:wrap;gap:3px 16px}
.dash-metrics-extra{border-top:1px solid var(--separator-soft);padding-top:6px;margin-top:1px}
.dash-metric{display:flex;align-items:baseline;gap:4px}
.dash-mv{font-size:13px;font-weight:700;line-height:1.2}
.dash-ml{font-size:9.5px;color:var(--secondary);text-transform:uppercase;letter-spacing:.02em}
.dash-notes{display:inline-flex;align-items:center;gap:7px}
.dash-notes .note-sev{display:inline-flex;align-items:center;gap:3px}
.dash-notes .note-sev .dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dash-notes0{color:var(--secondary)}
.dash-spark{width:120px;flex:none;align-self:stretch;display:flex;align-items:center}
.dash-spark .spark{width:120px}
.spark{display:block}
.spark .spark-base{stroke:var(--separator-soft);stroke-width:1;vector-effect:non-scaling-stroke}
.spark .spark-area{fill:var(--accent-soft);stroke:none}
.spark .spark-line{stroke:var(--accent);stroke-width:1.6;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.spark .spark-gap{stroke:var(--tertiary);stroke-width:1.4;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
.spark .spark-dot{fill:var(--accent)}
/* Notifications section */
.dash-sechead{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;margin:12px 0 8px}
.dash-sech1{font-size:15px;font-weight:800;letter-spacing:-.01em;margin:0}
.dash-secsub{color:var(--secondary);font-size:11.5px;margin:0}
.dash-secact{margin-left:auto;display:flex;align-items:center;gap:8px}
.dash-notif-empty{color:var(--secondary);font-size:12.5px;padding:4px 0 2px}
/* Stats strip — same accent treatment as the Overview bar */
.dash-nbar{display:flex;flex-wrap:wrap;gap:10px 44px;align-items:center;
  border:1px solid var(--accent-border);background:var(--accent-soft);
  border-radius:var(--radius);padding:11px 18px;margin:2px 0 14px}
.dash-nbstat{display:flex;flex-direction:column;line-height:1.15}
.dash-nbl{font-size:11px;color:var(--secondary);font-weight:600}
.dash-nbv{font-size:22px;font-weight:800;color:var(--primary)}
.dash-nbrefresh{margin-left:auto;display:inline-flex;align-items:center;gap:6px;
  border:1px solid var(--accent-border);background:var(--bg-elevated);color:var(--primary);
  border-radius:999px;padding:5px 13px;font-size:12.5px;font-weight:600;cursor:pointer;
  transition:background .15s}
.dash-nbrefresh:hover{background:var(--bg-fill)}
.dash-nbrefresh[disabled]{opacity:.6;cursor:progress}
.dash-nbrefresh .ic{display:inline-block;font-size:14px;line-height:1}
.dash-nbrefresh .ic.spin{animation:nc-spin .8s linear infinite}
/* Client-side filter row (severity / triggered / enabled / triggered-at) */
.dash-nfilters{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:-6px 0 14px}
.dash-nf-h{font-size:11px;font-weight:700;color:var(--secondary);text-transform:uppercase;
  letter-spacing:.03em}
.dash-nf{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;color:var(--secondary)}
.dash-nf select{font-size:12px;color:var(--primary);background:var(--bg-elevated);
  border:1px solid var(--separator);border-radius:8px;padding:3px 24px 3px 8px;cursor:pointer}
.dash-nf-clear{border:1px solid var(--separator);background:var(--bg-fill);color:var(--primary);
  border-radius:999px;padding:3px 11px;font-size:11.5px;font-weight:600;cursor:pointer}
.dash-nf-clear:hover{background:var(--bg-fill-strong)}
.dash-nf-clear.inline{padding:1px 9px;margin-left:2px}
.dash-nf-count{margin-left:auto;font-size:11.5px;color:var(--secondary);font-weight:600}
/* Per-rule gauge cards — grid-auto-rows:1fr makes every card the same height (the tallest),
   so rows line up regardless of whether a card has a gauge or a longer subtitle. The min
   column width is generous so the four stat boxes (incl. the combined interval·base box)
   always sit on one row; the tiles grow wider rather than wrapping the stats. */
.dash-ngrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,560px),1fr));
  grid-auto-rows:1fr;gap:12px}
.nc{background:var(--bg-elevated);border:1px solid var(--separator);border-radius:14px;
  box-shadow:var(--shadow-sm);padding:11px 14px}
.nc.alert{box-shadow:var(--shadow-sm),0 0 0 1px color-mix(in srgb,var(--red) 32%,transparent)}
.nc.off{opacity:.68}
/* A note card is clickable — it opens the triggering note. */
.nc-open{cursor:pointer}
.nc-open:hover{box-shadow:var(--shadow-sm),0 0 0 1px var(--accent-border)}
.nc-open:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.nc-ndot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px;vertical-align:middle;flex:none}
.nc-head{display:flex;align-items:flex-start;gap:9px}
.nc-bell{font-size:15px;line-height:1.3;flex:none}
.nc-htext{min-width:0;flex:1}
.nc-title{font-size:15px;font-weight:800;letter-spacing:-.01em;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nc-sub{color:var(--secondary);font-size:11.5px;margin-top:1px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nc-pills{display:flex;align-items:center;gap:8px;flex:none}
.ncp{font-size:11px;font-weight:700;border-radius:999px;padding:2px 9px;white-space:nowrap}
.ncp-triggered{background:color-mix(in srgb,var(--red) 16%,transparent);color:var(--red)}
.ncp-ok{background:color-mix(in srgb,var(--green) 16%,transparent);color:var(--green)}
.ncp-warn{background:color-mix(in srgb,var(--orange) 16%,transparent);color:var(--orange)}
.ncp-off,.ncp-idle{background:var(--bg-fill-strong);color:var(--secondary)}
.ncp-urgent{background:color-mix(in srgb,var(--amber) 22%,transparent);color:var(--amber)}
.ncp-important{background:color-mix(in srgb,var(--orange) 18%,transparent);color:var(--orange)}
.ncp-info{background:color-mix(in srgb,var(--blue) 16%,transparent);color:var(--blue)}
.nc-sw{position:relative;width:34px;height:18px;border-radius:999px;border:1px solid var(--separator);
  background:var(--bg-fill);cursor:pointer;transition:background .15s,border-color .15s;flex:none}
.nc-sw[aria-checked="true"]{background:var(--accent-soft);border-color:var(--accent-border)}
.nc-sw::after{content:"";position:absolute;top:1px;left:1px;width:14px;height:14px;border-radius:50%;
  background:var(--primary);transition:transform .15s}
.nc-sw[aria-checked="true"]::after{transform:translateX(16px)}
.nc-sw[disabled]{opacity:.5;cursor:not-allowed}
.nc-refresh{border:1px solid var(--separator);background:var(--bg-fill);color:var(--secondary);
  width:24px;height:24px;border-radius:8px;cursor:pointer;font-size:13px;line-height:1;flex:none;
  display:inline-flex;align-items:center;justify-content:center;transition:background .15s,color .15s}
.nc-refresh:hover{background:var(--bg-fill-strong);color:var(--primary)}
.nc-refresh[disabled]{opacity:.6;cursor:progress}
.nc-refresh.spin{animation:nc-spin .8s linear infinite}
@keyframes nc-spin{to{transform:rotate(360deg)}}
/* Row 2: pills on the left, the per-card actions (refresh / acknowledge / switch) on the right. */
.nc-actions{display:flex;align-items:center;gap:7px;margin-top:8px}
.nc-aspacer{flex:1}
.nc-ack{border:1px solid var(--separator);background:var(--bg-fill);color:var(--secondary);
  height:24px;padding:0 10px;border-radius:999px;cursor:pointer;font-size:11.5px;font-weight:600;
  line-height:1;flex:none;display:inline-flex;align-items:center;gap:4px;white-space:nowrap;
  transition:background .15s,color .15s,border-color .15s}
.nc-ack:hover{background:color-mix(in srgb,var(--green) 16%,transparent);color:var(--green);
  border-color:transparent}
.nc-ack[disabled]{opacity:.6;cursor:progress}
/* Always reserve the gauge (bar) height — min-height matches the rendered track + scale — so
   cards without a gauge (note rules, or before the first measurement) keep the space and every
   card's stat boxes line up at the same position. */
.nc-gauge{margin:11px 0 2px;min-height:30px}
.nc-track{position:relative;height:10px;border-radius:999px;background:var(--bg-fill-strong)}
.nc-fill{position:absolute;left:0;top:0;bottom:0;border-radius:999px;background:var(--accent);min-width:3px}
.nc-tick{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--red);border-radius:1px}
.nc-scale{position:relative;display:flex;justify-content:space-between;margin-top:6px;
  font-size:10.5px;color:var(--secondary)}
.nc-lim{position:absolute;transform:translateX(-50%);color:var(--red);font-weight:600;white-space:nowrap}
/* Flex so each wrapped row fills the full width (no dangling single box), and every box is
   the same height. */
/* Four boxes always on ONE row (no wrap) — the tile widens instead. The combined
   interval·base box gets extra width so its label never truncates. */
.nc-stats{display:flex;flex-wrap:nowrap;gap:8px;margin-top:10px}
.nc-box{flex:1 1 84px;min-width:0;background:var(--bg-fill);border-radius:10px;padding:6px 10px;
  display:flex;flex-direction:column;justify-content:center;gap:2px;height:46px;box-sizing:border-box}
.nc-box-wide{flex:1.7 1 150px}
.nc-bl{font-size:10px;color:var(--secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nc-bl .nc-ico{font-size:11px;margin-right:2px}
.nc-bsep{color:var(--tertiary);font-weight:700}
/* Keep the value on one line so a two-part value (e.g. "60 s (6.3%)") never wraps and makes
   the box taller than the others — every box stays the same fixed height. */
.nc-bv{font-size:14px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nc-bv-dual{font-size:13.5px}
/* When a value is too wide for its box it scrolls right-to-left like a ticker (the Marquee
   component adds .on + a second copy); when it fits it sits still. Pauses on hover. */
.mq-track{display:inline-flex;will-change:transform}
.mq-copy{flex:none;white-space:nowrap}
.nc-bv.mq.on .mq-track{animation:mq-scroll linear infinite}
.nc-bv.mq.on .mq-copy{padding-right:28px}
.nc-bv.mq.on:hover .mq-track{animation-play-state:paused}
@keyframes mq-scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@media (prefers-reduced-motion:reduce){
  .nc-bv.mq.on .mq-track{animation:none}
  .nc-bv.mq.on .mq-copy:nth-child(2){display:none}
}
.nc-bv.fire{color:var(--red)}
.nc-bv.ok{color:var(--green)}
.nc-bv.idle{color:var(--secondary)}
.nc-pct{font-size:12px;font-weight:700}
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

// A distinct pastel per connection: the connection pill is tinted with it and each of its
// tiles gets a matching coloured left edge, so a connection still reads at a glance even
// though the tiles are no longer grouped under headers.
const GROUP_HUES = ['#3a9bff', '#30c48d', '#ff9f43', '#a66cff', '#ff6b8b', '#2bb9d4', '#e0b000', '#6b7bff']
const hexA = (hex: string, a: number): string => {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}
const groupHue = (i: number): string => GROUP_HUES[i % GROUP_HUES.length]

/** Move `dragKey` to sit immediately before `dropKey` in `keys`. Pure, so it's unit-tested. */
export function reorderKeys(keys: string[], dragKey: string, dropKey: string): string[] {
  if (dragKey === dropKey) return keys
  const rest = keys.filter((k) => k !== dragKey)
  const idx = rest.indexOf(dropKey)
  rest.splice(idx < 0 ? rest.length : idx, 0, dragKey)
  return rest
}

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

interface Tile {
  key: string
  connId: string
  connName: string
  schema: string | null
  hue: string
  p: DashboardProcess
}

const triggeredMs = (r: NotificationRule): number =>
  r.enabled && r.state?.triggered && r.state.triggeredAt ? Date.parse(r.state.triggeredAt) || 0 : 0

/** A rule counts as "triggered" for display/filtering only while enabled AND currently firing
 *  (the engine clears triggeredAt on recovery, so a recovered rule is not triggered). */
const isRuleTriggered = (r: NotificationRule): boolean => !!(r.enabled && r.state?.triggered)

/** The Notifications section's client-side filters. Each is "all" (off) or a specific choice. */
export interface NotifFilters {
  severity: string // 'all' | 'URGENT' | 'IMPORTANT' | 'INFO'
  triggered: string // 'all' | 'yes' | 'no'
  enabled: string // 'all' | 'yes' | 'no'
  triggeredAt: string // one of TRIGGERED_AT_WINDOWS keys
  type: string // 'all' | 'event' | 'note'
  scope: string // 'all' | 'shared' | 'personal' — narrows NOTE notifications
  noteSeverity: string // 'all' | 'NORMAL' | 'INFO' | 'IMPORTANT' | 'URGENT' — narrows NOTE notifications
}

export const NOTIF_FILTER_DEFAULTS: NotifFilters = {
  severity: 'all',
  triggered: 'all',
  enabled: 'all',
  triggeredAt: 'all',
  type: 'all',
  scope: 'all',
  noteSeverity: 'all',
}

/** "Triggered at" windows: how recently a rule fired, measured from its state.triggeredAt. */
export const TRIGGERED_AT_WINDOWS: { key: string; label: string; secs: number }[] = [
  { key: 'all', label: 'All', secs: 0 },
  { key: 'hour', label: 'Last hour', secs: 3600 },
  { key: 'day', label: 'Last 24 hours', secs: 86400 },
  { key: 'week', label: 'Last week', secs: 604800 },
  { key: 'month', label: 'Last month', secs: 2592000 },
]

/** True when any filter is set to something other than its "all" default. */
export function notifFiltersActive(f: NotifFilters): boolean {
  return (
    f.severity !== 'all' || f.triggered !== 'all' || f.enabled !== 'all' ||
    f.triggeredAt !== 'all' || f.type !== 'all' || f.scope !== 'all' || f.noteSeverity !== 'all'
  )
}

/** Apply the Notifications filters. Pure, so it is unit-tested. A "Triggered at" window implies
 *  the rule is currently triggered (only a firing rule has a triggeredAt timestamp). The
 *  scope + note-severity filters narrow NOTE notifications only (event notifications pass). */
export function filterNotifications(
  rules: NotificationRule[],
  f: NotifFilters,
  now: number = Date.now(),
): NotificationRule[] {
  return rules.filter((r) => {
    const isNote = r.kind === 'note'
    if (f.type === 'note' && !isNote) return false
    if (f.type === 'event' && isNote) return false
    if (f.severity !== 'all' && r.severity !== f.severity) return false
    const trig = isRuleTriggered(r)
    if (f.triggered === 'yes' && !trig) return false
    if (f.triggered === 'no' && trig) return false
    if (f.enabled === 'yes' && !r.enabled) return false
    if (f.enabled === 'no' && r.enabled) return false
    if (f.triggeredAt !== 'all') {
      const win = TRIGGERED_AT_WINDOWS.find((w) => w.key === f.triggeredAt)
      const at = r.state?.triggeredAt ? Date.parse(r.state.triggeredAt) : NaN
      if (!trig || Number.isNaN(at)) return false
      if (win && win.secs > 0 && now - at > win.secs * 1000) return false
    }
    // Note-only refinements — fall back to the rule's configured scope/importance when there
    // is no current matching note (so an untriggered note rule still filters sensibly).
    if (isNote) {
      if (f.scope !== 'all') {
        const scope = r.state?.note?.scope ?? (r.config.scope === 'all' ? 'shared' : r.config.scope)
        if (scope !== f.scope) return false
      }
      if (f.noteSeverity !== 'all') {
        const imp = r.state?.note?.importance ?? r.config.minImportance ?? 'NORMAL'
        if (imp !== f.noteSeverity) return false
      }
    }
    return true
  })
}

/** Order rules by urgency then time (descending): triggered first, then by severity, then by
 *  most-recently triggered, then by name. */
function sortRules(rules: NotificationRule[]): NotificationRule[] {
  return [...rules].sort((a, b) => {
    const ta = a.enabled && a.state?.triggered ? 1 : 0
    const tb = b.enabled && b.state?.triggered ? 1 : 0
    if (ta !== tb) return tb - ta
    const sa = NOTIFICATION_SEVERITY_RANK[a.severity] || 0
    const sb = NOTIFICATION_SEVERITY_RANK[b.severity] || 0
    if (sa !== sb) return sb - sa
    const tm = triggeredMs(b) - triggeredMs(a)
    if (tm !== 0) return tm
    return (a.name || a.id).localeCompare(b.name || b.id)
  })
}

/** Format a seconds countdown for readability: under a minute as "45s", otherwise "m:ss". */
function fmtCountdown(secs: number): string {
  const s = Math.max(0, Math.ceil(secs))
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** The dashboard auto-refresh countdown: a clean progress ring with the remaining time shown
 *  as readable text BESIDE it (not crammed inside the ring). Ticks locally (~5 fps); renders
 *  nothing until a refresh is scheduled. */
function DashRefreshRing({ secs, nextAt }: { secs: number; nextAt: number | null }) {
  const [, force] = useState(0)
  useEffect(() => {
    if (!nextAt) return
    const id = window.setInterval(() => force((x) => (x + 1) % 1_000_000), 200)
    return () => window.clearInterval(id)
  }, [nextAt])
  const size = 18
  const r = 7
  const circ = 2 * Math.PI * r
  if (!secs || !nextAt) return null
  const remaining = Math.max(0, (nextAt - Date.now()) / 1000)
  const frac = Math.max(0, Math.min(1, remaining / secs))
  const label = fmtCountdown(remaining)
  return (
    <span className="dash-ar-clock" title={`Next refresh in ${label}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle className="dash-ar-track" cx={size / 2} cy={size / 2} r={r} />
        <circle
          className="dash-ar-prog"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - frac)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="dash-ar-eta">{label}</span>
    </span>
  )
}

export function DashboardView() {
  const store = useStore()
  const [groups, setGroups] = useState<DashboardConnection[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [opening, setOpening] = useState<number | null>(null)
  const [extras, setExtras] = useSetting<DashboardMetric[]>('dashboard.extraMetrics')
  const [order, setOrder] = useSetting<string[]>('dashboard.tileOrder')
  const [dragKey, setDragKey] = useState<string | null>(null)
  const [overKey, setOverKey] = useState<string | null>(null)
  const notificationsOn = store.notificationsEnabled
  const [notifRules, setNotifRules] = useState<NotificationRule[]>([])
  const [canManageNotif, setCanManageNotif] = useState(false)
  const [notifWizard, setNotifWizard] = useState(false)
  const [notifBusy, setNotifBusy] = useState<string | null>(null) // rule id being toggled/refreshed
  const [notifAllBusy, setNotifAllBusy] = useState(false)
  const [notifFilters, setNotifFilters] = useState<NotifFilters>(NOTIF_FILTER_DEFAULTS)
  const [refreshSecs, setRefreshSecs] = useSetting<number>('dashboard.autoRefreshSecs')
  const [refreshNextAt, setRefreshNextAt] = useState<number | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  // Re-fetch the process tiles. `quiet` (the auto-refresh path) swallows errors so a transient
  // blip never blanks a working dashboard; the initial load surfaces an error instead.
  const loadDashboard = (quiet = false) => {
    api
      .dashboard()
      .then((r) => setGroups(r.connections))
      .catch((e) => {
        if (!quiet) setError(e?.message || 'Could not load the dashboard.')
      })
  }
  useEffect(() => {
    loadDashboard()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadNotifs = () => {
    if (!notificationsOn) return
    api
      .listNotifications()
      .then((r) => {
        setNotifRules(r.rules)
        setCanManageNotif(r.canManage)
      })
      .catch(() => {
        /* a transient failure just leaves the section empty; no hard error on the dashboard */
      })
  }
  useEffect(() => {
    loadNotifs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notificationsOn])

  // Refresh the WHOLE dashboard — the process tiles and the notifications — at once. Used by
  // the manual ↻ button and the auto-refresh timer. It re-fetches (reflecting the latest
  // ingest counts and the notification engine's current state); it does not re-evaluate rules
  // (that is the background engine's job, or the Notifications "Refresh all").
  const refreshAllData = async (quiet = false) => {
    setRefreshing(true)
    try {
      await Promise.allSettled([
        api.dashboard().then((r) => setGroups(r.connections)),
        notificationsOn
          ? api.listNotifications().then((r) => {
              setNotifRules(r.rules)
              setCanManageNotif(r.canManage)
            })
          : Promise.resolve(),
      ])
    } catch {
      if (!quiet) setError('Could not refresh the dashboard.')
    } finally {
      setRefreshing(false)
    }
  }

  // Auto-refresh timer: tick every `refreshSecs` seconds while an interval is set, re-fetching
  // the whole dashboard and resetting the countdown. `refreshNextAt` drives the ring.
  useEffect(() => {
    if (!refreshSecs || refreshSecs <= 0) {
      setRefreshNextAt(null)
      return
    }
    setRefreshNextAt(Date.now() + refreshSecs * 1000)
    const id = window.setInterval(() => {
      void refreshAllData(true)
      setRefreshNextAt(Date.now() + refreshSecs * 1000)
    }, refreshSecs * 1000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSecs, notificationsOn])

  const refreshNow = () => {
    void refreshAllData(false)
    if (refreshSecs > 0) setRefreshNextAt(Date.now() + refreshSecs * 1000) // restart the countdown
  }

  // One pastel per connection (by its position), shared by the process tiles and the
  // notification tiles so a connection reads the same colour in both.
  const hueOf = useMemo(() => {
    const m = new Map<string, string>()
    ;(groups || []).forEach((g, i) => m.set(g.id, groupHue(i)))
    return m
  }, [groups])

  const now = Date.now()
  const chosen = (extras || []).filter((m) => DASHBOARD_METRICS.includes(m))

  // Flatten every connection's projects into one tile list, coloured per connection, then
  // apply the user's saved order (tiles not listed keep server order, appended after).
  const tiles = useMemo<Tile[]>(() => {
    const gs = groups || []
    const all: Tile[] = gs.flatMap((g) =>
      g.projects.map((p) => ({
        key: `${g.id}::${p.projectId}`,
        connId: g.id,
        connName: g.name,
        schema: g.schema,
        hue: hueOf.get(g.id) || groupHue(0),
        p,
      })),
    )
    const pos = new Map((order || []).map((k, i) => [k, i]))
    return all
      .map((t, i) => ({ t, i }))
      .sort((a, b) => {
        const pa = pos.has(a.t.key) ? (pos.get(a.t.key) as number) : Infinity
        const pb = pos.has(b.t.key) ? (pos.get(b.t.key) as number) : Infinity
        return pa - pb || a.i - b.i // stable: fall back to server order
      })
      .map(({ t }) => t)
  }, [groups, order, hueOf])

  // Connections whose schema couldn't be read — shown as a compact note (no group headers now).
  const errors = (groups || []).filter((g) => g.error).map((g) => ({ name: g.name, error: g.error as string }))

  const overview = useMemo(() => {
    const all = (groups || []).flatMap((g) => g.projects)
    const weeks = all[0]?.timeline.length ?? 0
    const agg = new Array(weeks).fill(0)
    let events = 0
    for (const p of all) {
      events += p.events
      p.timeline.forEach((w, i) => (agg[i] += w.events))
    }
    return { processes: all.length, connections: (groups || []).length, events, timeline: agg, weeks }
  }, [groups])

  // One card per rule, ordered by urgency then time (descending).
  // The cards to show, and how many acknowledged alerts are hidden. An acknowledged alert is
  // kept out of the grid until it clears and triggers again (the engine gives it a fresh
  // triggered-at, which lapses the acknowledgement).
  const { sortedRules, ackHidden } = useMemo(() => {
    const filtered = sortRules(filterNotifications(notifRules, notifFilters))
    const shown = filtered.filter((r) => !r.state?.acknowledged)
    return { sortedRules: shown, ackHidden: filtered.length - shown.length }
  }, [notifRules, notifFilters])
  const filtersActive = notifFiltersActive(notifFilters)
  const hasNoteRules = useMemo(() => notifRules.some((r) => r.kind === 'note'), [notifRules])
  const setFilter = (patch: Partial<NotifFilters>) =>
    setNotifFilters((prev) => ({ ...prev, ...patch }))

  // Headline stats for the blue strip.
  const notifStats = useMemo(() => {
    const total = notifRules.length
    const enabled = notifRules.filter((r) => r.enabled).length
    const triggered = notifRules.filter((r) => r.enabled && r.state?.triggered).length
    const urgent = notifRules.filter(
      (r) => r.enabled && r.state?.triggered && r.severity === 'URGENT',
    ).length
    const watched = new Set(notifRules.map((r) => r.connectionId)).size
    return { total, enabled, triggered, urgent, watched, connections: (groups || []).length }
  }, [notifRules, groups])

  const toggleRule = async (rule: NotificationRule) => {
    if (!canManageNotif || notifBusy) return
    setNotifBusy(rule.id)
    try {
      await api.setNotificationEnabled(rule.id, !rule.enabled)
      loadNotifs()
    } catch {
      /* ignore — the switch simply won't flip */
    } finally {
      setNotifBusy(null)
    }
  }

  const refreshRule = async (rule: NotificationRule) => {
    if (notifBusy) return
    setNotifBusy(rule.id)
    try {
      const updated = await api.checkNotification(rule.id)
      setNotifRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch {
      /* ignore — a transient failure leaves the card unchanged */
    } finally {
      setNotifBusy(null)
    }
  }

  // Acknowledge a firing alert — it drops out of the grid until it clears and triggers again.
  const ackRule = async (rule: NotificationRule) => {
    if (notifBusy) return
    setNotifBusy(rule.id)
    try {
      const updated = await api.ackNotification(rule.id)
      setNotifRules((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    } catch {
      /* ignore — a transient failure leaves the card unchanged */
    } finally {
      setNotifBusy(null)
    }
  }

  const refreshAll = async () => {
    if (notifAllBusy) return
    setNotifAllBusy(true)
    try {
      const r = await api.checkAllNotifications()
      setNotifRules(r.rules)
      setCanManageNotif(r.canManage)
    } catch {
      /* ignore — a transient failure leaves the cards unchanged */
    } finally {
      setNotifAllBusy(false)
    }
  }

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

  // Open the note a note-notification points at: connect, select the project, switch to the
  // Notes view and ask it to open/scroll to that note.
  const openNote = async (rule: NotificationRule) => {
    const noteId = rule.state?.note?.noteId
    if (!noteId || opening != null) return
    setOpening(rule.projectId)
    try {
      const existing = useStore.getState().connections.find((c) => c.id === rule.connectionId)
      const ok = await store.connectConnection(
        existing ?? ({ id: rule.connectionId } as AssignedConnection),
      )
      if (ok) {
        const project = useStore.getState().projects.find((pr) => pr.projectId === rule.projectId)
        if (project) {
          await useStore.getState().selectProject(project)
          useStore.getState().goToNote(noteId)
        }
      }
    } finally {
      setOpening(null)
    }
  }

  const dropOnto = (dragK: string, dropKey: string) => {
    setDragKey(null)
    setOverKey(null)
    if (!dragK || dragK === dropKey) return
    // Persist the full current key order with the dragged tile moved before the drop target.
    setOrder(reorderKeys(tiles.map((t) => t.key), dragK, dropKey))
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

  return (
    <>
      <style>{STYLE}</style>
      <div className="dash">
        <div className="dash-head">
          <div>
            <h1 className="dash-h1">Dashboard</h1>
            <p className="dash-sub">Every process available to you — drag a tile to rearrange.</p>
          </div>
          <div className="dash-tools">
            <div className="dash-ar" role="group" aria-label="Auto-refresh">
              <span className="lbl">Auto-refresh:</span>
              {refreshSecs > 0 && <DashRefreshRing secs={refreshSecs} nextAt={refreshNextAt} />}
              <select
                className="dash-ar-sel"
                value={refreshSecs}
                onChange={(e) => setRefreshSecs(Number(e.target.value))}
                aria-label="Auto-refresh interval"
                title="Automatically refresh the whole dashboard on a timer"
              >
                {REFRESH_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <button
                className="dash-ar-now"
                onClick={refreshNow}
                disabled={refreshing}
                title="Refresh the whole dashboard (process tiles and notifications) now"
              >
                <span className={`ic${refreshing ? ' spin' : ''}`} aria-hidden>
                  ↻
                </span>{' '}
                Refresh
              </button>
            </div>
            <span className="dash-ar-sep" aria-hidden />
            <span className="lbl">Metrics:</span>
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

        {tiles.length === 0 && (
          <Unavailable
            glyph="🗺"
            title="No processes yet"
            description="You have no processes to show. Ask an administrator to assign a connection, or generate demo data."
          />
        )}

        {tiles.length > 0 && (
          <div className="dash-grid">
            {tiles.map((t) => (
              <div
                key={t.key}
                className={
                  'dash-card' +
                  (opening != null ? ' opening' : '') +
                  (dragKey === t.key ? ' dragging' : '') +
                  (overKey === t.key && dragKey !== t.key ? ' drag-over' : '')
                }
                style={{ borderLeftColor: t.hue }}
                role="button"
                tabIndex={0}
                draggable
                onDragStart={(e) => {
                  setDragKey(t.key)
                  e.dataTransfer.effectAllowed = 'move'
                  e.dataTransfer.setData('text/plain', t.key)
                }}
                onDragEnd={() => {
                  setDragKey(null)
                  setOverKey(null)
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  e.dataTransfer.dropEffect = 'move'
                  if (overKey !== t.key) setOverKey(t.key)
                }}
                onDragLeave={() => {
                  if (overKey === t.key) setOverKey(null)
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  // Prefer the dataTransfer payload (set on dragstart) so a drop still works
                  // even if the dragKey state hasn't flushed yet.
                  dropOnto(dragKey || e.dataTransfer.getData('text/plain'), t.key)
                }}
                onClick={() => void openProcess(t.connId, t.p)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    void openProcess(t.connId, t.p)
                  }
                }}
                title={`Open ${t.p.title}`}
              >
                <div className="dash-cmain">
                  {/* Row 1: connection pill + process name (+ code, drag grip). */}
                  <div className="dash-ctop">
                    <span
                      className="dash-conn-pill"
                      style={{ color: t.hue, background: hexA(t.hue, 0.14), borderColor: hexA(t.hue, 0.3) }}
                      title={t.schema ? `${t.connName} · ${t.schema}` : t.connName}
                    >
                      🛢 {t.connName}
                    </span>
                    <span className="dash-cname" title={t.p.title}>
                      {t.p.title}
                    </span>
                    {t.p.titleShort && <span className="dash-ccode">{t.p.titleShort}</span>}
                    <span className="dash-grip" aria-hidden title="Drag to rearrange">
                      ⠿
                    </span>
                  </div>
                  {/* Row 2: always-on metrics. */}
                  <div className="dash-metrics">
                    <div className="dash-metric">
                      <span className="dash-mv">{t.p.events.toLocaleString()}</span>
                      <span className="dash-ml">Events</span>
                    </div>
                    <div className="dash-metric">
                      <span className="dash-mv">{relativeTime(t.p.lastEventAt)}</span>
                      <span className="dash-ml">Last log</span>
                    </div>
                  </div>
                  {/* Row 3: the selected extra metrics. */}
                  {chosen.length > 0 && (
                    <div className="dash-metrics dash-metrics-extra">
                      {chosen.map((m) =>
                        m === 'openNotes' ? (
                          <div key={m} className="dash-metric">
                            <span className="dash-mv">
                              <OpenNotes counts={t.p.openNotes} />
                            </span>
                            <span className="dash-ml">{DASHBOARD_METRIC_LABELS[m]}</span>
                          </div>
                        ) : (
                          <div key={m} className="dash-metric">
                            <span className="dash-mv">{metricValue(m, t.p, now)}</span>
                            <span className="dash-ml">{DASHBOARD_METRIC_LABELS[m]}</span>
                          </div>
                        ),
                      )}
                    </div>
                  )}
                </div>
                <div className="dash-spark">
                  <Sparkline
                    values={t.p.timeline.map((w) => w.events)}
                    width={120}
                    height={46}
                    label={`Ingests for ${t.p.title} over the last ${t.p.timeline.length} weeks (to now)`}
                  />
                </div>
              </div>
            ))}
          </div>
        )}

        {notificationsOn && (
          <>
            <div className="dash-sechead">
              <div>
                <h2 className="dash-sech1">Notifications</h2>
                <p className="dash-secsub">
                  Alerts when a metric crosses a threshold or a note needs attention — most
                  urgent and most recent first.
                </p>
              </div>
              {canManageNotif && (
                <div className="dash-secact">
                  <button className="dash-chip" onClick={() => setNotifWizard(true)}>
                    ＋ Create / Edit
                  </button>
                </div>
              )}
            </div>

            <div className="dash-nbar">
              {[
                { l: 'Rules', v: `${notifStats.total}` },
                { l: 'Triggered', v: `${notifStats.triggered}` },
                { l: 'Enabled', v: `${notifStats.enabled} / ${notifStats.total}` },
                { l: 'Connections watched', v: `${notifStats.watched} / ${notifStats.connections}` },
                { l: 'Urgent', v: `${notifStats.urgent}` },
              ].map((s) => (
                <div key={s.l} className="dash-nbstat">
                  <span className="dash-nbl">{s.l}</span>
                  <span className="dash-nbv">{s.v}</span>
                </div>
              ))}
              {notifStats.total > 0 && (
                <button
                  className="dash-nbrefresh"
                  disabled={notifAllBusy}
                  onClick={() => void refreshAll()}
                  title="Re-check every rule against the current data now"
                >
                  <span className={`ic${notifAllBusy ? ' spin' : ''}`}>↻</span>
                  {notifAllBusy ? 'Refreshing…' : 'Refresh all'}
                </button>
              )}
            </div>

            {notifRules.length > 0 && (
              <div className="dash-nfilters">
                <span className="dash-nf-h">Filter</span>
                <label className="dash-nf">
                  Type
                  <select
                    value={notifFilters.type}
                    onChange={(e) => setFilter({ type: e.target.value })}
                  >
                    <option value="all">All</option>
                    <option value="event">Event</option>
                    <option value="note">Note</option>
                  </select>
                </label>
                <label className="dash-nf">
                  Severity
                  <select
                    value={notifFilters.severity}
                    onChange={(e) => setFilter({ severity: e.target.value })}
                  >
                    <option value="all">All</option>
                    {NOTIFICATION_SEVERITIES.map((s) => (
                      <option key={s.key} value={s.key}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="dash-nf">
                  Triggered
                  <select
                    value={notifFilters.triggered}
                    onChange={(e) => setFilter({ triggered: e.target.value })}
                  >
                    <option value="all">All</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </label>
                <label className="dash-nf">
                  Enabled
                  <select
                    value={notifFilters.enabled}
                    onChange={(e) => setFilter({ enabled: e.target.value })}
                  >
                    <option value="all">All</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </label>
                <label className="dash-nf">
                  Triggered at
                  <select
                    value={notifFilters.triggeredAt}
                    onChange={(e) => setFilter({ triggeredAt: e.target.value })}
                  >
                    {TRIGGERED_AT_WINDOWS.map((w) => (
                      <option key={w.key} value={w.key}>
                        {w.label}
                      </option>
                    ))}
                  </select>
                </label>
                {hasNoteRules && notifFilters.type !== 'event' && (
                  <>
                    <label className="dash-nf">
                      Note scope
                      <select
                        value={notifFilters.scope}
                        onChange={(e) => setFilter({ scope: e.target.value })}
                      >
                        <option value="all">All</option>
                        <option value="shared">Shared</option>
                        <option value="personal">Personal</option>
                      </select>
                    </label>
                    <label className="dash-nf">
                      Note severity
                      <select
                        value={notifFilters.noteSeverity}
                        onChange={(e) => setFilter({ noteSeverity: e.target.value })}
                      >
                        <option value="all">All</option>
                        {NOTE_IMPORTANCE_LEVELS.map((lvl) => (
                          <option key={lvl} value={lvl}>
                            {NOTE_IMPORTANCE_META[lvl].label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
                )}
                {filtersActive && (
                  <button
                    type="button"
                    className="dash-nf-clear"
                    onClick={() => setNotifFilters(NOTIF_FILTER_DEFAULTS)}
                  >
                    Clear filters
                  </button>
                )}
                <span className="dash-nf-count">
                  {sortedRules.length} of {notifRules.length}
                </span>
              </div>
            )}

            {sortedRules.length > 0 && (
              <div className="dash-ngrid">
                {sortedRules.map((r) => (
                  <NotificationCard
                    key={r.id}
                    rule={r}
                    canManage={canManageNotif}
                    onToggle={(x) => void toggleRule(x)}
                    onRefresh={(x) => void refreshRule(x)}
                    onAck={(x) => void ackRule(x)}
                    onOpen={(x) => void openNote(x)}
                    busy={notifBusy === r.id}
                  />
                ))}
              </div>
            )}
            {ackHidden > 0 && (
              <div className="dash-notif-empty">
                ✓ {ackHidden} acknowledged alert{ackHidden > 1 ? 's' : ''} hidden —{' '}
                {ackHidden > 1 ? 'they' : 'it'} will reappear on the next trigger.
              </div>
            )}
            {sortedRules.length === 0 && ackHidden === 0 && (
              <div className="dash-notif-empty">
                {notifRules.length > 0 && filtersActive ? (
                  <>
                    No notifications match the current filters.{' '}
                    <button
                      type="button"
                      className="dash-nf-clear inline"
                      onClick={() => setNotifFilters(NOTIF_FILTER_DEFAULTS)}
                    >
                      Clear filters
                    </button>
                  </>
                ) : canManageNotif ? (
                  'No notification rules yet — use Create / Edit to add one.'
                ) : (
                  'No notifications are configured for your connections.'
                )}
              </div>
            )}
          </>
        )}

        {errors.length > 0 && (
          <div className="dash-errnote">
            ⚠ Couldn't read {errors.length} connection{errors.length > 1 ? 's' : ''}:{' '}
            {errors.map((e, i) => (
              <span key={e.name}>
                {i > 0 && ', '}
                {e.name} — {e.error}
              </span>
            ))}
          </div>
        )}
      </div>
      {notifWizard && (
        <NotificationWizard
          groups={groups}
          rules={notifRules}
          onClose={() => setNotifWizard(false)}
          onChanged={loadNotifs}
        />
      )}
    </>
  )
}
