/** JSON path picker: renders a sample JSON record's scalar leaves as a clickable list;
 *  clicking one assigns its JSON path (e.g. `user.id`, `items[0].sku`) to the active
 *  role's field. Manual path entry stays available in the field rows themselves. */

import { useMemo } from 'react'
import { sampleLeaves } from '../integration/structuredPaths'
import { LeafPicker, type Mapping } from './LeafPicker'

export function JsonPathPicker({
  sample,
  onPick,
  color,
  mappedBy,
}: {
  /** One record's JSON text (the wizard's `sample`). */
  sample: string
  onPick: (path: string) => void
  color: string
  mappedBy?: (path: string) => Mapping | null
}) {
  const leaves = useMemo(() => sampleLeaves('json', sample), [sample])
  return (
    <LeafPicker
      leaves={leaves}
      onPick={onPick}
      color={color}
      mappedBy={mappedBy}
      emptyHint="Pick a JSON record on step 1 — its fields will appear here to click."
    />
  )
}
