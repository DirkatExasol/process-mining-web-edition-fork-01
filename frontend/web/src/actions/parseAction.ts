// Parser for the Actions DSL — a small, business-readable script language that is
// translated (on the backend) into safe Exasol SQL, guided by the chart's filters.
//
// Grammar (case-insensitive keywords; NODE≡NODES, ENTRY≡ENTRIES):
//
//   AVAILABILITY  <ALL NODES | Step, Step, …>
//   SHOW          <LAST [N] LOG ENTRIES
//                  | TRANSITION TABLE WITH "COUNT"[,"%JOURNEY%"] [FOR LAST N LOG ENTRIES]>
//   FROM          NODE(<sel>[, <sel> …])      sel ∈ THIS|PREVIOUS|FOLLOWING|ALL FOLLOWING|ALL PREVIOUS
//   [SORT         ASCENDING | DESCENDING]
//   [WHERE        EVENT_ID :: [id, id, …]]
//
// A clause keyword may sit on its own line with its value on the following line(s),
// or share a line with its value; the value runs until the next clause keyword.

import {
  ACTION_METRICS,
  type ActionMetric,
  type ActionShow,
  type ActionSpec,
  type ActionTarget,
  type ActionWhere,
  type ParseError,
  type ParseResult,
  type Selector,
} from './types'

const CLAUSES = ['AVAILABILITY', 'SHOW', 'FROM', 'SORT', 'WHERE'] as const
type Clause = (typeof CLAUSES)[number]

// Accepted spellings for each transition metric → its canonical ACTION_METRICS token.
const METRIC_ALIASES: Record<string, ActionMetric> = {
  COUNT: 'COUNT',
  CNT: 'COUNT',
  '%JOURNEY%': '%JOURNEY%',
  'JOURNEY %': '%JOURNEY%',
  'JOURNEY%': '%JOURNEY%',
  JOURNEY: '%JOURNEY%',
  '%OUTGOING%': '%OUTGOING%',
  'OUTGOING %': '%OUTGOING%',
  OUTGOING: '%OUTGOING%',
  PERCENTAGE: '%OUTGOING%',
  '%': '%OUTGOING%',
  'AVG TIME': 'AVG TIME',
  AVG: 'AVG TIME',
  AVERAGE: 'AVG TIME',
  'MIN TIME': 'MIN TIME',
  MIN: 'MIN TIME',
  'MAX TIME': 'MAX TIME',
  MAX: 'MAX TIME',
  'STD DEV': 'STD DEV',
  STDDEV: 'STD DEV',
  STDEV: 'STD DEV',
  STD: 'STD DEV',
  'STANDARD DEVIATION': 'STD DEV',
}

interface RawClause {
  keyword: Clause
  value: string
  line: number // 1-based line of the keyword
}

const firstWord = (line: string): string => line.trim().split(/\s+/, 1)[0]?.toUpperCase() ?? ''

/** Split the script into clause blocks, keeping source line numbers for errors. */
function splitClauses(script: string): { clauses: RawClause[]; errors: ParseError[] } {
  const lines = script.split(/\r?\n/)
  const clauses: RawClause[] = []
  const errors: ParseError[] = []
  let current: RawClause | null = null
  const parts: string[] = []

  const flush = () => {
    if (current) {
      current.value = parts.join(' ').replace(/\s+/g, ' ').trim()
      clauses.push(current)
    }
    parts.length = 0
  }

  lines.forEach((raw, i) => {
    const trimmed = raw.trim()
    if (!trimmed) return
    const head = firstWord(trimmed)
    if ((CLAUSES as readonly string[]).includes(head)) {
      flush()
      current = { keyword: head as Clause, value: '', line: i + 1 }
      parts.push(trimmed.slice(head.length).trim())
    } else if (current) {
      parts.push(trimmed)
    } else {
      errors.push({ line: i + 1, message: `Unexpected text before any clause: "${trimmed}"` })
    }
  })
  flush()
  return { clauses, errors }
}

/** Normalise NODE/NODES and ENTRY/ENTRIES and collapse whitespace. */
const canon = (s: string): string =>
  s
    .toUpperCase()
    .replace(/\bNODES\b/g, 'NODE')
    .replace(/\bENTRIES\b/g, 'ENTRY')
    .replace(/\s+/g, ' ')
    .trim()

function parseAvailability(value: string, line: number, errors: ParseError[]): ActionSpec['availability'] {
  if (!value) {
    errors.push({ line, message: 'AVAILABILITY needs "ALL NODES" or a list of step names.' })
    return { allNodes: false, steps: [] }
  }
  if (canon(value) === 'ALL NODE') return { allNodes: true, steps: [] }
  const steps = value.split(',').map((s) => s.trim()).filter(Boolean)
  if (!steps.length) errors.push({ line, message: 'AVAILABILITY list is empty.' })
  return { allNodes: false, steps }
}

function parseShow(value: string, line: number, errors: ParseError[]): ActionShow {
  const c = canon(value)
  // LAST [N] LOG ENTRY
  const last = c.match(/^LAST(?:\s+(\d+))?\s+LOG ENTRY$/)
  if (last) {
    const limit = last[1] ? parseInt(last[1], 10) : 1
    if (limit < 1) errors.push({ line, message: 'SHOW LAST N: N must be at least 1.' })
    return { kind: 'logEntries', limit: Math.max(1, limit), metrics: [], forLast: null }
  }
  // TRANSITION TABLE WITH … [FOR LAST N LOG ENTRY]
  if (c.startsWith('TRANSITION TABLE')) {
    let forLast: number | null = null
    const forMatch = c.match(/\bFOR LAST\s+(\d+)\s+LOG ENTRY$/)
    let head = c
    if (forMatch) {
      forLast = parseInt(forMatch[1], 10)
      head = c.slice(0, forMatch.index).trim()
    }
    const withMatch = head.match(/^TRANSITION TABLE(?:\s+WITH\s+(.+))?$/)
    const metrics =
      withMatch && withMatch[1] ? parseMetricList(withMatch[1], line, errors, 'transition metric') : []
    if (!metrics.length) metrics.push('COUNT')
    return { kind: 'transitionTable', limit: 0, metrics, forLast }
  }
  // FLOWCHART [IN SEPARATE PANEL] [FOR <metric, metric, …>] — a full process map of
  // another project. The optional FOR lists which edge metrics the panel offers to
  // switch between (default: Count only).
  if (c.startsWith('FLOWCHART')) {
    const noPanel = c.replace(/\bIN SEPARATE PANEL\b/, ' ').replace(/\s+/g, ' ').trim()
    const m = noPanel.match(/^FLOWCHART(?:\s+FOR\s+(.+))?$/)
    if (m) {
      const metrics = m[1] ? parseMetricList(m[1], line, errors) : []
      return { kind: 'flowchart', limit: 0, metrics, forLast: null }
    }
  }
  errors.push({
    line,
    message:
      'SHOW must be "LAST [N] LOG ENTRIES", "TRANSITION TABLE WITH …" or "FLOWCHART [IN SEPARATE PANEL] [FOR <metrics>]".',
  })
  return { kind: 'logEntries', limit: 1, metrics: [], forLast: null }
}

/** Parse a comma-separated metric list (shared by TRANSITION TABLE WITH and FLOWCHART
 *  FOR). Accepts the "ALL METRICS" shorthand. `body` is already canon()'d (upper-cased). */
function parseMetricList(
  body: string,
  line: number,
  errors: ParseError[],
  noun = 'metric',
): ActionMetric[] {
  const metrics: ActionMetric[] = []
  const clean = body.replace(/["']/g, '').trim()
  if (clean === 'ALL METRICS' || clean === 'ALL METRIC') {
    metrics.push(...ACTION_METRICS) // every metric, in the canonical order
    return metrics
  }
  for (const token of body.split(',')) {
    const m = token.replace(/["']/g, '').trim()
    if (!m) continue
    const canonical = METRIC_ALIASES[m]
    if (canonical) {
      if (!metrics.includes(canonical)) metrics.push(canonical)
    } else {
      errors.push({
        line,
        message: `Unknown ${noun} "${m}". Supported: ${ACTION_METRICS.join(', ')}, or ALL METRICS.`,
      })
    }
  }
  return metrics
}

const SELECTORS: Record<string, Selector> = {
  THIS: 'THIS',
  PREVIOUS: 'PREVIOUS',
  FOLLOWING: 'FOLLOWING',
  'ALL FOLLOWING': 'ALL_FOLLOWING',
  'ALL PREVIOUS': 'ALL_PREVIOUS',
}

interface FromResult {
  selectors: Selector[]
  target: ActionTarget | null
}

function parseFrom(value: string, line: number, errors: ParseError[]): FromResult {
  // A "<connection>::<project>" target (for SHOW FLOWCHART). Case is preserved — these
  // are real connection/project names, so they are NOT canonicalised.
  const raw = value.trim()
  if (raw.includes('::')) {
    const idx = raw.indexOf('::')
    const connection = raw.slice(0, idx).trim()
    const project = raw.slice(idx + 2).trim()
    if (!connection || !project) {
      errors.push({ line, message: 'FROM must be "<connection>::<project>" (both parts required).' })
    }
    return { selectors: [], target: { connection, project } }
  }
  const c = canon(value)
  const m = c.match(/^NODE\s*\((.*)\)$/)
  if (!m) {
    errors.push({ line, message: 'FROM must be NODE(THIS | PREVIOUS | FOLLOWING | ALL FOLLOWING | ALL PREVIOUS, …), or "<connection>::<project>" for a flowchart.' })
    return { selectors: [], target: null }
  }
  const selectors: Selector[] = []
  for (const token of m[1].split(',')) {
    const key = token.trim()
    if (!key) continue
    const sel = SELECTORS[key]
    if (sel) {
      if (!selectors.includes(sel)) selectors.push(sel)
    } else {
      errors.push({ line, message: `Unknown node selector "${token.trim()}".` })
    }
  }
  if (!selectors.length) errors.push({ line, message: 'FROM NODE(...) needs at least one selector.' })
  return { selectors, target: null }
}

function parseSort(value: string, line: number, errors: ParseError[]): 'ASC' | 'DESC' | null {
  const c = canon(value)
  if (c === 'ASCENDING' || c === 'ASC') return 'ASC'
  if (c === 'DESCENDING' || c === 'DESC') return 'DESC'
  errors.push({ line, message: 'SORT must be ASCENDING or DESCENDING.' })
  return null
}

function parseWhere(value: string, line: number, errors: ParseError[]): ActionWhere | null {
  // v1: EVENT_ID :: [id, id, …]
  const m = value.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*::\s*\[(.*)\]\s*$/s)
  if (!m) {
    errors.push({ line, message: 'WHERE must be "EVENT_ID :: [id, id, …]".' })
    return null
  }
  const field = m[1].toUpperCase()
  if (field !== 'EVENT_ID') {
    errors.push({ line, message: `WHERE on "${m[1]}" is not supported in this version (only EVENT_ID).` })
    return null
  }
  const values = m[2].split(',').map((s) => s.trim()).filter(Boolean)
  if (!values.length) errors.push({ line, message: 'WHERE EVENT_ID :: [] needs at least one id.' })
  return { field: 'EVENT_ID', op: 'in', values }
}

export function parseAction(script: string): ParseResult {
  const { clauses, errors } = splitClauses(script)
  const seen = new Map<Clause, RawClause>()
  for (const cl of clauses) {
    if (seen.has(cl.keyword)) {
      errors.push({ line: cl.line, message: `Duplicate ${cl.keyword} clause.` })
      continue
    }
    seen.set(cl.keyword, cl)
  }

  const avail = seen.get('AVAILABILITY')
  const show = seen.get('SHOW')
  const from = seen.get('FROM')
  const sort = seen.get('SORT')
  const where = seen.get('WHERE')

  if (!avail) errors.push({ line: 0, message: 'Missing AVAILABILITY clause.' })
  if (!show) errors.push({ line: 0, message: 'Missing SHOW clause.' })
  if (!from) errors.push({ line: 0, message: 'Missing FROM clause.' })

  const availability = avail
    ? parseAvailability(avail.value, avail.line, errors)
    : { allNodes: false, steps: [] }
  const showSpec = show ? parseShow(show.value, show.line, errors) : null
  const fromRes: FromResult = from
    ? parseFrom(from.value, from.line, errors)
    : { selectors: [], target: null }
  const sortSpec = sort ? parseSort(sort.value, sort.line, errors) : null
  const whereSpec = where ? parseWhere(where.value, where.line, errors) : null

  // FLOWCHART needs a <connection>::<project> target; the other shows need NODE(...).
  if (showSpec && from) {
    if (showSpec.kind === 'flowchart' && !fromRes.target) {
      errors.push({ line: from.line, message: 'SHOW FLOWCHART needs FROM "<connection>::<project>".' })
    }
    if (showSpec.kind !== 'flowchart' && fromRes.target) {
      errors.push({ line: from.line, message: 'FROM "<connection>::<project>" is only valid with SHOW FLOWCHART; use FROM NODE(...).' })
    }
  }

  if (errors.length || !showSpec) return { spec: null, errors }

  return {
    spec: {
      availability,
      show: showSpec,
      from: { selectors: fromRes.selectors },
      target: fromRes.target,
      sort: sortSpec,
      where: whereSpec,
    },
    errors: [],
  }
}
