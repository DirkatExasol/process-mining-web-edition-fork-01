// Validates that a selected set of steps is truly "interconnected" — one weakly
// connected component over the directly-follows edges among them, with no step left
// isolated. Used before creating an aggregate.

import type { ProcessTransition } from '../types'

export interface SelectionValidation {
  /** Selected steps with no directly-follows edge to any other selected step. */
  isolated: string[]
  /** Number of weakly-connected components among the selected steps. */
  components: number
  /** True when ≥2 steps are selected and they form a single interconnected group. */
  ok: boolean
}

export function validateAggregateSelection(
  selected: string[],
  transitions: ProcessTransition[],
): SelectionValidation {
  const set = new Set(selected)
  const adj = new Map<string, Set<string>>()
  for (const s of set) adj.set(s, new Set())
  for (const t of transitions) {
    if (t.fromStep === t.toStep) continue // ignore self-loops
    if (set.has(t.fromStep) && set.has(t.toStep)) {
      adj.get(t.fromStep)!.add(t.toStep)
      adj.get(t.toStep)!.add(t.fromStep) // undirected view
    }
  }

  const isolated = [...set].filter((s) => (adj.get(s)?.size ?? 0) === 0)

  // Count weakly-connected components via BFS over the undirected adjacency.
  const seen = new Set<string>()
  let components = 0
  for (const start of set) {
    if (seen.has(start)) continue
    components++
    const queue = [start]
    seen.add(start)
    while (queue.length) {
      const n = queue.shift()!
      for (const m of adj.get(n) ?? []) {
        if (!seen.has(m)) {
          seen.add(m)
          queue.push(m)
        }
      }
    }
  }

  const ok = selected.length >= 2 && isolated.length === 0 && components === 1
  return { isolated, components, ok }
}
