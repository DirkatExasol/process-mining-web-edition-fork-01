/** buildSwimlane — turns a single journey's ordered trace into lane-grouped, strictly
 *  sequential nodes + edges (loops unrolled, one lane per node group, edge = inter-step time). */

import { describe, expect, it } from 'vitest'
import { buildSwimlane, cumulativeSeries } from './SwimlaneChart'
import type { JourneyEvent, ProcessGraph } from '../types'

function step(belongsTo: string | null, bg = '#111', fg = '#fff', score: number | null = null) {
  return {
    step: 's', description: '', bgColor: bg, fgColor: fg, score,
    shape: 'round', endOfProcess: false, belongsTo, eventTime: null,
  }
}

const steps: ProcessGraph['steps'] = {
  login: step('Auth'),
  search: step('Browse'),
  logout: step(null), // ungrouped
}

const seq: JourneyEvent[] = [
  { step: 'login', eventTime: '2026-01-01T08:00:00Z' },
  { step: 'search', eventTime: '2026-01-01T08:01:00Z' }, // +60s
  { step: 'login', eventTime: '2026-01-01T08:05:00Z' }, // a revisit — +240s
  { step: 'logout', eventTime: '2026-01-01T08:05:30Z' }, // +30s, ungrouped lane
]

describe('buildSwimlane', () => {
  it('unrolls loops into one sequential column per event', () => {
    const { nodes } = buildSwimlane(seq, steps)
    const stepNodes = nodes.filter((n) => n.type === 'swimStep')
    // 4 events → 4 columns, even though "login" occurs twice (no collapsing).
    expect(stepNodes.map((n) => n.id)).toEqual(['n:0', 'n:1', 'n:2', 'n:3'])
    // Columns are strictly left-to-right in event order.
    const xs = stepNodes.map((n) => n.position.x)
    expect(xs).toEqual([...xs].sort((a, b) => a - b))
    expect(new Set(xs).size).toBe(4)
  })

  it('makes one lane per node group (first-appearance order) + a header band', () => {
    const { nodes } = buildSwimlane(seq, steps)
    const lanes = nodes.filter((n) => n.type === 'swimLane').map((n) => n.id)
    // Header band first, then Auth, Browse, and an "(ungrouped)" lane for logout.
    expect(lanes).toEqual(['lane:__header__', 'lane:Auth', 'lane:Browse', 'lane:(ungrouped)'])
    // The two "login" events sit in the SAME lane (same y), the revisit included.
    const n0 = nodes.find((n) => n.id === 'n:0')!
    const n2 = nodes.find((n) => n.id === 'n:2')!
    const n1 = nodes.find((n) => n.id === 'n:1')!
    expect(n0.position.y).toBe(n2.position.y)
    expect(n1.position.y).not.toBe(n0.position.y)
  })

  it('labels each edge with the time from one node to the next', () => {
    const { edges } = buildSwimlane(seq, steps)
    expect(edges.map((e) => e.id)).toEqual(['e:1', 'e:2', 'e:3'])
    expect(edges.map((e) => e.source)).toEqual(['n:0', 'n:1', 'n:2'])
    expect(edges.map((e) => e.label)).toEqual(['1m', '4m', '30s'])
  })

  it('carries each event date/time in the header row', () => {
    const { nodes } = buildSwimlane(seq, steps)
    const times = nodes.filter((n) => n.type === 'swimTime')
    expect(times).toHaveLength(4) // one per event
  })

  it('returns nothing for an empty journey', () => {
    expect(buildSwimlane([], steps)).toEqual({ nodes: [], edges: [] })
  })

  it('gives every node an explicit size so ReactFlow keeps it visible', () => {
    // jsdom never measures (mocked ResizeObserver); without measured dims a node renders
    // visibility:hidden — the reactflow-drag-hidden-nodes gotcha.
    const { nodes } = buildSwimlane(seq, steps)
    for (const n of nodes) {
      expect(n.measured?.width).toBeGreaterThan(0)
      expect(n.measured?.height).toBeGreaterThan(0)
    }
  })

  it('adds one cumulative-value chart node below the lanes', () => {
    const { nodes } = buildSwimlane(seq, steps)
    const chart = nodes.filter((n) => n.type === 'swimChart')
    expect(chart).toHaveLength(1)
    // It sits below the lane stack (larger y than every step node).
    const maxStepY = Math.max(...nodes.filter((n) => n.type === 'swimStep').map((n) => n.position.y))
    expect(chart[0].position.y).toBeGreaterThan(maxStepY)
  })
})

describe('cumulativeSeries', () => {
  const scored: ProcessGraph['steps'] = {
    login: step('Auth', '#111', '#fff', 5),
    search: step('Browse', '#111', '#fff', -2),
    logout: step(null, '#111', '#fff', 3),
  }
  const s: JourneyEvent[] = [
    { step: 'login', eventTime: '2026-01-01T08:00:00Z' },
    { step: 'search', eventTime: '2026-01-01T08:01:00Z' },
    { step: 'logout', eventTime: '2026-01-01T08:02:00Z' },
    { step: 'search', eventTime: '2026-01-01T08:03:00Z' }, // revisit, another -2
  ]

  it('runs a +/- cumulative sum of step scores from the start', () => {
    const { points, min, max } = cumulativeSeries(s, scored)
    expect(points.map((p) => p.value)).toEqual([5, -2, 3, -2])
    expect(points.map((p) => p.cumulative)).toEqual([5, 3, 6, 4]) // running total
    // min/max always include 0 so the baseline is on-chart.
    expect(min).toBe(0)
    expect(max).toBe(6)
    // x is aligned to the step column centres, strictly increasing.
    const xs = points.map((p) => p.cx)
    expect(xs).toEqual([...xs].sort((a, b) => a - b))
  })

  it('treats a missing/unset score as 0', () => {
    const { points } = cumulativeSeries(
      [{ step: 'login', eventTime: 't' }, { step: 'ghost', eventTime: 't' }],
      { login: step('Auth', '#111', '#fff', 4) },
    )
    expect(points.map((p) => p.cumulative)).toEqual([4, 4]) // ghost has no score → +0
  })
})
