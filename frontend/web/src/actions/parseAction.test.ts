import { describe, expect, it } from 'vitest'
import { parseAction } from './parseAction'

const ok = (script: string) => {
  const { spec, errors } = parseAction(script)
  expect(errors).toEqual([])
  expect(spec).not.toBeNull()
  return spec!
}

describe('parseAction — the example scripts from the spec', () => {
  it('AVAILABILITY PAYMENT / SHOW LAST 1 LOG ENTRY / FROM NODE(THIS) / SORT DESCENDING', () => {
    const spec = ok(`AVAILABILITY
\tPAYMENT
SHOW
\tLAST 1 LOG ENTRY
FROM
\tNODE(THIS)
SORT
\tDESCENDING`)
    expect(spec.availability).toEqual({ allNodes: false, steps: ['PAYMENT'] })
    expect(spec.show).toEqual({ kind: 'logEntries', limit: 1, metrics: [], forLast: null })
    expect(spec.from.selectors).toEqual(['THIS'])
    expect(spec.sort).toBe('DESC')
    expect(spec.where).toBeNull()
  })

  it('multiple availability steps + SHOW LAST LOG ENTRY (no N ⇒ 1) + NODE(PREVIOUS)', () => {
    const spec = ok(`AVAILABILITY
\tLOGIN, LOGOUT, PAYMENT
SHOW
\tLAST LOG ENTRY
FROM
\tNODE(PREVIOUS)`)
    expect(spec.availability.steps).toEqual(['LOGIN', 'LOGOUT', 'PAYMENT'])
    expect(spec.show.limit).toBe(1)
    expect(spec.from.selectors).toEqual(['PREVIOUS'])
    expect(spec.sort).toBeNull()
  })

  it('ALL NODES + LAST 100 LOG ENTRIES + NODE(FOLLOWING)', () => {
    const spec = ok(`AVAILABILITY
\tALL NODES
SHOW
\tLAST 100 LOG ENTRIES
FROM
\tNODE(FOLLOWING)`)
    expect(spec.availability).toEqual({ allNodes: true, steps: [] })
    expect(spec.show.limit).toBe(100)
    expect(spec.from.selectors).toEqual(['FOLLOWING'])
  })

  it('NODE(THIS,PREVIOUS,FOLLOWING) + WHERE EVENT_ID :: [list]', () => {
    const spec = ok(`AVAILABILITY
\tALL NODES
SHOW
\tLAST 5 LOG ENTRIES
FROM
\tNODE(THIS,PREVIOUS,FOLLOWING)
WHERE
\tEVENT_ID :: [CRA-000124, CRA-000125]`)
    expect(spec.from.selectors).toEqual(['THIS', 'PREVIOUS', 'FOLLOWING'])
    expect(spec.where).toEqual({ field: 'EVENT_ID', op: 'in', values: ['CRA-000124', 'CRA-000125'] })
  })

  it('TRANSITION TABLE WITH "COUNT","%JOURNEY%" FOR LAST 50 LOG ENTRIES + NODE(THIS, ALL FOLLOWING)', () => {
    const spec = ok(`AVAILABILITY
\tALL NODES
SHOW
\tTRANSITION TABLE WITH "COUNT", "%JOURNEY%"
\tFOR LAST 50 LOG ENTRIES
FROM
\tNODE(THIS, ALL FOLLOWING)`)
    expect(spec.show.kind).toBe('transitionTable')
    expect(spec.show.metrics).toEqual(['COUNT', '%JOURNEY%'])
    expect(spec.show.forLast).toBe(50)
    expect(spec.from.selectors).toEqual(['THIS', 'ALL_FOLLOWING'])
  })
})

describe('parseAction — keyword equivalences & case', () => {
  it('treats NODE≡NODES and ENTRY≡ENTRIES and is case-insensitive on keywords', () => {
    const spec = ok(`availability all nodes
show last 3 log entry
from nodes(all previous)`)
    expect(spec.availability.allNodes).toBe(true)
    expect(spec.show.limit).toBe(3)
    expect(spec.from.selectors).toEqual(['ALL_PREVIOUS'])
  })

  it('accepts a clause value on the same line as its keyword', () => {
    const spec = ok('AVAILABILITY PAYMENT\nSHOW LAST LOG ENTRY\nFROM NODE(THIS)')
    expect(spec.availability.steps).toEqual(['PAYMENT'])
  })

  it('transition table defaults to COUNT when no WITH given', () => {
    const spec = ok('AVAILABILITY ALL NODES\nSHOW TRANSITION TABLE\nFROM NODE(THIS)')
    expect(spec.show.metrics).toEqual(['COUNT'])
    expect(spec.show.forLast).toBeNull()
  })

  it('expands "ALL METRICS" to every metric in canonical order', () => {
    const spec = ok('AVAILABILITY ALL NODES\nSHOW TRANSITION TABLE WITH ALL METRICS\nFROM NODE(THIS)')
    expect(spec.show.metrics).toEqual([
      'COUNT',
      '%JOURNEY%',
      '%OUTGOING%',
      'AVG TIME',
      'MIN TIME',
      'MAX TIME',
      'STD DEV',
    ])
  })

  it('accepts all transition metrics, incl. friendly aliases, canonicalised', () => {
    const spec = ok(
      'AVAILABILITY ALL NODES\n' +
        'SHOW TRANSITION TABLE WITH "COUNT", "%OUTGOING%", "AVG", "min", "Std Dev", "MAX TIME", "journey %"\n' +
        'FROM NODE(THIS)',
    )
    expect(spec.show.metrics).toEqual([
      'COUNT',
      '%OUTGOING%',
      'AVG TIME',
      'MIN TIME',
      'STD DEV',
      'MAX TIME',
      '%JOURNEY%',
    ])
  })
})

describe('parseAction — errors', () => {
  const errs = (script: string) => parseAction(script).errors

  it('reports missing required clauses', () => {
    const e = errs('SHOW LAST LOG ENTRY')
    expect(e.some((x) => /AVAILABILITY/.test(x.message))).toBe(true)
    expect(e.some((x) => /FROM/.test(x.message))).toBe(true)
  })

  it('rejects an unknown node selector', () => {
    const e = errs('AVAILABILITY ALL NODES\nSHOW LAST LOG ENTRY\nFROM NODE(SIDEWAYS)')
    expect(e.some((x) => /Unknown node selector/.test(x.message))).toBe(true)
  })

  it('rejects an unknown SHOW form', () => {
    const e = errs('AVAILABILITY ALL NODES\nSHOW SOMETHING ELSE\nFROM NODE(THIS)')
    expect(e.some((x) => /SHOW must be/.test(x.message))).toBe(true)
  })

  it('rejects an unknown transition metric', () => {
    const e = errs('AVAILABILITY ALL NODES\nSHOW TRANSITION TABLE WITH "BOGUS"\nFROM NODE(THIS)')
    expect(e.some((x) => /Unknown transition metric/.test(x.message))).toBe(true)
  })

  it('rejects a WHERE on a column other than EVENT_ID', () => {
    const e = errs('AVAILABILITY ALL NODES\nSHOW LAST LOG ENTRY\nFROM NODE(THIS)\nWHERE STEP :: [A]')
    expect(e.some((x) => /not supported/.test(x.message))).toBe(true)
  })
})
