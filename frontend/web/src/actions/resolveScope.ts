// Resolve an action's FROM selectors to a concrete set of step names, relative to
// the node the action is run from. Adjacency comes from the live graph's directed
// transitions (fromStep → toStep), so this runs on the client where the graph lives.

import type { ProcessTransition } from '../types'
import type { Selector } from './types'

function traverse(
  start: string,
  transitions: ProcessTransition[],
  dir: 'forward' | 'backward',
  out: Set<string>,
): void {
  const seen = new Set<string>()
  const queue: string[] = []
  for (const t of transitions) {
    if (dir === 'forward' && t.fromStep === start) queue.push(t.toStep)
    if (dir === 'backward' && t.toStep === start) queue.push(t.fromStep)
  }
  while (queue.length) {
    const n = queue.shift()!
    if (seen.has(n)) continue
    seen.add(n)
    out.add(n)
    for (const t of transitions) {
      if (dir === 'forward' && t.fromStep === n && !seen.has(t.toStep)) queue.push(t.toStep)
      if (dir === 'backward' && t.toStep === n && !seen.has(t.fromStep)) queue.push(t.fromStep)
    }
  }
}

/**
 * Resolve the selectors against `node`, returning the de-duplicated step names.
 * THIS = the node itself; PREVIOUS/FOLLOWING = direct neighbours; ALL PREVIOUS /
 * ALL FOLLOWING = every node transitively upstream / downstream.
 */
export function resolveScope(
  selectors: Selector[],
  node: string,
  transitions: ProcessTransition[],
): string[] {
  const out = new Set<string>()
  for (const sel of selectors) {
    switch (sel) {
      case 'THIS':
        out.add(node)
        break
      case 'PREVIOUS':
        for (const t of transitions) if (t.toStep === node) out.add(t.fromStep)
        break
      case 'FOLLOWING':
        for (const t of transitions) if (t.fromStep === node) out.add(t.toStep)
        break
      case 'ALL_FOLLOWING':
        traverse(node, transitions, 'forward', out)
        break
      case 'ALL_PREVIOUS':
        traverse(node, transitions, 'backward', out)
        break
    }
  }
  return [...out]
}
