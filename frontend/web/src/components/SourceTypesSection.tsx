/** The "Source types" section of the integration console's left panel: the user's
 *  source-type definitions as badges (name · field count), a '+' in the header to add
 *  a new one, and per-badge delete. At most ~3 badges are visible; the list scrolls
 *  beyond that. A source type is a name plus an extraction spec built in the wizard. */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { SourceType } from '../types'
import { SourceTypeWizard } from './SourceTypeWizard'

export function SourceTypesSection() {
  const [sourceTypes, setSourceTypes] = useState<SourceType[]>([])
  // null = closed; 'new' = the add wizard; a SourceType = editing it.
  const [wizard, setWizard] = useState<'new' | SourceType | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setSourceTypes(await api.listSourceTypes())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = async (s: SourceType) => {
    if (!window.confirm(`Delete source type "${s.name}"?`)) return
    try {
      await api.deleteSourceType(s.id)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <>
      <div className="section-header">
        <span className="section-title" style={{ padding: '0 4px' }}>
          Source types
        </span>
        {sourceTypes.length > 0 && <span className="section-count">({sourceTypes.length})</span>}
        <span className="spacer" />
        <button
          className="icon-btn"
          title="Add a source type"
          aria-label="Add a source type"
          onClick={() => setWizard('new')}
        >
          ＋
        </button>
      </div>

      {error && (
        <div className="t-caption fg-red" style={{ padding: '0 4px' }}>
          {error}
        </div>
      )}

      {sourceTypes.length === 0 ? (
        <span className="t-caption fg-tertiary" style={{ padding: '0 4px' }}>
          No source types yet. Use ＋ to define one.
        </span>
      ) : (
        // At most ~3 badges (each min 52px + gap); scroll past that.
        <div className="card-list" style={{ maxHeight: 190 }}>
          {sourceTypes.map((s) => (
            <div
              key={s.id}
              className="card"
              style={{ minHeight: 52, cursor: 'pointer' }}
              title="Edit source type"
              onClick={() => setWizard(s)}
            >
              <span aria-hidden style={{ fontSize: 16, color: 'var(--accent)' }}>
                🧩
              </span>
              <div className="card-body">
                <span className="card-title">{s.name}</span>
                <span className="card-sub fg-tertiary">
                  {s.fields.length > 0
                    ? `${s.fields.length} field${s.fields.length === 1 ? '' : 's'}`
                    : 'no fields yet'}
                </span>
              </div>
              <button
                className="icon-btn"
                style={{ width: 22, height: 22, color: 'var(--secondary)' }}
                title="Delete source type"
                aria-label="Delete source type"
                onClick={(e) => {
                  e.stopPropagation()
                  void remove(s)
                }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {wizard && (
        <SourceTypeWizard
          existing={wizard === 'new' ? undefined : wizard}
          onClose={() => setWizard(null)}
          onSaved={async () => {
            setWizard(null)
            await refresh()
          }}
        />
      )}
    </>
  )
}
