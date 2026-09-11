/** Shared leaf picker for the JSON / XML path pickers: a compact, filterable list of a
 *  sample record's pickable fields. Each row is one line — the path selector on the left,
 *  the value it resolves to on the right — and clicking it assigns that path to the active
 *  role. A field already mapped shows a small role badge, so the whole mapping is visible
 *  at a glance without scrolling between the list and the field rows. */

import { useMemo, useState } from 'react'
import type { Leaf } from '../integration/structuredPaths'

export interface Mapping {
  label: string
  color: string
}

export function LeafPicker({
  leaves,
  onPick,
  color,
  emptyHint,
  mappedBy,
}: {
  leaves: Leaf[]
  onPick: (path: string) => void
  color: string
  emptyHint: string
  /** For a leaf already mapped to a role, the badge to show (label + colour). */
  mappedBy?: (path: string) => Mapping | null
}) {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (!term) return leaves
    return leaves.filter(
      (l) => l.path.toLowerCase().includes(term) || l.value.toLowerCase().includes(term),
    )
  }, [leaves, q])

  if (leaves.length === 0) {
    return <span className="t-caption2 fg-tertiary">{emptyHint}</span>
  }

  return (
    <div className="col" style={{ gap: 4 }}>
      {leaves.length > 8 && (
        <input
          className="text-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter fields…"
          style={{ fontSize: 12, padding: '4px 8px' }}
        />
      )}
      <div
        style={{
          maxHeight: 216, overflowY: 'auto',
          border: '1px solid var(--border-soft)', borderRadius: 8,
        }}
      >
        {filtered.map((l, i) => {
          const m = mappedBy?.(l.path) ?? null
          return (
            <button
              key={l.path}
              className="row leaf-row"
              onClick={() => onPick(l.path)}
              title={`Assign ${l.path} to the active field`}
              style={{
                width: '100%', gap: 8, alignItems: 'center', textAlign: 'left',
                padding: '4px 8px', background: 'transparent', border: 'none', cursor: 'pointer',
                borderTop: i === 0 ? 'none' : '1px solid var(--border-soft)',
              }}
            >
              {m ? (
                <span
                  className="badge"
                  style={{ fontSize: 10, flex: 'none', color: m.color, borderColor: m.color }}
                >
                  {m.label}
                </span>
              ) : (
                <span className="status-dot" style={{ background: color, opacity: 0.3, flex: 'none' }} />
              )}
              <code style={{ fontSize: 12, whiteSpace: 'nowrap', flex: 'none' }}>{l.path}</code>
              <span
                className="fg-tertiary"
                style={{
                  flex: 1, minWidth: 0, fontSize: 11.5, textAlign: 'right',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}
              >
                {l.value || '—'}
              </span>
            </button>
          )
        })}
        {filtered.length === 0 && (
          <span className="t-caption2 fg-tertiary" style={{ display: 'block', padding: 6 }}>
            No field matches “{q}”.
          </span>
        )}
      </div>
    </div>
  )
}
