/** XML path picker: a record-element input (the repeating element that is one record) plus
 *  a clickable list of the sample record's attributes and child texts; clicking one assigns
 *  its XPath-subset selector (e.g. `@id`, `payload/user@id`) to the active role's field. */

import { useMemo } from 'react'
import { sampleLeaves } from '../integration/structuredPaths'
import { LeafPicker, type Mapping } from './LeafPicker'

export function XmlPathPicker({
  sample,
  recordPath,
  onRecordPath,
  onPick,
  color,
  mappedBy,
}: {
  /** One record element's XML text (the wizard's `sample`). */
  sample: string
  recordPath: string
  onRecordPath: (value: string) => void
  onPick: (path: string) => void
  color: string
  mappedBy?: (path: string) => Mapping | null
}) {
  const leaves = useMemo(() => sampleLeaves('xml', sample), [sample])
  return (
    <div className="col" style={{ gap: 8 }}>
      <label className="row" style={{ gap: 8, alignItems: 'center' }}>
        <span className="t-caption fg-secondary" style={{ flex: 'none' }}>Record element</span>
        <input
          className="text-input"
          value={recordPath}
          onChange={(e) => onRecordPath(e.target.value)}
          placeholder="e.g. event"
          spellCheck={false}
          style={{ flex: 1, minWidth: 0, fontFamily: 'var(--mono, monospace)', fontSize: 12 }}
        />
      </label>
      <LeafPicker
        leaves={leaves}
        onPick={onPick}
        color={color}
        mappedBy={mappedBy}
        emptyHint="Pick an XML record on step 1 — its elements and attributes will appear here to click."
      />
    </div>
  )
}
