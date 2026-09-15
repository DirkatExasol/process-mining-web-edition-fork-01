/** The "Meta Infos" panel, opened from a flowchart node's context menu. Lists the
 *  project's distinct META values in three tabs (Meta_1/2/3), each searchable, and gives
 *  every value an Include / Exclude toggle — the list-based journey filter that mirrors the
 *  node Include/Exclude for steps. Project-wide (the same values the sidebar filters show),
 *  so it's the same panel from any node. */

import { useMemo, useState } from 'react'
import { useStore } from '../store'
import { Sheet } from './ui'

export function MetaInfoModal({ onClose }: { onClose: () => void }) {
  const meta1Title = useStore((s) => s.meta1Title)
  const meta2Title = useStore((s) => s.meta2Title)
  const meta3Title = useStore((s) => s.meta3Title)
  const meta1Values = useStore((s) => s.meta1Values)
  const meta2Values = useStore((s) => s.meta2Values)
  const meta3Values = useStore((s) => s.meta3Values)
  const metaFilters = useStore((s) => s.metaFilters)
  const handleMetaAction = useStore((s) => s.handleMetaAction)
  const clearMetaFilters = useStore((s) => s.clearMetaFilters)

  const cols = useMemo(
    () => [
      { title: meta1Title, values: meta1Values },
      { title: meta2Title, values: meta2Values },
      { title: meta3Title, values: meta3Values },
    ],
    [meta1Title, meta2Title, meta3Title, meta1Values, meta2Values, meta3Values],
  )
  const [tab, setTab] = useState(0)
  const [query, setQuery] = useState('')

  const active = cols[tab]
  const included = metaFilters.included[tab]
  const excluded = metaFilters.excluded[tab]
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const vals = active.values ?? []
    return q ? vals.filter((v) => v.toLowerCase().includes(q)) : vals
  }, [active.values, query])

  const activeCount = metaFilters.included.reduce((n, l) => n + l.length, 0) +
    metaFilters.excluded.reduce((n, l) => n + l.length, 0)

  return (
    <Sheet
      title="Meta Infos"
      icon="▤"
      onClose={onClose}
      footer={
        <>
          {activeCount > 0 && (
            <button className="btn small" onClick={() => clearMetaFilters()}>
              Clear meta filters ({activeCount})
            </button>
          )}
          <span className="spacer" />
          <button className="btn prominent" onClick={onClose}>Done</button>
        </>
      }
    >
      <div className="col" style={{ gap: 10, minWidth: 340 }}>
        {/* Tabs: one per META column. */}
        <div className="row" style={{ gap: 6 }}>
          {cols.map((c, i) => {
            const inc = metaFilters.included[i].length
            const exc = metaFilters.excluded[i].length
            return (
              <button
                key={i}
                className={`btn small${i === tab ? ' prominent' : ''}`}
                onClick={() => { setTab(i); setQuery('') }}
                style={{ flex: 1 }}
                title={c.title || `Meta ${i + 1}`}
              >
                <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {c.title || `Meta ${i + 1}`}
                  {inc + exc > 0 && <span className="fg-tertiary"> · {inc + exc}</span>}
                </span>
              </button>
            )
          })}
        </div>

        <input
          className="text-input"
          placeholder={`Search ${active.title || `Meta ${tab + 1}`} values…`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          spellCheck={false}
          autoFocus
        />

        <div className="col" style={{ gap: 4, maxHeight: 360, overflowY: 'auto', paddingRight: 2 }}>
          {(active.values ?? []).length === 0 ? (
            <span className="t-caption2 fg-tertiary" style={{ padding: '8px 2px' }}>
              No values in this column for the current project.
            </span>
          ) : filtered.length === 0 ? (
            <span className="t-caption2 fg-tertiary" style={{ padding: '8px 2px' }}>
              No values match “{query}”.
            </span>
          ) : (
            filtered.map((v) => {
              const isInc = included.includes(v)
              const isExc = excluded.includes(v)
              return (
                <div
                  key={v}
                  className="row"
                  style={{
                    gap: 8, alignItems: 'center', padding: '5px 8px', borderRadius: 6,
                    background: isInc ? 'color-mix(in srgb, transparent, var(--green) 14%)'
                      : isExc ? 'color-mix(in srgb, transparent, var(--red) 14%)' : 'var(--bg-fill)',
                  }}
                >
                  <span
                    title={v}
                    style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 13 }}
                  >
                    {v}
                  </span>
                  <button
                    className="icon-btn"
                    title={isInc ? 'Included — click to clear' : 'Include journeys with this value'}
                    aria-label={`Include ${v}`}
                    aria-pressed={isInc}
                    onClick={() => handleMetaAction(tab, v, 'include')}
                    style={{ color: isInc ? 'var(--green)' : 'var(--secondary)', fontWeight: 700 }}
                  >
                    ⊕
                  </button>
                  <button
                    className="icon-btn"
                    title={isExc ? 'Excluded — click to clear' : 'Exclude journeys with this value'}
                    aria-label={`Exclude ${v}`}
                    aria-pressed={isExc}
                    onClick={() => handleMetaAction(tab, v, 'exclude')}
                    style={{ color: isExc ? 'var(--red)' : 'var(--secondary)', fontWeight: 700 }}
                  >
                    ⊖
                  </button>
                </div>
              )
            })
          )}
        </div>

        <span className="t-caption2 fg-tertiary">
          ⊕ keeps only journeys that have an event with the value; ⊖ drops journeys that
          have it. Same as a step Include/Exclude, per Meta column.
        </span>
      </div>
    </Sheet>
  )
}
