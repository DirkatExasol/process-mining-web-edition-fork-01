/** Layout-engine tests — the ported Sugiyama layout must place nodes in the same
 *  layered structure as GraphLayout.compute in FlowChartView.swift. */

import { describe, expect, it } from 'vitest'
import { EMPTY_GRAPH, type ProcessGraph, type StepInfo } from '../types'
import { NODE_W, computeLayout, defaultNodeHeight, groupRects } from './layout'

function step(name: string, belongsTo: string | null = null): StepInfo {
  return {
    step: name,
    description: name,
    bgColor: 'blue',
    fgColor: 'white',
    score: null,
    shape: 'stadium',
    endOfProcess: false,
    belongsTo,
    eventTime: null,
  }
}

function graphFrom(edges: [string, string, number][], groups: Record<string, string> = {}): ProcessGraph {
  const names = new Set<string>()
  for (const [a, b] of edges) {
    names.add(a)
    names.add(b)
  }
  const steps: Record<string, StepInfo> = {}
  for (const name of names) steps[name] = step(name, groups[name] ?? null)
  return {
    steps,
    transitions: edges.map(([fromStep, toStep, occurrences]) => ({
      fromStep,
      toStep,
      occurrences,
      avgSecs: 60,
      minSecs: null,
      maxSecs: null,
      stdDevSecs: null,
    })),
  }
}

describe('computeLayout', () => {
  it('returns a default canvas for an empty graph', () => {
    const layout = computeLayout(EMPTY_GRAPH)
    expect(layout.nodePositions).toEqual({})
    expect(layout.canvasSize.width).toBeGreaterThan(0)
    expect(layout.canvasSize.height).toBeGreaterThan(0)
  })

  it('places a linear chain on descending layers', () => {
    const layout = computeLayout(
      graphFrom([
        ['A', 'B', 10],
        ['B', 'C', 8],
      ]),
    )
    const { A, B, C } = layout.nodePositions
    expect(A).toBeDefined()
    expect(B).toBeDefined()
    expect(C).toBeDefined()
    // Longest-path layering → strictly increasing y.
    expect(A.y).toBeLessThan(B.y)
    expect(B.y).toBeLessThan(C.y)
    expect(layout.canvasSize.width).toBeGreaterThanOrEqual(NODE_W)
  })

  it('spreads a fork onto the same layer', () => {
    const layout = computeLayout(
      graphFrom([
        ['A', 'B', 5],
        ['A', 'C', 5],
        ['B', 'D', 5],
        ['C', 'D', 5],
      ]),
    )
    const { A, B, C, D } = layout.nodePositions
    // B and C are both one layer below A and one above D.
    expect(B.y).toBeGreaterThan(A.y)
    expect(C.y).toBeGreaterThan(A.y)
    expect(Math.abs(B.y - C.y)).toBeLessThan(1) // same layer row
    expect(D.y).toBeGreaterThan(B.y)
    expect(B.x).not.toBe(C.x) // side by side, not overlapping
  })

  it('is deterministic for the same input', () => {
    const g = graphFrom([
      ['A', 'B', 3],
      ['A', 'C', 2],
      ['B', 'D', 1],
    ])
    expect(computeLayout(g).nodePositions).toEqual(computeLayout(g).nodePositions)
  })

  it('does not crash on a cyclic graph', () => {
    const layout = computeLayout(
      graphFrom([
        ['A', 'B', 5],
        ['B', 'A', 1],
      ]),
    )
    expect(Object.keys(layout.nodePositions).sort()).toEqual(['A', 'B'])
  })

  it('taller node height when a step carries a timestamp', () => {
    const timed = graphFrom([['A', 'B', 1]])
    timed.steps.A.eventTime = '2024-01-01T00:00:00'
    expect(defaultNodeHeight(timed)).toBeGreaterThan(defaultNodeHeight(graphFrom([['A', 'B', 1]])))
  })
})

describe('groupRects', () => {
  it('produces one non-overlapping box per BELONGS_TO group', () => {
    const g = graphFrom(
      [
        ['A', 'B', 5],
        ['B', 'C', 5],
      ],
      { A: 'G1', B: 'G1', C: 'G2' },
    )
    const layout = computeLayout(g)
    const rects = groupRects(g, layout.nodePositions, new Set(), defaultNodeHeight(g), (grp) => `__group__${grp}`)
    expect(rects.map((r) => r.name).sort()).toEqual(['G1', 'G2'])
    const [g1, g2] = rects
    // Rects have positive area.
    for (const { rect } of rects) {
      expect(rect.width).toBeGreaterThan(0)
      expect(rect.height).toBeGreaterThan(0)
    }
    // The two group boxes were pushed apart (no full overlap).
    const overlap =
      g1.rect.x < g2.rect.x + g2.rect.width &&
      g2.rect.x < g1.rect.x + g1.rect.width &&
      g1.rect.y < g2.rect.y + g2.rect.height &&
      g2.rect.y < g1.rect.y + g1.rect.height
    expect(overlap).toBe(false)
  })

  it('reserves more label space when the group-title scale grows', () => {
    const g = graphFrom([['A', 'B', 5]], { A: 'G1', B: 'G1' })
    const layout = computeLayout(g)
    const h = defaultNodeHeight(g)
    const id = (grp: string) => `__group__${grp}`
    const small = groupRects(g, layout.nodePositions, new Set(), h, id, NODE_W, 1)
    const large = groupRects(g, layout.nodePositions, new Set(), h, id, NODE_W, 3)
    // A larger title pill pushes the box top up and makes the box taller, so the
    // rendered pill never overlaps the reserved band — same node positions.
    expect(large[0].rect.y).toBeLessThan(small[0].rect.y)
    expect(large[0].rect.height).toBeGreaterThan(small[0].rect.height)
  })
})

describe('node scaling', () => {
  it('a larger nodeWidth widens the canvas and node spacing', () => {
    // Two sibling nodes on the same layer, so horizontal spacing depends on width.
    const graph = graphFrom([
      ['Start', 'A', 5],
      ['Start', 'B', 5],
    ])
    const base = computeLayout(graph, defaultNodeHeight(graph), true, NODE_W)
    const big = computeLayout(graph, defaultNodeHeight(graph), true, NODE_W * 1.5)

    expect(big.canvasSize.width).toBeGreaterThan(base.canvasSize.width)
    // The two same-layer siblings are pushed further apart at the larger width.
    const gap = (l: typeof base) =>
      Math.abs(l.nodePositions['A'].x - l.nodePositions['B'].x)
    expect(gap(big)).toBeGreaterThan(gap(base))
  })
})
