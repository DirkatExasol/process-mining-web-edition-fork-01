// Types for the Actions feature: the business-readable action DSL, its parsed
// spec (the AST that is sent to the backend and translated to SQL), and the shapes
// returned when an action runs. See parseAction.ts for the grammar.

/** A node selector, relative to the node an action is run from ("THIS"). */
export type Selector =
  | 'THIS'
  | 'PREVIOUS'
  | 'FOLLOWING'
  | 'ALL_FOLLOWING'
  | 'ALL_PREVIOUS'

export type ShowKind = 'logEntries' | 'transitionTable'

/** Transition-table metrics — the same set the chart offers (canonical tokens). */
export const ACTION_METRICS = [
  'COUNT',
  '%JOURNEY%', // share of all filtered journeys that traverse the edge
  '%OUTGOING%', // branching share of the source node's outgoing journeys
  'AVG TIME', // transition times, in seconds
  'MIN TIME',
  'MAX TIME',
  'STD DEV',
] as const
export type ActionMetric = (typeof ACTION_METRICS)[number]

export interface ActionShow {
  kind: ShowKind
  /** logEntries: how many rows (SHOW LAST N LOG ENTRIES; default 1). */
  limit: number
  /** transitionTable: the requested metric columns. Empty for logEntries. */
  metrics: ActionMetric[]
  /** transitionTable: optional "FOR LAST N LOG ENTRIES" recency cap (null = none). */
  forLast: number | null
}

export interface ActionAvailability {
  /** True for "AVAILABILITY ALL NODES" — the action shows on every node. */
  allNodes: boolean
  /** Otherwise, the step names this action is offered on. */
  steps: string[]
}

/** v1 supports only "WHERE EVENT_ID :: [id, …]" (`::` = "in"). */
export interface ActionWhere {
  field: 'EVENT_ID'
  op: 'in'
  values: string[]
}

export interface ActionSpec {
  availability: ActionAvailability
  show: ActionShow
  from: { selectors: Selector[] }
  /** Log-entry ordering by EVENT_TIME; null means the default (DESC = most recent). */
  sort: 'ASC' | 'DESC' | null
  where: ActionWhere | null
}

export interface ParseError {
  /** 1-based source line the error is anchored to (0 if unknown). */
  line: number
  message: string
}

export interface ParseResult {
  spec: ActionSpec | null
  errors: ParseError[]
}

/** A saved, named action as stored on the backend and listed in node menus. */
export interface SavedAction {
  id: string
  name: string
  script: string
  spec: ActionSpec
  enabled: boolean
}

/** Result of running an action — a generic table the UI renders as-is. */
export interface ActionRunResult {
  kind: ShowKind
  columns: string[]
  rows: (string | number | null)[][]
  /** How many context nodes the query was scoped to (for the results header). */
  nodeCount?: number
}
