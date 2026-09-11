import { describe, expect, it } from 'vitest'
import { outgoingNormSummary } from './ConformanceView'

describe('outgoingNormSummary (Conformance edit-mode remaining %)', () => {
  it('reports what is left to reach 100% across a node’s outgoing edges', () => {
    const norms = { 'A->B': 30, 'A->C': 20, 'X->Y': 99 } // X->Y is a different node
    const s = outgoingNormSummary(norms, 'A', 'D', '') // editing a new edge A->D
    expect(s.assignedOthers).toBe(50) // 30 + 20 from A's other edges only
    expect(s.otherCount).toBe(2)
    expect(s.remaining).toBe(50) // 100 - 50
    expect(s.over).toBe(false)
  })

  it('excludes the edge being edited from the "others" sum', () => {
    const norms = { 'A->B': 30, 'A->C': 20 }
    const s = outgoingNormSummary(norms, 'A', 'B', '25') // re-editing A->B
    expect(s.assignedOthers).toBe(20) // only A->C counts
    expect(s.remaining).toBe(80)
    expect(s.total).toBe(45) // 20 others + 25 typed
  })

  it('factors the typed value into the total and flags going over 100%', () => {
    const norms = { 'A->B': 70 }
    const over = outgoingNormSummary(norms, 'A', 'C', '40')
    expect(over.total).toBe(110)
    expect(over.over).toBe(true)
    const exact = outgoingNormSummary(norms, 'A', 'C', '30')
    expect(exact.total).toBe(100)
    expect(exact.over).toBe(false)
  })

  it('treats blank / non-numeric input as 0 and rounds tidily', () => {
    const norms = { 'A->B': 33.3, 'A->C': 33.3 }
    const s = outgoingNormSummary(norms, 'A', 'D', 'abc')
    expect(s.total).toBe(66.6) // typed → 0
    expect(s.remaining).toBe(33.4) // 100 - 66.6, one-decimal rounded
  })
})
