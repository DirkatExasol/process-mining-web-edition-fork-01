/** Helpers for the series-parallel Happy Path model: a node is a single STEP
 *  (`step` set, `branches` empty) or a SPLIT (`branches` non-empty — each inner
 *  list is one alternative sub-path, which may itself contain splits). Steps that
 *  follow a split in the same list are the shared "after-rejoin" continuation. */

import type { HappyPath, HappyPathNode, LegacyHappyPath } from '../types'

const newId = () => crypto.randomUUID().toUpperCase()

export function stepNode(step: string): HappyPathNode {
  return { id: newId(), step, label: '', branches: [] }
}

export function splitNode(branches: HappyPathNode[][] = [[], []]): HappyPathNode {
  return { id: newId(), step: '', label: '', rejoinLabel: '', branches }
}

export const isSplit = (n: HappyPathNode): boolean => n.branches.length > 0

/** Migrate a stored/backup blob to the node model. New payloads (with `nodes`)
 *  pass through; a legacy {steps, branches} blob folds the trunk into step nodes
 *  and any non-empty branches into one trailing split — enumerating to exactly the
 *  old trunk+branch routes, so conformance scores are unchanged. */
export function migrateHappyPath(raw: LegacyHappyPath): HappyPath {
  if (raw.nodes) return { id: raw.id, name: raw.name, nodes: raw.nodes }
  const nodes: HappyPathNode[] = (raw.steps ?? []).map(stepNode)
  const live = (raw.branches ?? []).filter((b) => b.steps && b.steps.length > 0)
  if (live.length > 0) {
    nodes.push(splitNode(live.map((b) => b.steps.map(stepNode))))
  }
  return { id: raw.id, name: raw.name, nodes }
}

/** Every step name used anywhere in the tree (so the editor can offer only unused
 *  steps — a step appears at most once across the whole path). */
export function usedSteps(nodes: HappyPathNode[], acc: Set<string> = new Set()): Set<string> {
  for (const n of nodes) {
    if (n.step) acc.add(n.step)
    for (const branch of n.branches) usedSteps(branch, acc)
  }
  return acc
}

/** Immutably apply `fn` to the node with `id`, searching recursively into split
 *  branches. Used to edit a (possibly nested) split by id, e.g. rename. */
export function updateNode(
  nodes: HappyPathNode[],
  id: string,
  fn: (n: HappyPathNode) => HappyPathNode,
): HappyPathNode[] {
  return nodes.map((n) => {
    if (n.id === id) return fn(n)
    if (n.branches.length > 0) {
      return { ...n, branches: n.branches.map((br) => updateNode(br, id, fn)) }
    }
    return n
  })
}
