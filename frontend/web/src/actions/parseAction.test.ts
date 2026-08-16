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

describe('parseAction — SHOW FLOWCHART (cross-project)', () => {
  it('parses a flowchart with a connection::project target, preserving case & spaces', () => {
    const spec = ok(`AVAILABILITY
\tPAYMENT
SHOW
\tFLOWCHART IN SEPARATE PANEL
FROM
\t01 - Exasol Nano @ Macbook Pro::Airport Passenger Flow Analysis`)
    expect(spec.availability.steps).toEqual(['PAYMENT'])
    expect(spec.show.kind).toBe('flowchart')
    expect(spec.from.selectors).toEqual([])
    expect(spec.target).toEqual({
      connection: '01 - Exasol Nano @ Macbook Pro',
      project: 'Airport Passenger Flow Analysis',
    })
  })

  it('accepts a bare FLOWCHART keyword', () => {
    const spec = ok('AVAILABILITY ALL NODES\nSHOW FLOWCHART\nFROM ConnA::Proj B')
    expect(spec.show.kind).toBe('flowchart')
    expect(spec.target).toEqual({ connection: 'ConnA', project: 'Proj B' })
  })

  it('accepts FLOWCHART … FOR with one or more metrics', () => {
    const spec = ok('AVAILABILITY ALL NODES\nSHOW FLOWCHART IN SEPARATE PANEL FOR Count, Avg Time\nFROM ConnA::Proj B')
    expect(spec.show.kind).toBe('flowchart')
    expect(spec.show.metrics).toEqual(['COUNT', 'AVG TIME'])
  })

  it('accepts FOR before IN SEPARATE PANEL and ALL METRICS shorthand', () => {
    const a = ok('AVAILABILITY ALL NODES\nSHOW FLOWCHART FOR Count IN SEPARATE PANEL\nFROM ConnA::Proj B')
    expect(a.show.metrics).toEqual(['COUNT'])
    const b = ok('AVAILABILITY ALL NODES\nSHOW FLOWCHART FOR ALL METRICS\nFROM ConnA::Proj B')
    expect(b.show.metrics.length).toBe(7)
  })

  it('flags an unknown FLOWCHART metric', () => {
    const e = parseAction('AVAILABILITY ALL NODES\nSHOW FLOWCHART FOR Bananas\nFROM ConnA::Proj B').errors
    expect(e.some((x) => /Unknown metric "BANANAS"/.test(x.message))).toBe(true)
  })

  it('requires a target for FLOWCHART', () => {
    const e = parseAction('AVAILABILITY ALL NODES\nSHOW FLOWCHART IN SEPARATE PANEL\nFROM NODE(THIS)').errors
    expect(e.some((x) => /FLOWCHART needs FROM/.test(x.message))).toBe(true)
  })

  it('rejects a connection::project target for non-flowchart shows', () => {
    const e = parseAction('AVAILABILITY ALL NODES\nSHOW LAST 1 LOG ENTRY\nFROM ConnA::ProjB').errors
    expect(e.some((x) => /only valid with SHOW FLOWCHART/.test(x.message))).toBe(true)
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
