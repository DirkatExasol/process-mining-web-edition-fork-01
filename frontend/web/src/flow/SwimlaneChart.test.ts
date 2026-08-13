/** buildSwimlane — turns a single journey's ordered trace into lane-grouped, strictly
 *  sequential nodes + edges (loops unrolled, one lane per node group, edge = inter-step time). */

import { describe, expect, it } from 'vitest'
import { buildSwimlane } from './SwimlaneChart'
import type { JourneyEvent, ProcessGraph } from '../types'

function step(belongsTo: string | null, bg = '#111', fg = '#fff') {
  return {
    step: 's', description: '', bgColor: bg, fgColor: fg, score: null,
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
})
