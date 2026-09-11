import { describe, expect, it } from 'vitest'
import type { HappyPathNode } from '../types'
import {
  isSplit,
  migrateHappyPath,
  splitNode,
  stepNode,
  updateNode,
  usedSteps,
} from './happyPath'

describe('happyPath node helpers', () => {
  it('stepNode is a step; splitNode is a split', () => {
    const s = stepNode('A')
    expect(s.step).toBe('A')
    expect(isSplit(s)).toBe(false)
    const sp = splitNode()
    expect(isSplit(sp)).toBe(true)
    expect(sp.branches).toEqual([[], []]) // seeded with two empty branches
  })
})

describe('migrateHappyPath', () => {
  it('passes through a payload that already has nodes', () => {
    const nodes: HappyPathNode[] = [stepNode('A')]
    const out = migrateHappyPath({ id: 'X', name: 'P', nodes })
    expect(out.nodes).toBe(nodes)
  })

  it('folds a legacy trunk into step nodes', () => {
    const out = migrateHappyPath({ id: 'X', name: 'P', steps: ['A', 'B', 'C'] })
    expect(out.nodes.map((n) => n.step)).toEqual(['A', 'B', 'C'])
    expect(out.nodes.every((n) => !isSplit(n))).toBe(true)
  })

  it('folds legacy branches into one trailing split (drops empty branches)', () => {
    const out = migrateHappyPath({
      id: 'X',
      name: 'P',
      steps: ['A', 'B'],
      branches: [
        { label: 'l', steps: ['C'] },
        { steps: ['D'] },
        { steps: [] }, // dropped
      ],
    })
    expect(out.nodes.slice(0, 2).map((n) => n.step)).toEqual(['A', 'B'])
    const split = out.nodes[2]
    expect(isSplit(split)).toBe(true)
    expect(split.branches.map((b) => b.map((n) => n.step))).toEqual([['C'], ['D']])
  })

  it('a trunk-only legacy path gets no split', () => {
    const out = migrateHappyPath({ id: 'X', name: 'P', steps: ['A'], branches: [] })
    expect(out.nodes.map((n) => n.step)).toEqual(['A'])
  })
})

describe('usedSteps + updateNode', () => {
  const nested: HappyPathNode[] = [
    stepNode('A'),
    { id: 'S1', step: '', label: 'top', branches: [
      [stepNode('B'), { id: 'S2', step: '', label: 'inner', branches: [[stepNode('C')], [stepNode('D')]] }],
      [stepNode('E')],
    ] },
    stepNode('F'),
  ]

  it('collects every step across the whole tree', () => {
    expect([...usedSteps(nested)].sort()).toEqual(['A', 'B', 'C', 'D', 'E', 'F'])
  })

  it('updates a nested node by id, immutably', () => {
    const out = updateNode(nested, 'S2', (n) => ({ ...n, label: 'renamed' }))
    // the nested split is renamed…
    expect(out[1].branches[0][1].label).toBe('renamed')
    // …and the original tree is untouched (immutable)
    expect(nested[1].branches[0][1].label).toBe('inner')
  })
})
