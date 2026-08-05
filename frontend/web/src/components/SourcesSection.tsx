/** The "Sources" section of the integration console's left panel: the user's data
 *  sources as badges (kind icon · name · a config summary), a '+' in the header to add
 *  one via the wizard, and per-badge delete. At most ~3 badges show; the list scrolls. */

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { sourceKind } from '../integration/sourceKinds'
import type { Source } from '../types'
import { ConfirmDialog } from './ConfirmDialog'
import { RunSourceDialog } from './RunSourceDialog'
import { SectionHeader } from './SectionHeader'
import { SourceWizard } from './SourceWizard'

export function SourcesSection({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [sources, setSources] = useState<Source[]>([])
  const [wizard, setWizard] = useState<'new' | Source | null>(null)
  const [running, setRunning] = useState<Source | null>(null)
  const [confirming, setConfirming] = useState<Source | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setSources(await api.listSources())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = async (s: Source) => {
    setBusy(true)
    try {
      await api.deleteSource(s.id)
      setConfirming(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <SectionHeader
        title="Sources"
        count={sources.length}
        open={open}
        onToggle={onToggle}
        trailing={
          <button
            className="icon-btn"
            title="Add a source"
            aria-label="Add a source"
            onClick={() => setWizard('new')}
          >
            ＋
          </button>
        }
      />

      {open && error && (
        <div className="t-caption fg-red" style={{ padding: '0 4px' }}>
          {error}
        </div>
      )}

      {open &&
        (sources.length === 0 ? (
          <span className="t-caption fg-tertiary" style={{ padding: '0 4px' }}>
            No sources yet. Use ＋ to add one.
          </span>
        ) : (
          <div className="card-list" style={{ maxHeight: 190 }}>
            {sources.map((s) => {
            const kind = sourceKind(s.kind)
            return (
              <div
                key={s.id}
                className="card"
                style={{ minHeight: 52, cursor: 'pointer' }}
                title="Edit source"
                onClick={() => setWizard(s)}
              >
                <span aria-hidden style={{ fontSize: 16 }}>{kind?.icon ?? '🗂️'}</span>
                <div className="card-body">
                  <span className="card-title">
                    {s.name}
                    {(s.config?.watchdog as { enabled?: boolean } | undefined)?.enabled && (
                      <span title="Watchdog on — auto-imports new lines" style={{ marginLeft: 6 }}>👁</span>
                    )}
                  </span>
                  <span className="card-sub fg-tertiary">
                    {kind?.label ?? s.kind}
                    {kind ? ` · ${kind.summary(s.config)}` : ''}
                  </span>
                </div>
                {s.kind === 'file' && (
                  <button
                    className="icon-btn"
                    style={{ width: 22, height: 22, color: 'var(--accent)' }}
                    title="Run extraction"
                    aria-label="Run extraction"
                    onClick={(e) => {
                      e.stopPropagation()
                      setRunning(s)
                    }}
                  >
                    ▷
                  </button>
                )}
                <button
                  className="icon-btn"
                  style={{ width: 22, height: 22, color: 'var(--secondary)' }}
                  title="Delete source"
                  aria-label="Delete source"
                  onClick={(e) => {
                    e.stopPropagation()
                    setConfirming(s)
                  }}
                >
                  ✕
                </button>
              </div>
            )
          })}
          </div>
        ))}

      {wizard && (
        <SourceWizard
          existing={wizard === 'new' ? undefined : wizard}
          onClose={() => setWizard(null)}
          onSaved={async () => {
            setWizard(null)
            await refresh()
          }}
        />
      )}

      {running && (
        <RunSourceDialog source={running} onClose={() => setRunning(null)} onDone={() => {}} />
      )}

      {confirming && (
        <ConfirmDialog
          title="Delete source"
          message={`Delete the source “${confirming.name}”? This can’t be undone.`}
          confirmLabel="Delete source"
          busy={busy}
          onConfirm={() => void remove(confirming)}
          onCancel={() => setConfirming(null)}
        />
      )}
    </>
  )
}
