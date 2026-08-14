// Human-readable helpers for the Actions DSL: a plain-English restatement shown in
// the builder, and the availability check used to decide whether a saved action
// appears in a given node's context menu.

import type { ActionSpec, Selector } from './types'

const SELECTOR_PHRASES: Record<Selector, string> = {
  THIS: 'this node',
  PREVIOUS: 'the preceding nodes',
  FOLLOWING: 'the following nodes',
  ALL_FOLLOWING: 'every node that follows',
  ALL_PREVIOUS: 'every node that precedes',
}

function joinPhrases(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/** True if an action with this spec should be offered on `node`. */
export function actionMatchesNode(spec: ActionSpec, node: string): boolean {
  return spec.availability.allNodes || spec.availability.steps.includes(node)
}

/** A one-sentence plain-English restatement of what the action will show. */
export function describeAction(spec: ActionSpec): string {
  const scope = joinPhrases(spec.from.selectors.map((s) => SELECTOR_PHRASES[s])) || 'this node'
  let what: string
  if (spec.show.kind === 'logEntries') {
    const n = spec.show.limit
    const order = spec.sort === 'ASC' ? 'oldest first' : 'most recent first'
    what = `the ${n === 1 ? 'last log entry' : `last ${n} log entries`} (${order})`
  } else {
    const metrics = spec.show.metrics.join(', ')
    const cap = spec.show.forLast ? `, over the last ${spec.show.forLast} log entries` : ''
    what = `a transition table with ${metrics}${cap}`
  }
  const where = spec.where
    ? ` restricted to Event ID ${spec.where.values.join(', ')}`
    : ''
  return `Show ${what} from ${scope}${where}. Results also honour the chart's current filters.`
}
