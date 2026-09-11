import { createContext } from 'react'

/** Drives the aggregate "pick steps" mode: which nodes are selected, so StepNode can
 *  ring them. Kept out of the node-building memo so a pick just re-renders the nodes. */
export interface AggregatePick {
  active: boolean
  /** Steps in the group currently being built (bright, pulsing ring). */
  picked: ReadonlySet<string>
  /** Steps already banked into an earlier group this session (calm, solid ring; locked). */
  banked: ReadonlySet<string>
}

export const AggregatePickContext = createContext<AggregatePick>({
  active: false,
  picked: new Set<string>(),
  banked: new Set<string>(),
})
