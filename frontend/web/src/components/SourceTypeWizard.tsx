/** Source-type wizard. Walks through basics (name + a pasted example log line) →
 *  mapping the extraction fields → review & save. The mapping step has one tab per role
 *  (Timestamp · Step · Id · Metas): the active tab colours its highlights and any segment
 *  you select is mapped to that role. The spec (sample + regexes) is stored with the
 *  source type for future automatic extraction. Edits an existing one when `existing` is
 *  set. Styling follows the app's Sheet / text-input / sheet-tabs conventions. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import {
  buildHighlights,
  matchAll,
  ROLE_COLOR,
  ROLE_LABEL,
  selectionOffsetsWithin,
  testPattern,
  type ExtractionField,
  type FieldRole,
  type HighlightSpan,
} from '../integration/regexHighlight'
import type { SourceType } from '../types'
import { Sheet } from './ui'

// Tab order requested: Timestamp, Step, Id, Metas.
const ROLE_TABS: FieldRole[] = ['timestamp', 'step', 'id', 'meta']
const LAST_STEP = 3

let fieldSeq = 0
const newFieldId = () => `f${++fieldSeq}`

export function SourceTypeWizard({
  existing,
  onClose,
  onSaved,
}: {
  existing?: SourceType
  onClose: () => void
  onSaved: () => void | Promise<void>
}) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState(existing?.name ?? '')
  const [sample, setSample] = useState(existing?.sample ?? '')
  const [fields, setFields] = useState<ExtractionField[]>(
    (existing?.fields ?? []).map((f) => ({ ...f, id: f.id ?? newFieldId() })),
  )
  const [activeRole, setActiveRole] = useState<FieldRole>('timestamp')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const previewRef = useRef<HTMLDivElement>(null)

  const setField = (id: string, patch: Partial<ExtractionField>) =>
    setFields((fs) => fs.map((f) => (f.id === id ? { ...f, ...patch } : f)))
  const removeField = (id: string) => setFields((fs) => fs.filter((f) => f.id !== id))

  const useSelection = async () => {
    const el = previewRef.current
    const span = el ? selectionOffsetsWithin(el) : null
    if (!span) {
      setError('Select a piece of the sample above first.')
      return
    }
    setError(null)
    try {
      const { regex } = await api.parseSegment(sample, span[0], span[1])
      setFields((fs) => [
        ...fs,
        { id: newFieldId(), name: defaultName(activeRole, fs), role: activeRole, regex },
      ])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const addBlankField = () =>
    setFields((fs) => [
      ...fs,
      { id: newFieldId(), name: defaultName(activeRole, fs), role: activeRole, regex: '' },
    ])

  const save = async () => {
    if (!name.trim()) {
      setError('A name is required.')
      setStep(1)
      return
    }
    setBusy(true)
    setError(null)
    const body = {
      name: name.trim(),
      sample,
      fields: fields.map(({ name, role, regex, format, title }) => ({
        name: name.trim() || role,
        role,
        regex,
        format,
        title,
      })),
    }
    try {
      if (existing) await api.updateSourceType(existing.id, body)
      else await api.createSourceType(body)
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  const highlights = useMemo(() => buildHighlights(sample, fields), [sample, fields])
  const roleFields = fields.filter((f) => f.role === activeRole)
  const countByRole = (r: FieldRole) => fields.filter((f) => f.role === r).length

  // Normalised EVENT_TIME for the example JOURNEYS record (backend-parsed).
  const tsField = fields.find((f) => f.role === 'timestamp')
  const tsValue = tsField ? matchAll(sample, tsField.regex)?.[0]?.value ?? '' : ''
  const [normalizedTs, setNormalizedTs] = useState('')
  useEffect(() => {
    if (!tsValue) {
      setNormalizedTs('')
      return
    }
    let alive = true
    void api.parseTimestamp(tsValue).then((i) => alive && setNormalizedTs(i.normalized)).catch(() => {})
    return () => {
      alive = false
    }
  }, [tsValue])

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
          disabled={busy || (step === 1 && !name.trim())}
          onClick={() => setStep((s) => s + 1)}
        >
          Next
        </button>
      )}
      {step === LAST_STEP && (
        <button className="btn prominent" onClick={() => void save()} disabled={busy}>
          {busy ? 'Saving…' : existing ? 'Save changes' : 'Create source type'}
        </button>
      )}
    </>
  )

  return (
    <Sheet
      title={existing ? 'Edit source type' : 'New source type'}
      icon="🧩"
      onClose={onClose}
      footer={footer}
    >
      <div className="iwiz-col mapping">
      {step === 1 && (
        <>
          <Field label="Name">
            <input
              className="text-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Apache access log, App JSON log"
              autoFocus
            />
          </Field>
          <Field label="Paste an example log entry">
            <textarea
              className="text-input"
              value={sample}
              onChange={(e) => setSample(e.target.value)}
              rows={7}
              placeholder="2026-08-03T14:05:09Z INFO OrderReceived case_id=abc-123 …"
              style={{ fontFamily: 'var(--mono, monospace)', fontSize: 12 }}
            />
          </Field>
          <span className="t-caption2 fg-tertiary">
            On the next step you'll map each field yourself — highlight a segment and assign
            it, or type its regex. Every field is defined manually.
          </span>
        </>
      )}

      {step === 2 && (
        <>
          <Field label="Select a segment below, pick a tab, then map it">
            <div
              ref={previewRef}
              className="text-input"
              style={{
                fontFamily: 'var(--mono, monospace)', fontSize: 12, whiteSpace: 'pre-wrap',
                wordBreak: 'break-word', maxHeight: 150, overflow: 'auto', cursor: 'text', userSelect: 'text',
              }}
            >
              <Highlighted highlights={highlights} />
            </div>
          </Field>

          <div className="sheet-tabs">
            {ROLE_TABS.map((r) => {
              const sel = activeRole === r
              return (
                <button
                  key={r}
                  className={sel ? 'sel' : ''}
                  style={sel ? { color: ROLE_COLOR[r], borderBottomColor: ROLE_COLOR[r] } : undefined}
                  onClick={() => setActiveRole(r)}
                >
                  <span className="status-dot" style={{ background: ROLE_COLOR[r], marginRight: 6, verticalAlign: 'middle' }} />
                  {r === 'meta' ? 'Metas' : ROLE_LABEL[r]}
                  {countByRole(r) > 0 && ` (${countByRole(r)})`}
                </button>
              )
            })}
          </div>

          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <button className="btn" style={{ color: ROLE_COLOR[activeRole] }} onClick={() => void useSelection()}>
              🎯 Use selection
            </button>
            <button className="btn" onClick={addBlankField}>＋ Add field</button>
          </div>

          {roleFields.length === 0 ? (
            <span className="t-caption fg-tertiary">
              No {activeRole === 'meta' ? 'meta fields' : ROLE_LABEL[activeRole].toLowerCase()} yet — select a segment
              above and map it, or add a field.
            </span>
          ) : (
            <div className="col" style={{ gap: 8 }}>
              {roleFields.map((f) => (
                <FieldRow
                  key={f.id}
                  field={f}
                  sample={sample}
                  onChange={(patch) => setField(f.id!, patch)}
                  onRemove={() => removeField(f.id!)}
                />
              ))}
            </div>
          )}

          {fields.length > 0 && (
            <JourneysRecordPreview fields={fields} sample={sample} normalizedTs={normalizedTs} />
          )}
        </>
      )}

      {step === 3 && (
        <>
          <Field label="Preview">
            <div
              className="text-input"
              style={{
                fontFamily: 'var(--mono, monospace)', fontSize: 12, whiteSpace: 'pre-wrap',
                wordBreak: 'break-word', maxHeight: 130, overflow: 'auto',
              }}
            >
              <Highlighted highlights={highlights} />
            </div>
          </Field>
          <div className="t-caption fg-secondary">{name || '(unnamed)'}</div>
          <div className="col" style={{ gap: 6 }}>
            {fields.length === 0 && <span className="t-caption fg-tertiary">No extraction fields defined.</span>}
            {fields.map((f) => (
              <div key={f.id} className="row" style={{ gap: 8, alignItems: 'baseline' }}>
                <span className="status-dot" style={{ background: ROLE_COLOR[f.role] }} />
                <span className="t-caption2 fg-tertiary" style={{ minWidth: 78 }}>
                  {f.role === 'meta' ? 'Meta' : ROLE_LABEL[f.role]}
                </span>
                <strong>{f.name}</strong>
                <code className="t-caption2 fg-tertiary" style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {f.regex}
                </code>
                {f.role === 'timestamp' && f.format && (
                  <span className="t-caption2 fg-tertiary">→ {f.format}</span>
                )}
              </div>
            ))}
          </div>
          {fields.length > 0 && (
            <JourneysRecordPreview fields={fields} sample={sample} normalizedTs={normalizedTs} />
          )}
        </>
      )}

      {error && <div className="t-caption fg-red">{error}</div>}
      </div>
    </Sheet>
  )
}

function FieldRow({
  field,
  sample,
  onChange,
  onRemove,
}: {
  field: ExtractionField
  sample: string
  onChange: (patch: Partial<ExtractionField>) => void
  onRemove: () => void
}) {
  const result = testPattern(sample, field.regex)
  const color = result.ok ? 'var(--green)' : result.error ? 'var(--red)' : 'var(--secondary)'

  // For a timestamp field, analyse the captured value → normalised
  // "YYYY-MM-DD HH:MM:SS" + a parse format, which is stored with the field.
  const [ts, setTs] = useState<{ format: string; normalized: string } | null>(null)
  const matchValue = field.role === 'timestamp' && result.ok ? result.value : undefined
  useEffect(() => {
    if (!matchValue) {
      setTs(null)
      return
    }
    let alive = true
    void api
      .parseTimestamp(matchValue)
      .then((info) => {
        if (!alive) return
        setTs(info)
        if (info.format !== (field.format ?? '')) onChange({ format: info.format })
      })
      .catch(() => alive && setTs(null))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchValue])

  return (
    <div className="col" style={{ gap: 6, padding: 10, borderRadius: 10, background: 'var(--fill)' }}>
      {/* field name (or role label) + regex on one line */}
      <div className="row" style={{ gap: 6, alignItems: 'center' }}>
        {field.role === 'meta' ? (
          <input
            className="text-input"
            value={field.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="field name"
            style={{ width: 130, flex: 'none' }}
          />
        ) : (
          <span
            className="t-caption"
            style={{ fontWeight: 600, color: ROLE_COLOR[field.role], width: 96, flex: 'none' }}
          >
            {ROLE_LABEL[field.role]}
          </span>
        )}
        <input
          className="text-input"
          value={field.regex}
          onChange={(e) => onChange({ regex: e.target.value })}
          placeholder="regex (one capture group = the value)"
          spellCheck={false}
          style={{ flex: 1, minWidth: 0, fontFamily: 'var(--mono, monospace)', fontSize: 12 }}
        />
        <button className="icon-btn" title="Remove field" aria-label="Remove field" onClick={onRemove}>
          ✕
        </button>
      </div>
      {field.role === 'meta' && (
        <input
          className="text-input"
          value={field.title ?? ''}
          onChange={(e) => onChange({ title: e.target.value })}
          placeholder="Business name (e.g. Book ID) — shown in the app"
        />
      )}
      <span className="t-caption2" style={{ color }}>
        {field.regex
          ? result.ok
            ? `✓ matches: ${result.value}`
            : result.error
              ? '⚠ invalid regex'
              : '• no match in the sample'
          : '• enter a regex'}
      </span>
      {field.role === 'timestamp' && result.ok && ts && (
        <span className="t-caption2" style={{ color: ts.normalized ? 'var(--green)' : 'var(--orange)' }}>
          {ts.normalized
            ? `🕒 ${ts.normalized}  ·  format ${ts.format}`
            : '⚠ couldn’t recognise the date — stored as extracted'}
        </span>
      )}
    </div>
  )
}

/** A live preview of the JOURNEYS row the current spec would produce from the sample:
 *  id → EVENT_ID, step → STEP, timestamp → EVENT_TIME (normalised), the first three
 *  meta fields → META_1..3. PROJECT_ID / STEP_ID / SAMPLE_SET are filled at load time. */
function JourneysRecordPreview({
  fields,
  sample,
  normalizedTs,
}: {
  fields: ExtractionField[]
  sample: string
  normalizedTs: string
}) {
  const firstValue = (role: FieldRole): string => {
    const f = fields.find((x) => x.role === role)
    if (!f) return ''
    return matchAll(sample, f.regex)?.[0]?.value ?? ''
  }
  const metas = fields.filter((f) => f.role === 'meta')
  const metaCell = (i: number) => {
    const f = metas[i]
    if (!f) return null
    return { name: f.title || f.name, value: matchAll(sample, f.regex)?.[0]?.value ?? '' }
  }

  const rows: { col: string; note?: string; value: string; muted?: boolean }[] = [
    { col: 'PROJECT_ID', value: '(set when the source runs)', muted: true },
    // The original id is shown here; it's stored MD5-hashed in JOURNEYS.
    { col: 'EVENT_ID', note: 'original — stored as MD5', value: firstValue('id') },
    { col: 'STEP', value: firstValue('step') },
    { col: 'STEP_ID', value: '', muted: true },
    { col: 'EVENT_TIME', value: normalizedTs || firstValue('timestamp') },
    ...[0, 1, 2].map((i) => {
      const c = metaCell(i)
      return { col: `META_${i + 1}`, note: c?.name, value: c?.value ?? '' }
    }),
    { col: 'SAMPLE_SET', value: 'ORIGINAL', muted: true },
  ]

  return (
    <div className="col" style={{ gap: 4 }}>
      <span className="t-caption fg-secondary">Example JOURNEYS record</span>
      <div
        style={{
          overflowX: 'auto', border: '1px solid var(--border-soft)', borderRadius: 10,
        }}
      >
        <table
          style={{
            borderCollapse: 'collapse', fontFamily: 'var(--mono, monospace)', fontSize: 12,
            whiteSpace: 'nowrap', width: '100%',
          }}
        >
          <thead>
            <tr>
              {rows.map((r) => (
                <th
                  key={r.col}
                  style={{
                    textAlign: 'left', padding: '6px 10px', color: 'var(--secondary)',
                    fontWeight: 600, background: 'var(--fill)',
                    borderBottom: '1px solid var(--border-soft)',
                  }}
                >
                  {r.col}
                  {r.note ? <div className="t-caption2 fg-tertiary" style={{ fontWeight: 400 }}>{r.note}</div> : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {rows.map((r) => (
                <td
                  key={r.col}
                  style={{ padding: '6px 10px', color: r.muted ? 'var(--tertiary)' : 'inherit' }}
                >
                  {r.value !== '' ? r.value : <span className="fg-tertiary">—</span>}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Highlighted({ highlights }: { highlights: HighlightSpan[] }) {
  if (highlights.length === 0)
    return <span className="fg-tertiary">Paste a sample on the previous step.</span>
  return (
    <>
      {highlights.map((h, i) =>
        h.role ? (
          <mark
            key={i}
            style={{ background: `color-mix(in srgb, transparent, ${ROLE_COLOR[h.role]} 32%)`, color: 'inherit', borderRadius: 3 }}
          >
            {h.text}
          </mark>
        ) : (
          <span key={i}>{h.text}</span>
        ),
      )}
    </>
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

function defaultName(role: FieldRole, existing: ExtractionField[]): string {
  if (role !== 'meta') return role
  const n = existing.filter((f) => f.role === 'meta').length + 1
  return `meta_${n}`
}
