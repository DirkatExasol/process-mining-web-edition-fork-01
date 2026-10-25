/** cardMetrics — the pure display math behind a notification gauge card — plus the card's
 *  second-row actions (refresh / acknowledge / switch). */

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { cardMetrics, fmtClock, niceCeil, NotificationCard } from './NotificationCard'
import type { NotificationRule } from '../types'

const rule = (over: Partial<NotificationRule> = {}): NotificationRule => ({
  id: 'r', connectionId: 'c', connectionName: '01 - Air Travel', projectId: 1,
  projectTitle: 'Airport Passenger Flow', kind: 'transition_metric', name: '',
  severity: 'URGENT', intervalSecs: 300, enabled: true,
  config: { fromStep: 'enter', toStep: 'leave security check', metric: 'Avg Time', comparator: '>', threshold: 960 },
  state: {},
  ...over,
})

describe('fmtClock / niceCeil', () => {
  it('formats durations as m:ss or h:mm:ss', () => {
    expect(fmtClock(1020)).toBe('17:00')
    expect(fmtClock(960)).toBe('16:00')
    expect(fmtClock(9000)).toBe('2:30:00')
  })
  it('rounds up to a nice top-of-scale', () => {
    expect(niceCeil(19.55)).toBe(20)
    expect(niceCeil(17)).toBe(20)
    expect(niceCeil(26)).toBe(30)
  })
})

describe('cardMetrics — the screenshot scenario (avg time, over a 16:00 limit)', () => {
  const m = cardMetrics(rule({
    state: { triggered: true, triggeredAt: '2026-09-14T10:55:00Z', lastValue: 1020, lastRunAt: 'x' },
  }))

  it('builds the subtitle and status', () => {
    expect(m.subtitle).toBe('01 - Air Travel · Airport Passenger Flow · avg time, enter → leave security check')
    expect(m.status).toEqual({ key: 'triggered', label: 'Triggered' })
    expect(m.severityLabel).toBe('Urgent')
  })

  it('scales the gauge to 20 min with the limit at 16:00', () => {
    expect(m.gauge).not.toBeNull()
    expect(m.gauge!.rightLabel).toBe('20 min')
    expect(m.gauge!.leftLabel).toBe('0 min')
    expect(m.gauge!.limitLabel).toBe('limit 16:00')
    expect(Math.round(m.gauge!.fillPct)).toBe(85) // 1020 / 1200
    expect(Math.round(m.gauge!.limitPct)).toBe(80) // 960 / 1200
  })

  it('reports the last value and the over-limit breach', () => {
    expect(m.lastValue).toBe('17:00 min')
    expect(m.deltaLabel).toBe('Over limit')
    expect(m.deltaValue).toBe('60 s')
    expect(m.deltaPct).toBe('(6.3%)')
    expect(m.deltaClass).toBe('fire')
    expect(m.interval).toBe('5 minutes')
  })
})

describe('cardMetrics — other states', () => {
  it('shows no gauge and dashes before the first run', () => {
    const m = cardMetrics(rule())
    expect(m.gauge).toBeNull()
    expect(m.lastValue).toBe('—')
    expect(m.deltaValue).toBe('—')
    expect(m.triggeredAt).toBe('—')
  })

  it('is OK and green within the limit, and the box reads "Under limit"', () => {
    const m = cardMetrics(rule({ state: { lastRunAt: 'x', lastValue: 600, triggered: false } }))
    expect(m.status.label).toBe('OK')
    expect(m.deltaLabel).toBe('Under limit') // below the limit → "Under limit"
    expect(m.deltaClass).toBe('ok') // …and green
    expect(m.deltaValue).toBe('6:00 min') // |600 − 960| = 360 s, unsigned
  })

  it('handles a count metric and an under-limit (<) rule', () => {
    const m = cardMetrics(rule({
      severity: 'INFO',
      config: { fromStep: 'A', toStep: 'B', metric: 'Count', comparator: '<', threshold: 1000 },
      state: { triggered: true, triggeredAt: 'x', lastValue: 200, lastRunAt: 'x' },
    }))
    expect(m.deltaLabel).toBe('Under limit')
    expect(m.lastValue).toBe('200')
    expect(m.gauge!.limitLabel).toBe('limit 1,000')
    expect(m.deltaValue).toBe('800')
  })

  it('shows sub-second precision for a tiny overage', () => {
    const m = cardMetrics(rule({
      config: { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 1020 },
      state: { triggered: true, triggeredAt: 'x', lastValue: 1020.4, lastRunAt: 'x' },
    }))
    expect(m.lastValue).toBe('17:00 min') // headline still rounds
    expect(m.deltaValue).toBe('0.4 s') // …but the breach reads precisely, not "0 s"
    expect(m.deltaPct).toBe('(0.04%)')
  })

  it('reports Off when disabled', () => {
    expect(cardMetrics(rule({ enabled: false })).status).toEqual({ key: 'off', label: 'Off' })
  })

  it('describes a journey_duration rule without steps', () => {
    const m = cardMetrics(rule({
      kind: 'journey_duration',
      config: { metric: 'Max Time', comparator: '>', threshold: 7200 },
      state: { triggered: true, triggeredAt: 'x', lastValue: 9000, lastRunAt: 'x' },
    }))
    expect(m.criterion).toBe('journey duration, max time')
    expect(m.subtitle).toBe('01 - Air Travel · Airport Passenger Flow · journey duration, max time')
    expect(m.lastValue).toBe('2:30:00 h')
  })

  it('shows the base period (lookback)', () => {
    const cfg = { fromStep: 'A', toStep: 'B', metric: 'Avg Time' as const, comparator: '>', threshold: 960 }
    expect(cardMetrics(rule({ config: cfg })).lookback).toBe('All history')
    expect(cardMetrics(rule({ config: { ...cfg, lookbackUnit: 'days', lookbackValue: 7 } })).lookback).toBe('7 days')
    expect(cardMetrics(rule({ config: { ...cfg, lookbackUnit: 'days', lookbackValue: 1 } })).lookback).toBe('1 day')
  })

  it('gives compact interval/base tokens for the combined box', () => {
    const cfg = { fromStep: 'A', toStep: 'B', metric: 'Avg Time' as const, comparator: '>', threshold: 960 }
    expect(cardMetrics(rule({ intervalSecs: 300, config: cfg })).intervalShort).toBe('5m')
    expect(cardMetrics(rule({ intervalSecs: 3600, config: cfg })).intervalShort).toBe('1h')
    expect(cardMetrics(rule({ intervalSecs: 86400, config: cfg })).intervalShort).toBe('1d')
    expect(cardMetrics(rule({ config: cfg })).lookbackShort).toBe('All')
    expect(cardMetrics(rule({ config: { ...cfg, lookbackUnit: 'days', lookbackValue: 7 } })).lookbackShort).toBe('7d')
    expect(cardMetrics(rule({ config: { ...cfg, lookbackUnit: 'months', lookbackValue: 3 } })).lookbackShort).toBe('3mo')
  })
})

describe('NotificationCard — second-row actions', () => {
  const render0 = (over: Partial<NotificationRule> = {}, onAck = vi.fn()) => {
    render(
      <NotificationCard
        rule={rule(over)}
        canManage
        onToggle={vi.fn()}
        onRefresh={vi.fn()}
        onAck={onAck}
        onOpen={vi.fn()}
        busy={false}
      />,
    )
    return onAck
  }

  it('shows Acknowledge only while triggered, and calls onAck', () => {
    const onAck = render0({
      state: { triggered: true, triggeredAt: '2026-10-20T10:00:00Z', lastValue: 1020, lastRunAt: 'x' },
    })
    fireEvent.click(screen.getByText('✓ Acknowledge'))
    expect(onAck).toHaveBeenCalledTimes(1)
  })

  it('hides Acknowledge when the rule is not triggered', () => {
    render0({ state: { triggered: false, lastRunAt: 'x', lastValue: 600 } })
    expect(screen.queryByText('✓ Acknowledge')).toBeNull()
  })
})

describe('NotificationCard — note kind', () => {
  const noteRule = (): NotificationRule => rule({
    kind: 'note',
    config: { comparator: '>=', threshold: 1, event: 'created', scope: 'shared', minImportance: 'IMPORTANT' } as never,
    state: {
      triggered: true, triggeredAt: '2026-10-20T10:00:00Z', lastValue: 3, lastRunAt: 'x',
      note: { noteId: 'n1', title: 'Check this step', target: 'Enter', at: '2026-10-20T10:00:00Z', importance: 'URGENT', count: 3, scope: 'shared', event: 'created' } as never,
    },
  })

  it('shows the note metrics and matching count', () => {
    const m = cardMetrics(noteRule())
    expect(m.isNote).toBe(true)
    expect(m.criterion).toBe('notes · new notes · shared · important+')
    expect(m.lastValue).toBe('3 notes')
    expect(m.note?.title).toBe('Check this step')
  })

  it('renders a clickable card that calls onOpen', () => {
    const onOpen = vi.fn()
    render(
      <NotificationCard
        rule={noteRule()}
        canManage
        onToggle={vi.fn()}
        onRefresh={vi.fn()}
        onAck={vi.fn()}
        onOpen={onOpen}
        busy={false}
      />,
    )
    fireEvent.click(screen.getByText(/Check this step/))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })
})
