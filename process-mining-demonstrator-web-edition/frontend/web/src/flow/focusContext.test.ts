/** computeFocus — the hover-dwell spotlight set for one node: itself, its neighbours,
 *  and its incident edges. Drives which nodes/edges stay bright while the rest dim. */

import { describe, expect, it } from 'vitest'
import { computeFocus } from './focusContext'

const T = (fromStep: string, toStep: string) => ({ fromStep, toStep })

// A → B → C, plus A → C (a skip) and a self-loop on B.
const transitions = [T('A', 'B'), T('B', 'C'), T('A', 'C'), T('B', 'B')]

describe('computeFocus', () => {
  it('collects a node, its neighbours and its incident edges', () => {
    const f = computeFocus(transitions, 'B')
    // Incoming A→B, outgoing B→C, and the self-loop B→B.
    expect([...f.edges].sort()).toEqual(['A->B', 'B->B', 'B->C'])
    // Bright nodes: B plus the endpoints it connects to.
    expect([...f.nodes].sort()).toEqual(['A', 'B', 'C'])
    expect(f.node).toBe('B')
  })

  it('does not include unrelated edges', () => {
    const f = computeFocus(transitions, 'A')
    // A touches A→B and A→C, but never B→C.
    expect(f.edges.has('B->C')).toBe(false)
    expect([...f.edges].sort()).toEqual(['A->B', 'A->C'])
    expect([...f.nodes].sort()).toEqual(['A', 'B', 'C'])
  })

  it('handles a node with no connections', () => {
    const f = computeFocus(transitions, 'Z')
    expect(f.edges.size).toBe(0)
    expect([...f.nodes]).toEqual(['Z']) // only itself
  })
})
