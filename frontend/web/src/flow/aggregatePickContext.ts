import { createContext } from 'react'

/** Drives the aggregate "pick steps" mode: which nodes are selected, so StepNode can
 *  ring them. Kept out of the node-building memo so a pick just re-renders the nodes. */
export interface AggregatePick {
  active: boolean
  picked: ReadonlySet<string>
}

export const AggregatePickContext = createContext<AggregatePick>({
  active: false,
  picked: new Set<string>(),
})
