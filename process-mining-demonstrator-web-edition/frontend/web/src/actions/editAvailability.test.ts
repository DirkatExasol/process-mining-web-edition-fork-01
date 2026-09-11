import { describe, expect, it } from 'vitest'
import { insertAvailabilityStep } from './editAvailability'
import { parseAction } from './parseAction'

const avail = (script: string) => parseAction(script).spec?.availability

describe('insertAvailabilityStep', () => {
  it('replaces a lone ALL NODES with the picked step', () => {
    const out = insertAvailabilityStep('AVAILABILITY\n\tALL NODES\nSHOW\n\tLAST 1 LOG ENTRY\nFROM\n\tNODE(THIS)', 'Σ Payment')
    expect(avail(out)).toEqual({ allNodes: false, steps: ['Σ Payment'] })
  })

  it('appends to an existing step list', () => {
    const out = insertAvailabilityStep('AVAILABILITY\n\tLogin\nSHOW\n\tLAST 1 LOG ENTRY\nFROM\n\tNODE(THIS)', 'Σ Payment')
    expect(avail(out)?.steps).toEqual(['Login', 'Σ Payment'])
  })

  it('is a no-op when the step is already listed (glyph/case tolerant)', () => {
    const script = 'AVAILABILITY\n\tΣ Payment\nSHOW\n\tLAST 1 LOG ENTRY\nFROM\n\tNODE(THIS)'
    expect(insertAvailabilityStep(script, '∑ payment')).toBe(script)
  })

  it('keeps the other clauses intact', () => {
    const out = insertAvailabilityStep('AVAILABILITY\n\tALL NODES\nSHOW\n\tLAST 5 LOG ENTRIES\nFROM\n\tNODE(THIS)\nSORT\n\tDESCENDING', 'Payment')
    const spec = parseAction(out).spec
    expect(spec?.show.kind).toBe('logEntries')
    expect(spec?.from.selectors).toEqual(['THIS'])
    expect(spec?.availability.steps).toEqual(['Payment'])
  })

  it('adds an AVAILABILITY clause when none exists', () => {
    const out = insertAvailabilityStep('SHOW\n\tLAST 1 LOG ENTRY\nFROM\n\tNODE(THIS)', 'Payment')
    expect(avail(out)).toEqual({ allNodes: false, steps: ['Payment'] })
  })
})
