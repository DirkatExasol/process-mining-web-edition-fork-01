/** One notification rule rendered as a gauge card (Dashboard → Notifications). Shows the
 *  rule's criterion, a status + severity pill, a bar of the measured value against its limit,
 *  and four stat boxes (last value, over/under limit, triggered-at, check interval). The
 *  per-card CSS (.nc-*, .dash-nbar) lives in DashboardView's inline STYLE. */

import { useLayoutEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import {
  NOTE_IMPORTANCE_META,
  NOTIFICATION_INTERVALS,
  NOTIFICATION_NOTE_EVENTS,
  NOTIFICATION_SEVERITIES,
  NOTIFICATION_TIME_METRICS,
  normalizeImportance,
  type NotificationNote,
  type NotificationRule,
} from '../types'

/** A stat value that scrolls right-to-left like a ticker when it is too wide for its box, and
 *  sits still (no animation) when it fits. Pauses on hover; honours reduced-motion. */
function Marquee({ children, className = '' }: { children: ReactNode; className?: string }) {
  const box = useRef<HTMLSpanElement>(null)
  const copy = useRef<HTMLSpanElement>(null)
  const [on, setOn] = useState(false)
  const [dur, setDur] = useState(8)

  useLayoutEffect(() => {
    const measure = () => {
      if (!box.current || !copy.current) return
      const w = copy.current.scrollWidth
      const overflows = w > box.current.clientWidth + 1
      setOn(overflows)
      if (overflows) setDur(Math.max(4, Math.round((w + 28) / 35))) // ~35 px/s, plus the gap
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return // jsdom / older engines
    const ro = new ResizeObserver(measure)
    if (box.current) ro.observe(box.current)
    if (copy.current) ro.observe(copy.current)
    return () => ro.disconnect()
  })

  return (
    <span className={`nc-bv mq ${className}${on ? ' on' : ''}`} ref={box}>
      <span className="mq-track" style={on ? { animationDuration: `${dur}s` } : undefined}>
        <span className="mq-copy" ref={copy}>
          {children}
        </span>
        {on && (
          <span className="mq-copy" aria-hidden>
            {children}
          </span>
        )}
      </span>
    </span>
  )
}

// ── formatting ────────────────────────────────────────────────────────────────

/** m:ss (or h:mm:ss) — the duration style the cards use (e.g. 1020s → "17:00"). */
export function fmtClock(secs: number): string {
  const s = Math.max(0, Math.round(secs))
  const two = (n: number) => String(n).padStart(2, '0')
  if (s < 3600) return `${Math.floor(s / 60)}:${two(s % 60)}`
  return `${Math.floor(s / 3600)}:${two(Math.floor((s % 3600) / 60))}:${two(s % 60)}`
}

/** Smallest "nice" number (1,1.5,2,3,4,5,6,8,10 × 10ⁿ) ≥ x, for a gauge's top of scale. */
export function niceCeil(x: number): number {
  if (x <= 0) return 1
  const exp = Math.floor(Math.log10(x))
  const base = 10 ** exp
  const f = x / base
  const nice = [1, 1.5, 2, 3, 4, 5, 6, 8, 10].find((s) => f <= s + 1e-9) ?? 10
  return nice * base
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

interface Gauge {
  fillPct: number
  limitPct: number
  leftLabel: string
  rightLabel: string
  limitLabel: string
}

export interface CardMetrics {
  status: { key: string; label: string }
  severityLabel: string
  criterion: string
  subtitle: string
  gauge: Gauge | null
  lastValue: string
  deltaLabel: string
  deltaValue: string
  deltaPct: string
  deltaClass: string
  triggeredAt: string
  interval: string
  lookback: string
  /** Compact forms for the combined interval·base box (e.g. "5m", "7d" / "All"). */
  intervalShort: string
  lookbackShort: string
  /** note kind only: whether this is a note rule, and the triggering note (if any). */
  isNote: boolean
  note: NotificationNote | null
}

/** A note rule's criterion line, e.g. "notes · new · important+". */
function noteCriterion(c: NotificationRule['config']): string {
  const ev = NOTIFICATION_NOTE_EVENTS.find((e) => e.event === c.event)?.label?.toLowerCase() || 'notes'
  const scope = c.scope === 'all' ? 'all' : 'shared'
  const imp = c.minImportance && c.minImportance !== 'NORMAL'
    ? ` · ${NOTE_IMPORTANCE_META[normalizeImportance(c.minImportance)].label.toLowerCase()}+`
    : ''
  return `notes · ${ev} · ${scope}${imp}`
}

/** The check interval as a compact token: "1m", "15m", "1h", "2h", "1d". */
function shortInterval(secs: number): string {
  if (secs > 0 && secs % 86400 === 0) return `${secs / 86400}d`
  if (secs > 0 && secs % 3600 === 0) return `${secs / 3600}h`
  if (secs > 0 && secs % 60 === 0) return `${secs / 60}m`
  return `${secs}s`
}

/** The base period as a compact token: "All", "7d", "30m", "3mo", "1y". */
function shortLookback(c: { lookbackUnit?: string; lookbackValue?: number }): string {
  if (!c.lookbackUnit || c.lookbackUnit === 'all' || !c.lookbackValue) return 'All'
  const u: Record<string, string> =
    { minutes: 'm', days: 'd', months: 'mo', years: 'y' }
  return `${c.lookbackValue}${u[c.lookbackUnit] ?? c.lookbackUnit[0]}`
}

function timeUnit(maxSecs: number): { secs: number; word: string } {
  if (maxSecs >= 86400) return { secs: 86400, word: 'd' }
  if (maxSecs >= 3600) return { secs: 3600, word: 'h' }
  return { secs: 60, word: 'min' }
}

function clockOfDay(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

/** All display values for a rule's card. Pure, so it is unit-tested. */
export function cardMetrics(rule: NotificationRule): CardMetrics {
  const c = rule.config
  const st = rule.state || {}
  const isNote = rule.kind === 'note'
  const isTime = !isNote && NOTIFICATION_TIME_METRICS.has(c.metric ?? '')
  const value = typeof st.lastValue === 'number' ? st.lastValue : null
  const hasValue = value != null
  const threshold = c.threshold

  // Status pill.
  let status = { key: 'idle', label: 'Pending' }
  if (!rule.enabled) status = { key: 'off', label: 'Off' }
  else if (st.lastError) status = { key: 'warn', label: 'Error' }
  else if (st.triggered) status = { key: 'triggered', label: 'Triggered' }
  else if (hasValue || st.lastRunAt) status = { key: 'ok', label: 'OK' }

  const severityLabel =
    NOTIFICATION_SEVERITIES.find((s) => s.key === rule.severity)?.label || rule.severity

  const criterion = isNote
    ? noteCriterion(c)
    : rule.kind === 'journey_duration'
      ? `journey duration, ${(c.metric ?? '').toLowerCase()}`
      : `${(c.metric ?? '').toLowerCase()}, ${c.fromStep} → ${c.toStep}`
  const subtitle = [rule.connectionName, rule.projectTitle, criterion]
    .filter(Boolean)
    .join(' · ')

  // The unit used across the gauge + boxes (time metrics only).
  const unit = isTime ? timeUnit(Math.max(threshold, value ?? threshold)) : { secs: 1, word: '' }
  const fmtVal = (v: number) =>
    isNote ? `${v.toLocaleString()} note${v === 1 ? '' : 's'}`
      : isTime ? `${fmtClock(v)} ${unit.word}` : v.toLocaleString()

  // Gauge (only once there is a measured value) — note rules show the note itself instead.
  let gauge: Gauge | null = null
  if (hasValue && !isNote) {
    const maxVal = Math.max(threshold, value as number)
    const scaleMax = isTime
      ? niceCeil((maxVal / unit.secs) * 1.15) * unit.secs
      : niceCeil(maxVal * 1.15)
    const rightNum = isTime ? scaleMax / unit.secs : scaleMax
    gauge = {
      fillPct: clamp(((value as number) / scaleMax) * 100, 0, 100),
      limitPct: clamp((threshold / scaleMax) * 100, 0, 100),
      leftLabel: isTime ? `0 ${unit.word}` : '0',
      rightLabel: isTime ? `${Math.round(rightNum)} ${unit.word}` : rightNum.toLocaleString(),
      limitLabel: isTime ? `limit ${fmtClock(threshold)}` : `limit ${threshold.toLocaleString()}`,
    }
  }

  // Over/under limit box. The label follows the actual sign of the measured value relative
  // to the limit — below it reads "Under limit" (green), above it "Over limit".
  const over = c.comparator === '>' || c.comparator === '>='
  const delta = hasValue ? (value as number) - threshold : null
  let deltaValue = '—'
  let deltaPct = ''
  if (delta != null) {
    // No +/− sign — the "Over limit" / "Under limit" label already states the direction.
    const abs = Math.abs(delta)
    if (!isTime) {
      deltaValue = abs.toLocaleString()
    } else if (abs < 120) {
      // Seconds — keep a decimal for a small fractional (sub-second) breach, so a 0.4 s
      // overage reads "0.4 s" rather than rounding to a misleading "0 s".
      const dec = abs < 10 && !Number.isInteger(abs) ? 1 : 0
      deltaValue = `${abs.toFixed(dec)} s`
    } else {
      deltaValue = `${fmtClock(abs)} ${unit.word}`
    }
    if (threshold !== 0) {
      // More decimals for a tiny percentage, so it isn't swallowed to "0.0%".
      const p = Math.abs((delta / threshold) * 100)
      deltaPct = `(${p.toFixed(p >= 10 ? 0 : p >= 1 ? 1 : 2)}%)`
    }
  }

  return {
    status,
    severityLabel,
    criterion,
    subtitle,
    gauge,
    lastValue: hasValue ? fmtVal(value as number) : '—',
    deltaLabel:
      delta == null
        ? over
          ? 'Over limit'
          : 'Under limit'
        : delta < 0
          ? 'Under limit'
          : delta > 0
            ? 'Over limit'
            : 'At limit',
    deltaValue,
    deltaPct,
    // Green below the limit, red above it; neutral when exactly at it or not yet measured.
    deltaClass:
      delta == null ? 'idle' : delta < 0 ? 'ok' : delta > 0 ? 'fire' : 'idle',
    triggeredAt: st.triggered ? clockOfDay(st.triggeredAt) : '—',
    interval:
      NOTIFICATION_INTERVALS.find((i) => i.secs === rule.intervalSecs)?.label ||
      `${rule.intervalSecs}s`,
    lookback:
      !c.lookbackUnit || c.lookbackUnit === 'all' || !c.lookbackValue
        ? 'All history'
        : `${c.lookbackValue} ${c.lookbackValue === 1 ? c.lookbackUnit.replace(/s$/, '') : c.lookbackUnit}`,
    intervalShort: shortInterval(rule.intervalSecs),
    lookbackShort: shortLookback(c),
    isNote,
    note: (isNote && st.note) || null,
  }
}

export function NotificationCard({
  rule,
  canManage,
  onToggle,
  onRefresh,
  onAck,
  onOpen,
  busy,
}: {
  rule: NotificationRule
  canManage: boolean
  onToggle: (rule: NotificationRule) => void
  onRefresh: (rule: NotificationRule) => void
  onAck: (rule: NotificationRule) => void
  onOpen: (rule: NotificationRule) => void
  busy: boolean
}) {
  const m = cardMetrics(rule)
  const sevKey = rule.severity.toLowerCase()
  const isTriggered = m.status.key === 'triggered'
  // A note card with a matching note is clickable — it opens that note.
  const openable = m.isNote && !!m.note?.noteId
  const open = () => openable && onOpen(rule)
  const stop = (fn: () => void) => (e: ReactMouseEvent) => {
    e.stopPropagation()
    fn()
  }
  return (
    <div
      className={
        `nc${!rule.enabled ? ' off' : m.status.key === 'triggered' ? ' alert' : ''}` +
        (openable ? ' nc-open' : '')
      }
      onClick={openable ? open : undefined}
      role={openable ? 'button' : undefined}
      tabIndex={openable ? 0 : undefined}
      onKeyDown={
        openable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                open()
              }
            }
          : undefined
      }
      title={openable ? 'Open this note' : undefined}
    >
      {/* Row 1 — the title (and its subtitle) alone. */}
      <div className="nc-head">
        <span className="nc-bell" aria-hidden>
          {m.isNote ? '🗒️' : '🔔'}
        </span>
        <div className="nc-htext">
          <div className="nc-title">{rule.name || m.criterion}</div>
          <div className="nc-sub">{m.subtitle}</div>
        </div>
      </div>
      {/* Row 2 — the status + severity pills, then the per-card actions. */}
      <div className="nc-actions">
        <span className={`ncp ncp-${m.status.key}`}>{m.status.label}</span>
        <span className={`ncp ncp-${sevKey}`}>{m.severityLabel}</span>
        <span className="nc-aspacer" />
        <button
          className={`nc-refresh${busy ? ' spin' : ''}`}
          disabled={busy}
          onClick={stop(() => onRefresh(rule))}
          title="Check this rule against the current data now"
          aria-label="Refresh this rule"
        >
          ↻
        </button>
        {isTriggered && (
          <button
            className="nc-ack"
            disabled={busy}
            onClick={stop(() => onAck(rule))}
            title="Acknowledge — hide this alert until it clears and triggers again"
          >
            ✓ Acknowledge
          </button>
        )}
        {canManage && (
          <button
            className="nc-sw"
            role="switch"
            aria-checked={rule.enabled}
            disabled={busy}
            onClick={stop(() => onToggle(rule))}
            title={rule.enabled ? 'Disable this rule' : 'Enable this rule'}
            aria-label="Enable or disable this rule"
          />
        )}
      </div>

      {/* The gauge (bar) area is always present — reserved even when there is no gauge (note
          rules, or before the first measurement) — so the stat boxes below line up across
          every card in a row. */}
      <div className="nc-gauge">
        {m.gauge && (
          <>
            <div className="nc-track">
              <div className="nc-fill" style={{ width: `${m.gauge.fillPct}%` }} />
              <div className="nc-tick" style={{ left: `${m.gauge.limitPct}%` }} />
            </div>
            <div className="nc-scale">
              <span>{m.gauge.leftLabel}</span>
              <span
                className="nc-lim"
                style={{ left: `${clamp(m.gauge.limitPct, 6, 94)}%` }}
              >
                {m.gauge.limitLabel}
              </span>
              <span>{m.gauge.rightLabel}</span>
            </div>
          </>
        )}
      </div>

      <div className="nc-stats">
        {m.isNote ? (
          <>
            <div className="nc-box">
              <span className="nc-bl">Matching notes</span>
              <Marquee>{m.lastValue}</Marquee>
            </div>
            <div className="nc-box nc-box-wide">
              <span className="nc-bl">Latest note</span>
              <Marquee>
                {m.note ? (
                  <>
                    <i
                      className="nc-ndot"
                      style={{ background: NOTE_IMPORTANCE_META[normalizeImportance(m.note.importance)].color }}
                    />
                    {m.note.title}
                    {m.note.target ? ` — ${m.note.target}` : ''}
                  </>
                ) : (
                  '—'
                )}
              </Marquee>
            </div>
            <div className="nc-box">
              <span className="nc-bl">Seen at</span>
              <Marquee>{m.triggeredAt}</Marquee>
            </div>
          </>
        ) : (
          <>
            <div className="nc-box">
              <span className="nc-bl">Last value</span>
              <Marquee>{m.lastValue}</Marquee>
            </div>
            <div className="nc-box">
              <span className="nc-bl">{m.deltaLabel}</span>
              <Marquee className={m.deltaClass}>
                {m.deltaValue} {m.deltaPct && <small className="nc-pct">{m.deltaPct}</small>}
              </Marquee>
            </div>
            <div className="nc-box">
              <span className="nc-bl">Triggered at</span>
              <Marquee>{m.triggeredAt}</Marquee>
            </div>
          </>
        )}
        {/* Check interval + Base period combined into one (wider) box. */}
        <div className="nc-box nc-box-wide" title={`Check interval ${m.interval} · Base period ${m.lookback}`}>
          <span className="nc-bl">
            <span aria-hidden className="nc-ico">🛠️🕒</span> Interval
            <span className="nc-bsep"> · </span>
            <span aria-hidden className="nc-ico">⬅️🕒</span> Base
          </span>
          <Marquee className="nc-bv-dual">
            {m.interval} <span className="nc-bsep">·</span> {m.lookback}
          </Marquee>
        </div>
      </div>
    </div>
  )
}
