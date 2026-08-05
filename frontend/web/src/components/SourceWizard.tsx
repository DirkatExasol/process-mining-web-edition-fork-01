/** "Add / edit source" wizard. Generic over source *kinds* (see `sourceKinds.ts`):
 *  step 1 picks a kind, step 2 fills that kind's config fields, step 3 reviews & saves.
 *  Only "File" is selectable for now; other kinds appear disabled to show the structure. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { SOURCE_KINDS, sourceKind, type SourceKindDef } from '../integration/sourceKinds'
import type { Source, SourceType } from '../types'
import { Sheet } from './ui'

const LAST_STEP = 3

export function SourceWizard({
  existing,
  onClose,
  onSaved,
}: {
  existing?: Source
  onClose: () => void
  onSaved: () => void | Promise<void>
}) {
  const [step, setStep] = useState(existing ? 2 : 1)
  const [kindId, setKindId] = useState(existing?.kind ?? 'file')
  const [name, setName] = useState(existing?.name ?? '')
  const [config, setConfig] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    const kind = sourceKind(existing?.kind ?? 'file')
    for (const f of kind?.fields ?? []) init[f.key] = String(existing?.config?.[f.key] ?? f.default ?? '')
    return init
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sourceTypes, setSourceTypes] = useState<SourceType[]>([])
  const [previewLines, setPreviewLines] = useState(5)
  const [preview, setPreview] = useState<{ lines: string[]; truncated: boolean } | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const kind = sourceKind(kindId)

  // The picker of source types (for a 'sourceType' field).
  useEffect(() => {
    void api.listSourceTypes().then(setSourceTypes).catch(() => setSourceTypes([]))
  }, [])

  // Live preview of the first N lines of a file source, refreshed as path/lines change.
  const filePath = kindId === 'file' ? (config.path ?? '').trim() : ''
  useEffect(() => {
    if (!filePath) {
      setPreview(null)
      setPreviewError(null)
      return
    }
    let alive = true
    const t = window.setTimeout(() => {
      void api
        .previewSource(filePath, previewLines)
        .then((p) => {
          if (!alive) return
          setPreview(p)
          setPreviewError(null)
        })
        .catch((e) => {
          if (!alive) return
          setPreview(null)
          setPreviewError(e instanceof Error ? e.message : String(e))
        })
    }, 350)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [filePath, previewLines])

  const pickKind = (k: SourceKindDef) => {
    if (!k.available) return
    setKindId(k.id)
    // Seed defaults for the newly chosen kind's fields.
    setConfig((prev) => {
      const next: Record<string, string> = {}
      for (const f of k.fields) next[f.key] = prev[f.key] ?? f.default ?? ''
      return next
    })
  }

  const setField = (key: string, value: string) => setConfig((c) => ({ ...c, [key]: value }))

  const missingRequired = (kind?.fields ?? []).find((f) => f.required && !config[f.key]?.trim())

  const save = async () => {
    if (!name.trim()) {
      setError('A name is required.')
      return
    }
    if (missingRequired) {
      setError(`${missingRequired.label} is required.`)
      setStep(2)
      return
    }
    setBusy(true)
    setError(null)
    // Only keep the current kind's declared fields (trimmed, non-empty).
    const cleaned: Record<string, string> = {}
    for (const f of kind?.fields ?? []) {
      const v = config[f.key]?.trim()
      if (v) cleaned[f.key] = v
    }
    const body = { name: name.trim(), kind: kindId, config: cleaned }
    try {
      if (existing) await api.updateSource(existing.id, body)
      else await api.createSource(body)
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  const footer = (
    <>
      <span className="t-caption2 fg-tertiary">Step {step} of {LAST_STEP}</span>
      <span className="spacer" />
      <button className="btn" onClick={onClose} disabled={busy}>
        Cancel
      </button>
      {step > 1 && (
        <button className="btn" onClick={() => setStep((s) => s - 1)} disabled={busy}>
          Back
        </button>
      )}
      {step < LAST_STEP && (
        <button
          className="btn prominent"
          disabled={busy || (step === 2 && !name.trim())}
          onClick={() => setStep((s) => s + 1)}
        >
          Next
        </button>
      )}
      {step === LAST_STEP && (
        <button className="btn prominent" onClick={() => void save()} disabled={busy}>
          {busy ? 'Saving…' : existing ? 'Save changes' : 'Create source'}
        </button>
      )}
    </>
  )

  return (
    <Sheet
      title={existing ? 'Edit source' : 'New source'}
      icon={kind?.icon ?? '🗂️'}
      onClose={onClose}
      footer={footer}
    >
      <div className="iwiz-col narrow">
      {step === 1 && (
        <>
          <span className="t-caption fg-secondary">Choose a source kind</span>
          <div className="col" style={{ gap: 8 }}>
            {SOURCE_KINDS.map((k) => (
              <div
                key={k.id}
                className={`card${kindId === k.id ? ' selected' : ''}`}
                style={{ minHeight: 56, cursor: k.available ? 'pointer' : 'not-allowed', opacity: k.available ? 1 : 0.55 }}
                onClick={() => pickKind(k)}
              >
                <span aria-hidden style={{ fontSize: 20 }}>{k.icon}</span>
                <div className="card-body">
                  <span className="card-title">
                    {k.label}
                    {!k.available && <span className="fg-tertiary"> · coming soon</span>}
                  </span>
                  <span className="card-sub fg-tertiary">{k.description}</span>
                </div>
                {kindId === k.id && k.available && (
                  <span className="status-dot" style={{ background: 'var(--green)' }} />
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {step === 2 && kind && (
        <>
          <Field label="Name">
            <input
              className="text-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={`e.g. ${kind.label} — access log`}
              autoFocus
            />
          </Field>
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <span aria-hidden>{kind.icon}</span>
            <span className="t-caption fg-secondary">{kind.label}</span>
            {SOURCE_KINDS.filter((k) => k.available).length > 1 && (
              <button className="btn small" onClick={() => setStep(1)}>Change kind</button>
            )}
          </div>
          <div className="row" style={{ flexWrap: 'wrap', gap: 12, alignItems: 'flex-start' }}>
          {kind.fields.map((f) => (
            <div
              key={f.key}
              style={{
                minWidth: 0,
                flex:
                  f.layout === 'narrow' ? '0 0 150px' : f.layout === 'grow' ? '1 1 220px' : '1 1 100%',
              }}
            >
            <Field label={f.required ? `${f.label} *` : f.label}>
              {f.type === 'select' ? (
                <select
                  className="text-input"
                  value={config[f.key] ?? f.default ?? ''}
                  onChange={(e) => setField(f.key, e.target.value)}
                >
                  {(f.options ?? []).map((o) => (
                    <option key={o} value={o}>{o}</option>
                  ))}
                </select>
              ) : f.type === 'sourceType' ? (
                <select
                  className="text-input"
                  value={config[f.key] ?? ''}
                  onChange={(e) => setField(f.key, e.target.value)}
                >
                  <option value="">— none —</option>
                  {sourceTypes.map((st) => (
                    <option key={st.id} value={st.id}>{st.name}</option>
                  ))}
                </select>
              ) : (
                <input
                  className="text-input"
                  type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'}
                  value={config[f.key] ?? ''}
                  onChange={(e) => setField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                />
              )}
              {f.help && <span className="t-caption2 fg-tertiary">{f.help}</span>}
              {f.type === 'sourceType' && sourceTypes.length === 0 && (
                <span className="t-caption2 fg-tertiary">
                  No source types yet — define one in the Source types section first.
                </span>
              )}
            </Field>
            </div>
          ))}
          </div>

          {kindId === 'file' && (
            <div className="col" style={{ gap: 4 }}>
              <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                <span className="t-caption fg-secondary">Preview</span>
                <span className="t-caption2 fg-tertiary">first</span>
                <input
                  className="text-input"
                  type="number"
                  min={1}
                  max={50}
                  value={previewLines}
                  onChange={(e) => setPreviewLines(Math.max(1, Math.min(50, Number(e.target.value) || 5)))}
                  style={{ width: 64 }}
                />
                <span className="t-caption2 fg-tertiary">lines</span>
              </div>
              {previewError ? (
                <div className="t-caption fg-red">{previewError}</div>
              ) : (
                <div
                  className="text-input"
                  style={{
                    fontFamily: 'var(--mono, monospace)', fontSize: 12, whiteSpace: 'pre',
                    overflow: 'auto', maxHeight: 160,
                  }}
                >
                  {!filePath ? (
                    <span className="fg-tertiary">Enter a file path to preview it.</span>
                  ) : preview && preview.lines.length ? (
                    preview.lines.join('\n') + (preview.truncated ? '\n…' : '')
                  ) : (
                    <span className="fg-tertiary">No lines.</span>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {step === 3 && kind && (
        <div className="col" style={{ gap: 8 }}>
          <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
            <span aria-hidden>{kind.icon}</span>
            <strong>{name || '(unnamed)'}</strong>
            <span className="t-caption2 fg-tertiary">{kind.label}</span>
          </div>
          {kind.fields.map((f) => (
            <div key={f.key} className="row" style={{ gap: 10, alignItems: 'baseline' }}>
              <span className="t-caption fg-tertiary" style={{ minWidth: 130 }}>{f.label}</span>
              <span className="t-body" style={{ fontFamily: f.type === 'password' ? undefined : 'var(--mono, monospace)', wordBreak: 'break-all' }}>
                {config[f.key]?.trim()
                  ? f.type === 'password'
                    ? '••••••'
                    : f.type === 'sourceType'
                      ? sourceTypes.find((st) => st.id === config[f.key])?.name ?? '(unknown)'
                      : config[f.key]
                  : <span className="fg-tertiary">—</span>}
              </span>
            </div>
          ))}
        </div>
      )}

      {error && <div className="t-caption fg-red">{error}</div>}
      </div>
    </Sheet>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="col" style={{ gap: 4 }}>
      <span className="t-caption fg-secondary">{label}</span>
      {children}
    </label>
  )
}
