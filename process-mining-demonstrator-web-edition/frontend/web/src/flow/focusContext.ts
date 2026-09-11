/** Hover-dwell focus for the process map.
 *
 *  When the pointer rests on a node for a few seconds (see FlowChart's dwell timer), that
 *  node and its incoming/outgoing transitions are spotlit and everything else is dimmed,
 *  so a single step's neighbourhood is legible even in a dense, crowded chart. The active
 *  focus is broadcast through this context rather than baked into the node/edge arrays, so
 *  toggling it re-renders only the leaf StepNode/MetricEdge components (which read the
 *  context) and never busts the node-position caches that keep dragging and panning smooth.
 *
 *  `null` = no focus (the common case), so nodes and edges render at full strength.
 */
import { createContext } from 'react'

export interface FlowFocus {
  /** The dwelled-on node's id. */
  node: string
  /** The focused node plus its direct neighbours — these stay bright; others dim. */
  nodes: Set<string>
  /** Ids (`from->to`) of the focused node's incoming + outgoing edges — these stay bright. */
  edges: Set<string>
}

export const FlowFocusContext = createContext<FlowFocus | null>(null)

/** The spotlight for one node: itself, its direct neighbours, and its incident edges
 *  (`from->to` ids). Self-loops resolve to the node alone. Pure, so it is unit-tested and
 *  reused by the dwell handler. `transitions` must be the *resolved/drawn* graph so the
 *  edge ids match the rendered edges (collapsed groups use their virtual ids). */
export function computeFocus(
  transitions: ReadonlyArray<{ fromStep: string; toStep: string }>,
  node: string,
): FlowFocus {
  const nodes = new Set<string>([node])
  const edges = new Set<string>()
  for (const t of transitions) {
    if (t.fromStep === node || t.toStep === node) {
      edges.add(`${t.fromStep}->${t.toStep}`)
      nodes.add(t.fromStep)
      nodes.add(t.toStep)
    }
  }
  return { node, nodes, edges }
}
