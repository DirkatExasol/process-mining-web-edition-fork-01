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
  deriveCompoundStep,
  matchAll,
  ROLE_COLOR,
  ROLE_LABEL,
  selectionOffsetsWithin,
  testPattern,
  type ExtractionField,
  type FieldRole,
  type HighlightSpan,
} from '../integration/regexHighlight'
import {
  COMPOUND_OPS,
  COMPOUND_OP_LABEL,
  type CompoundCondition,
  type CompoundOp,
  type CompoundRule,
  type DataFormat,
  type SourceType,
} from '../types'
import { resolveFieldValue } from '../integration/structuredPaths'
import { Sheet } from './ui'
import { SourceTypeFilePicker } from './SourceTypeFilePicker'
import { JsonPathPicker } from './JsonPathPicker'
import { XmlPathPicker } from './XmlPathPicker'

const FORMAT_LABEL: Record<DataFormat, string> = {
  text: 'Text (regex)',
  json: 'JSON (paths)',
  xml: 'XML (paths)',
}

/** The value a field extracts from the sample — a regex match (text) or a path selector
 *  result (json/xml). The single place the two mapping styles converge. */
function valueOf(format: DataFormat, sample: string, field: ExtractionField): string {
  if (format === 'text') return matchAll(sample, field.regex)?.[0]?.value ?? ''
  return resolveFieldValue(format, sample, field.path ?? '') ?? ''
}

// Tab order requested: Timestamp, Step, Id, Metas.
const ROLE_TABS: FieldRole[] = ['timestamp', 'step', 'id', 'meta', 'aux']
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
  // Data format: text (regex per line) or the semi-structured json/xml (path per field).
  const [format, setFormat] = useState<DataFormat>(existing?.format ?? 'text')
  const [recordPath, setRecordPath] = useState(existing?.recordPath ?? '')
  const [fields, setFields] = useState<ExtractionField[]>(
    (existing?.fields ?? []).map((f) => ({ ...f, id: f.id ?? newFieldId() })),
  )
  const structured = format !== 'text'
  // Compound steps (optional): rules that build the final STEP from several fields.
  const [compound, setCompound] = useState<CompoundRule[]>(
    (existing?.compound ?? []).map((r) => ({ ...r, id: r.id ?? newFieldId() })),
  )
  const [activeRole, setActiveRole] = useState<FieldRole>('timestamp')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const previewRef = useRef<HTMLDivElement>(null)

  const setField = (id: string, patch: Partial<ExtractionField>) => {
    // Compound rules reference a field BY NAME, so a rename would otherwise orphan
    // every rule pointing at the old one. Carry the rename into the rules instead —
    // the reference follows the field and nothing silently stops matching.
    const before = fields.find((f) => f.id === id)?.name.trim() ?? ''
    const after = (patch.name ?? '').trim()
    if (patch.name !== undefined && before && after && before !== after) {
      setCompound((rs) =>
        rs.map((r) => ({
          ...r,
          when: r.when.map((c) => (c.field.trim() === before ? { ...c, field: after } : c)),
        })),
      )
    }
    setFields((fs) => fs.map((f) => (f.id === id ? { ...f, ...patch } : f)))
  }
  const removeField = (id: string) => {
    // Guarded in the UI by the lock, and here too so no other path can orphan a rule.
    const name = fields.find((f) => f.id === id)?.name.trim() ?? ''
    if (name && rulesUsingField(compound, name).length > 0) return
    setFields((fs) => fs.filter((f) => f.id !== id))
  }

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

  // Structured mapping: clicking a leaf assigns its path to the active role. Single roles
  // (timestamp/id/step) fill/replace their one field; meta/aux add another.
  const assignPath = (path: string) => {
    const single = activeRole !== 'meta' && activeRole !== 'aux'
    if (single) {
      const existing = fields.find((f) => f.role === activeRole)
      if (existing) setField(existing.id!, { path })
      else
        setFields((fs) => [
          ...fs,
          { id: newFieldId(), name: activeRole, role: activeRole, regex: '', path },
        ])
    } else {
      setFields((fs) => [
        ...fs,
        { id: newFieldId(), name: defaultName(activeRole, fs), role: activeRole, regex: '', path },
      ])
    }
  }
  const addBlankStructuredField = () =>
    setFields((fs) => [
      ...fs,
      { id: newFieldId(), name: defaultName(activeRole, fs), role: activeRole, regex: '', path: '' },
    ])

  // The role a leaf path is already mapped to (for the picker's inline badges), so the
  // whole mapping is visible in one list instead of scrolling between list and rows.
  const mappedBy = (path: string) => {
    const f = fields.find((x) => (x.path ?? '') !== '' && (x.path ?? '') === path)
    if (!f) return null
    const label = f.role === 'meta' ? 'Meta' : f.role === 'aux' ? 'Helper' : ROLE_LABEL[f.role]
    return { label, color: ROLE_COLOR[f.role] }
  }

  // When a file is picked, its detected format drives the mapping style. Suggested fields
  // pre-fill a new (empty) structured source type so the user starts from a mapping.
  const onPickFile = (record: string, detection: import('../types').StructureDetection) => {
    setSample(record)
    setFormat(detection.format)
    setRecordPath(detection.recordPath ?? '')
    if (detection.format !== 'text' && fields.length === 0 && detection.fields.length > 0) {
      // Pre-fill the confidently-guessed id/step/timestamp plus at most three metas (only
      // META_1..3 are ever written), so the mapping starts compact — the user clicks more
      // leaves in the picker to add any further fields rather than starting from a wall.
      let metas = 0
      const suggested = detection.fields.filter((f) => {
        if (f.role !== 'meta') return true
        metas += 1
        return metas <= 3
      })
      setFields(
        suggested.map((f) => ({
          id: newFieldId(),
          name: f.name,
          role: f.role,
          regex: '',
          path: f.path,
          format: f.format,
          title: '',
        })),
      )
    }
  }

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
      format,
      recordPath: format === 'xml' ? recordPath.trim() : '',
      fields: fields.map(({ name, role, regex, path, format: fieldFmt, title }) => ({
        name: name.trim() || role,
        role,
        regex,
        path,
        format: fieldFmt,
        title,
      })),
      // Compound rules match on extracted field VALUES, so they apply to every format;
      // only complete rules are sent (the backend drops incomplete ones anyway).
      compound: compound
        .filter((r) => r.step.trim() && r.when.some((c) => c.field.trim()))
        .map((r) => ({
          step: r.step.trim(),
          when: r.when.filter((c) => c.field.trim()),
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
  const tsValue = tsField ? valueOf(format, sample, tsField) : ''
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
          <Field label="Load an example from a file">
            <SourceTypeFilePicker selected={sample} onPick={onPickFile} />
          </Field>
          <Field label="Data format">
            <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <select
                className="text-input"
                value={format}
                onChange={(e) => setFormat(e.target.value as DataFormat)}
                style={{ width: 190, flex: 'none' }}
              >
                <option value="text">Text — unstructured (regex)</option>
                <option value="json">JSON — array or JSONL (paths)</option>
                <option value="xml">XML (paths)</option>
              </select>
              <span className="t-caption2 fg-tertiary">
                {structured
                  ? 'Fields are located by a path selector, not a regex.'
                  : 'Each field is captured with a regular expression.'}
              </span>
            </div>
          </Field>
          <Field label={structured ? '…or paste one example record' : '…or paste an example log entry'}>
            <textarea
              className="text-input"
              value={sample}
              onChange={(e) => setSample(e.target.value)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                // A record dragged from the file picker above lands here as the example.
                const rec =
                  e.dataTransfer.getData('application/x-pmw-record') ||
                  e.dataTransfer.getData('text/plain')
                if (rec) {
                  e.preventDefault()
                  setSample(rec)
                }
              }}
              rows={5}
              placeholder={
                structured
                  ? format === 'xml'
                    ? '<event id="c1"><step>login</step><ts>2026-08-03T14:05:09</ts></event>'
                    : '{"caseId": "c1", "step": "login", "ts": "2026-08-03T14:05:09"}'
                  : '2026-08-03T14:05:09Z INFO OrderReceived case_id=abc-123 …'
              }
              style={{ fontFamily: 'var(--mono, monospace)', fontSize: 12 }}
            />
          </Field>
          <span className="t-caption2 fg-tertiary">
            {structured
              ? 'Pick one record as the example. On the next step you map each field to a path — click a field in the record, or type its path.'
              : "Pick one record as the example. On the next step you'll map each field yourself — highlight a segment and assign it, or type its regex."}
          </span>
        </>
      )}

      {step === 2 && (
        <>
          {structured ? (
            <details className="iwiz-raw-record">
              <summary className="t-caption fg-secondary" style={{ cursor: 'pointer' }}>
                Raw example record
              </summary>
              <div
                className="text-input"
                style={{
                  marginTop: 4, fontFamily: 'var(--mono, monospace)', fontSize: 12,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 150, overflow: 'auto',
                }}
              >
                {sample || <span className="fg-tertiary">Pick a record on the previous step.</span>}
              </div>
            </details>
          ) : (
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
          )}

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

          {structured ? (
            <>
              <div className="row" style={{ gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <span className="t-caption fg-secondary">
                  Click a field to map it to <strong style={{ color: ROLE_COLOR[activeRole] }}>
                    {activeRole === 'meta' ? 'Metas' : ROLE_LABEL[activeRole]}
                  </strong>.
                </span>
                <span className="spacer" />
                <button className="btn small" onClick={addBlankStructuredField}>＋ Add field</button>
              </div>
              {format === 'xml' ? (
                <XmlPathPicker
                  sample={sample}
                  recordPath={recordPath}
                  onRecordPath={setRecordPath}
                  onPick={assignPath}
                  color={ROLE_COLOR[activeRole]}
                  mappedBy={mappedBy}
                />
              ) : (
                <JsonPathPicker
                  sample={sample}
                  onPick={assignPath}
                  color={ROLE_COLOR[activeRole]}
                  mappedBy={mappedBy}
                />
              )}
            </>
          ) : (
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button className="btn" style={{ color: ROLE_COLOR[activeRole] }} onClick={() => void useSelection()}>
                🎯 Use selection
              </button>
              <button className="btn" onClick={addBlankField}>＋ Add field</button>
            </div>
          )}

          {roleFields.length === 0 ? (
            <span className="t-caption fg-tertiary">
              No {activeRole === 'meta' ? 'meta fields' : ROLE_LABEL[activeRole].toLowerCase()} yet —{' '}
              {structured ? 'click a field above, or add one.' : 'select a segment above and map it, or add a field.'}
            </span>
          ) : (
            <div className="col" style={{ gap: 8 }}>
              {roleFields.map((f) =>
                structured ? (
                  <StructuredFieldRow
                    key={f.id}
                    field={f}
                    format={format}
                    sample={sample}
                    onChange={(patch) => setField(f.id!, patch)}
                    onRemove={() => removeField(f.id!)}
                  />
                ) : (
                  <FieldRow
                    key={f.id}
                    field={f}
                    sample={sample}
                    usedBy={rulesUsingField(compound, f.name)}
                    onChange={(patch) => setField(f.id!, patch)}
                    onRemove={() => removeField(f.id!)}
                  />
                ),
              )}
            </div>
          )}

          {/* Compound steps belong to the STEP mapping — they only ever produce a
              STEP value — so they live inside that tab rather than under all of them.
              They match on extracted field VALUES, so they work for every format. */}
          {activeRole === 'step' && (
            <CompoundSection
              rules={compound}
              fields={fields}
              format={format}
              sample={sample}
              onChange={setCompound}
              onFieldsChange={setFields}
            />
          )}

          {fields.length > 0 && (
            <JourneysRecordPreview
              fields={fields}
              format={format}
              sample={sample}
              normalizedTs={normalizedTs}
              compound={compound}
            />
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
              {structured ? (
                sample || <span className="fg-tertiary">No example record.</span>
              ) : (
                <Highlighted highlights={highlights} />
              )}
            </div>
          </Field>
          <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
            <div className="t-caption fg-secondary">{name || '(unnamed)'}</div>
            <span className="badge" style={{ fontSize: 11 }}>{FORMAT_LABEL[format]}</span>
            {format === 'xml' && recordPath && (
              <code className="t-caption2 fg-tertiary">record: {recordPath}</code>
            )}
          </div>
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
                  {structured ? f.path : f.regex}
                </code>
                {f.role === 'timestamp' && f.format && (
                  <span className="t-caption2 fg-tertiary">→ {f.format}</span>
                )}
              </div>
            ))}
          </div>
          {compound.length > 0 && (
            <div className="col" style={{ gap: 4 }}>
              <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
                Compound steps
              </span>
              {compound.map((r) => (
                <div key={r.id} className="t-caption2 fg-tertiary">
                  <strong style={{ color: 'var(--green)' }}>{r.step || '(no step)'}</strong>
                  {' ← '}
                  {r.when
                    .filter((c) => c.field.trim())
                    .map((c) => `${c.field} ${COMPOUND_OP_LABEL[c.op]} "${c.value}"`)
                    .join(' and ') || '(no conditions)'}
                </div>
              ))}
            </div>
          )}

          {fields.length > 0 && (
            <JourneysRecordPreview
              fields={fields}
              format={format}
              sample={sample}
              normalizedTs={normalizedTs}
              compound={compound}
            />
          )}
        </>
      )}

      {error && <div className="t-caption fg-red">{error}</div>}
      </div>
    </Sheet>
  )
}

/** Compound steps (optional): rules that build the final STEP from several extracted
 *  fields — e.g. step "login" + status "200" → "login successful". Shown as compact
 *  badges (about four visible, then scroll); a badge opens a temporary panel to edit
 *  that rule. Rules are checked in order and the first whose conditions all hold wins;
 *  when none match the plain step field's value is used, so rules are always additive. */
function CompoundSection({
  rules,
  fields,
  format,
  sample,
  onChange,
  onFieldsChange,
}: {
  rules: CompoundRule[]
  fields: ExtractionField[]
  format: DataFormat
  sample: string
  onChange: (next: CompoundRule[]) => void
  onFieldsChange: (updater: (fs: ExtractionField[]) => ExtractionField[]) => void
}) {
  const [editing, setEditing] = useState<CompoundRule | null>(null)

  const values = fieldValues(fields, format, sample)
  const derived = deriveCompoundStep(rules, values)
  const stepFieldName = fields.find((f) => f.role === 'step')?.name.trim() ?? ''

  const addRule = () => {
    const rule: CompoundRule = {
      id: newFieldId(),
      step: '',
      // Two conditions by default — a compound step combines at least two fields.
      when: [
        { field: stepFieldName, op: 'eq', value: '' },
        { field: '', op: 'eq', value: '' },
      ],
    }
    onChange([...rules, rule])
    setEditing(rule)
  }

  return (
    <div className="col" style={{ gap: 8, marginTop: 6 }}>
      <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
        <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
          Compound steps
        </span>
        <span className="t-caption2 fg-tertiary">
          optional{rules.length > 0 ? ` · ${rules.length}` : ''}
        </span>
        <span className="spacer" />
        <button className="btn small" onClick={addRule}>＋ Add rule</button>
      </div>

      {rules.length === 0 ? (
        <span className="t-caption2 fg-tertiary">
          Build the step from more than one field when the log splits it — e.g. step
          “login” plus status “200” becomes “login successful”. Values needed only for
          matching can be extracted as helper fields, which are never written to the
          database, so your META columns stay free for business attributes.
        </span>
      ) : (
        <>
          {/* ~3 badges visible (each ≈52px + gap), then the list scrolls. */}
          <div className="card-list" style={{ maxHeight: 190 }}>
            {rules.map((r, i) => {
              const conditions = r.when.filter((c) => c.field.trim())
              const matches = deriveCompoundStep([r], values) != null
              return (
                <div
                  key={r.id}
                  className="card"
                  style={{ minHeight: 52, cursor: 'pointer' }}
                  title="Edit this rule"
                  onClick={() => setEditing(r)}
                >
                  <span
                    aria-hidden
                    className="t-caption2 fg-tertiary"
                    style={{ width: 16, flex: 'none', textAlign: 'right' }}
                    // The order matters: the first matching rule wins.
                    title={`Rule ${i + 1} — checked in this order`}
                  >
                    {i + 1}
                  </span>
                  <div className="card-body">
                    <span className="card-title" style={{ color: 'var(--green)' }}>
                      {r.step.trim() || '(no step yet)'}
                    </span>
                    <span className="card-sub fg-tertiary">
                      {conditions.length
                        ? conditions
                            .map((c) => `${c.field} ${COMPOUND_OP_LABEL[c.op]} “${c.value}”`)
                            .join(' · ')
                        : 'no conditions yet'}
                    </span>
                  </div>
                  {matches && (
                    <span title="Matches the sample line" style={{ color: 'var(--green)' }}>✓</span>
                  )}
                  <button
                    className="icon-btn"
                    style={{ width: 22, height: 22, color: 'var(--secondary)' }}
                    title="Remove rule"
                    aria-label="Remove rule"
                    onClick={(e) => {
                      e.stopPropagation()
                      onChange(rules.filter((x) => x.id !== r.id))
                    }}
                  >
                    ✕
                  </button>
                </div>
              )
            })}
          </div>

          <span className="t-caption2" style={{ color: derived ? 'var(--green)' : 'var(--secondary)' }}>
            {derived
              ? `✓ For the sample line the step becomes “${derived}”.`
              : '• No rule matches the sample line — the plain STEP value would be used.'}
          </span>
        </>
      )}

      {editing && (
        <CompoundRuleEditor
          rule={rules.find((r) => r.id === editing.id) ?? editing}
          fields={fields}
          format={format}
          sample={sample}
          onChange={(next) => onChange(rules.map((r) => (r.id === next.id ? next : r)))}
          onFieldsChange={onFieldsChange}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

/** The temporary panel for one compound rule: its resulting step, its conditions, and
 *  a place to add a **helper field** on the spot — a value extracted only so a rule can
 *  match on it, never written to the database (so META stays free for business data). */
function CompoundRuleEditor({
  rule,
  fields,
  format,
  sample,
  onChange,
  onFieldsChange,
  onClose,
}: {
  rule: CompoundRule
  fields: ExtractionField[]
  format: DataFormat
  sample: string
  onChange: (next: CompoundRule) => void
  onFieldsChange: (updater: (fs: ExtractionField[]) => ExtractionField[]) => void
  onClose: () => void
}) {
  const structured = format !== 'text'
  const [helperName, setHelperName] = useState('')
  // The helper's selector — a regex for text, a path for JSON/XML.
  const [helperSel, setHelperSel] = useState('')

  const named = fields.filter((f) => f.name.trim())
  const values = fieldValues(fields, format, sample)
  const matches = deriveCompoundStep([rule], values) != null

  const setWhen = (i: number, patch: Partial<CompoundCondition>) => {
    const when = [...rule.when]
    when[i] = { ...when[i], ...patch }
    onChange({ ...rule, when })
  }

  // Preview what the helper's selector extracts from the sample record.
  const helperResult = structured
    ? (() => {
        const v = resolveFieldValue(format, sample, helperSel)
        return { ok: v != null, value: v ?? '', error: false }
      })()
    : testPattern(sample, helperSel)
  const canAddHelper = Boolean(helperName.trim() && helperSel.trim())
  const addHelper = () => {
    if (!canAddHelper) return
    const name = helperName.trim()
    onFieldsChange((fs) => [
      ...fs,
      structured
        ? { id: newFieldId(), name, role: 'aux', regex: '', path: helperSel.trim() }
        : { id: newFieldId(), name, role: 'aux', regex: helperSel.trim() },
    ])
    // Point the first empty condition at the field just created.
    const idx = rule.when.findIndex((c) => !c.field.trim())
    if (idx >= 0) setWhen(idx, { field: name })
    else onChange({ ...rule, when: [...rule.when, { field: name, op: 'eq', value: '' }] })
    setHelperName('')
    setHelperSel('')
  }

  return (
    <Sheet
      title="Compound step rule"
      icon="⚗️"
      onClose={onClose}
      footer={
        <>
          <span
            className="t-caption2"
            style={{ color: matches ? 'var(--green)' : 'var(--secondary)' }}
          >
            {matches ? '✓ matches the sample line' : '• does not match the sample line'}
          </span>
          <span className="spacer" />
          <button className="btn prominent" onClick={onClose}>Done</button>
        </>
      }
    >
      <div className="iwiz-col narrow">
        <label className="col" style={{ gap: 4 }}>
          <span className="t-caption fg-secondary">Step becomes</span>
          <input
            className="text-input"
            value={rule.step}
            placeholder="e.g. login successful"
            autoFocus
            onChange={(e) => onChange({ ...rule, step: e.target.value })}
            style={{ color: 'var(--green)', fontWeight: 600 }}
          />
        </label>

        <span className="t-caption fg-secondary" style={{ fontWeight: 600, marginTop: 6 }}>
          Conditions — all must hold
        </span>
        {rule.when.map((c, i) => (
          <div key={i} className="col" style={{ gap: 4 }}>
            <div className="row" style={{ gap: 6, alignItems: 'center' }}>
              <span className="t-caption2 fg-tertiary" style={{ width: 30, flex: 'none' }}>
                {i === 0 ? 'when' : 'and'}
              </span>
              <select
                className="text-input"
                value={c.field}
                onChange={(e) => setWhen(i, { field: e.target.value })}
                style={{ flex: 1, minWidth: 0 }}
              >
                <option value="">(field)</option>
                {named.map((f) => (
                  <option key={f.id} value={f.name.trim()}>
                    {f.name.trim()}
                    {f.role === 'aux' ? ' (helper)' : ''}
                  </option>
                ))}
              </select>
              {rule.when.length > 1 && (
                <button
                  className="icon-btn"
                  title="Remove condition"
                  aria-label="Remove condition"
                  onClick={() => onChange({ ...rule, when: rule.when.filter((_, j) => j !== i) })}
                >
                  −
                </button>
              )}
            </div>
            <div className="row" style={{ gap: 6, alignItems: 'center', paddingLeft: 36 }}>
              <select
                className="text-input"
                value={c.op}
                onChange={(e) => setWhen(i, { op: e.target.value as CompoundOp })}
                style={{ width: 130, flex: 'none' }}
              >
                {COMPOUND_OPS.map((op) => (
                  <option key={op} value={op}>{COMPOUND_OP_LABEL[op]}</option>
                ))}
              </select>
              <input
                className="text-input"
                value={c.value}
                placeholder="value"
                onChange={(e) => setWhen(i, { value: e.target.value })}
                style={{ flex: 1, minWidth: 0 }}
              />
              {c.field && values[c.field] != null && (
                <span
                  className="t-caption2 fg-tertiary"
                  title="What this field captures from the sample line"
                  style={{ whiteSpace: 'nowrap' }}
                >
                  = {values[c.field]}
                </span>
              )}
            </div>
          </div>
        ))}
        <button
          className="btn small"
          style={{ alignSelf: 'flex-start' }}
          onClick={() => onChange({ ...rule, when: [...rule.when, { field: '', op: 'eq', value: '' }] })}
        >
          ＋ Add condition
        </button>

        <div
          className="col"
          style={{
            gap: 6, marginTop: 10, padding: 10, borderRadius: 10, background: 'var(--fill)',
          }}
        >
          <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
            Add a helper field
          </span>
          <span className="t-caption2 fg-tertiary">
            Extract a value only needed for matching (an HTTP status, a result code). Helper
            fields are <strong>never written to the database</strong>, so your three META
            columns stay free for business attributes.
          </span>
          <div className="row" style={{ gap: 6 }}>
            <input
              className="text-input"
              value={helperName}
              placeholder="name, e.g. status"
              onChange={(e) => setHelperName(e.target.value)}
              style={{ width: 130, flex: 'none' }}
            />
            <input
              className="text-input"
              value={helperSel}
              placeholder={
                structured
                  ? format === 'xml' ? 'path e.g. @status' : 'path e.g. status'
                  : 'regex with one capture group'
              }
              spellCheck={false}
              onChange={(e) => setHelperSel(e.target.value)}
              style={{ flex: 1, minWidth: 0, fontFamily: 'var(--mono, monospace)', fontSize: 12 }}
            />
            <button className="btn" disabled={!canAddHelper} onClick={addHelper}>Add</button>
          </div>
          {helperSel.trim() && (
            <span
              className="t-caption2"
              style={{ color: helperResult.ok ? 'var(--green)' : 'var(--orange)' }}
            >
              {helperResult.ok
                ? `✓ ${structured ? 'value' : 'captures'} “${helperResult.value}” from the sample`
                : helperResult.error
                  ? '⚠ invalid regex'
                  : structured ? '• no value at this path' : '• no match in the sample line'}
            </span>
          )}
        </div>
      </div>
    </Sheet>
  )
}

/** The steps of every compound rule that references `name` — a field with any is locked
 *  against deletion, because removing it would leave those rules unable to match. */
function rulesUsingField(rules: CompoundRule[], name: string): string[] {
  const key = (name || '').trim()
  if (!key) return []
  return rules
    .filter((r) => r.when.some((c) => c.field.trim() === key))
    .map((r) => r.step.trim() || '(unnamed rule)')
}

/** What each named field extracts from the sample — the values compound rules match on.
 *  Format-aware: a regex match for text, a path selector result for JSON/XML. */
function fieldValues(
  fields: ExtractionField[],
  format: DataFormat,
  sample: string,
): Record<string, string> {
  const values: Record<string, string> = {}
  for (const f of fields) {
    const name = f.name.trim()
    if (!name) continue
    const v = valueOf(format, sample, f)
    if (v) values[name] = v
  }
  return values
}

function FieldRow({
  field,
  sample,
  usedBy,
  onChange,
  onRemove,
}: {
  field: ExtractionField
  sample: string
  /** Steps of the compound rules referencing this field — non-empty means it is locked. */
  usedBy: string[]
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
    <div
      className="col field-row"
      style={{ gap: 6, padding: 10, borderRadius: 10, background: 'var(--fill)' }}
    >
      {/* field name (or role label) + regex on one line */}
      <div className="row" style={{ gap: 6, alignItems: 'center' }}>
        {field.role === 'meta' || field.role === 'aux' ? (
          <input
            className="text-input"
            value={field.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder={field.role === 'aux' ? 'helper name' : 'field name'}
            title={
              field.role === 'aux'
                ? 'Compound rules reference a helper by this name'
                : undefined
            }
            style={{
              width: 130,
              flex: 'none',
              ...(field.role === 'aux' ? { color: ROLE_COLOR.aux } : {}),
            }}
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
        {usedBy.length > 0 ? (
          // Deleting it would leave those rules pointing at a field that no longer
          // exists, so they would quietly stop matching. Refuse, and say why.
          <span
            className="icon-btn"
            style={{ cursor: 'not-allowed', color: 'var(--orange)' }}
            aria-disabled="true"
            role="img"
            aria-label={`Locked — used by ${usedBy.length} compound rule${usedBy.length === 1 ? '' : 's'}`}
            title={
              `Used by ${usedBy.length} compound step rule${usedBy.length === 1 ? '' : 's'} ` +
              `(${usedBy.join(', ')}).\n\nRemove the field from those rules first — ` +
              `deleting it now would stop them matching. Renaming is safe: the rules follow the new name.`
            }
          >
            🔒
          </span>
        ) : (
          <button className="icon-btn" title="Remove field" aria-label="Remove field" onClick={onRemove}>
            ✕
          </button>
        )}
      </div>
      {field.role === 'meta' && (
        <input
          className="text-input"
          value={field.title ?? ''}
          onChange={(e) => onChange({ title: e.target.value })}
          placeholder="Business name (e.g. Book ID) — shown in the app"
        />
      )}
      {usedBy.length > 0 && (
        <span className="t-caption2" style={{ color: 'var(--orange)' }}>
          🔒 Used by {usedBy.length} compound rule{usedBy.length === 1 ? '' : 's'}:{' '}
          {usedBy.join(', ')} — remove it there before deleting this field. Renaming is safe.
        </span>
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

/** The structured (JSON/XML) counterpart of FieldRow: a field mapped by a PATH selector
 *  rather than a regex. Shows the value the path resolves to in the sample record, and —
 *  for a timestamp — its normalised form + inferred parse format (stored with the field). */
function StructuredFieldRow({
  field,
  format,
  sample,
  onChange,
  onRemove,
}: {
  field: ExtractionField
  format: DataFormat
  sample: string
  onChange: (patch: Partial<ExtractionField>) => void
  onRemove: () => void
}) {
  const value = field.path ? resolveFieldValue(format, sample, field.path) : null
  const color = value != null ? 'var(--green)' : 'var(--secondary)'

  const [ts, setTs] = useState<{ format: string; normalized: string } | null>(null)
  const matchValue = field.role === 'timestamp' && value != null ? value : undefined
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
    <div className="col field-row" style={{ gap: 6, padding: 10, borderRadius: 10, background: 'var(--fill)' }}>
      <div className="row" style={{ gap: 6, alignItems: 'center' }}>
        {field.role === 'meta' || field.role === 'aux' ? (
          <input
            className="text-input"
            value={field.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder={field.role === 'aux' ? 'helper name' : 'field name'}
            style={{ width: 130, flex: 'none', ...(field.role === 'aux' ? { color: ROLE_COLOR.aux } : {}) }}
          />
        ) : (
          <span className="t-caption" style={{ fontWeight: 600, color: ROLE_COLOR[field.role], width: 96, flex: 'none' }}>
            {ROLE_LABEL[field.role]}
          </span>
        )}
        <input
          className="text-input"
          value={field.path ?? ''}
          onChange={(e) => onChange({ path: e.target.value })}
          placeholder={format === 'xml' ? 'path e.g. @id or user/name' : 'path e.g. user.id or items[0].sku'}
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
        {field.path
          ? value != null
            ? `✓ value: ${value}`
            : '• no value at this path in the sample'
          : '• enter a path'}
      </span>
      {field.role === 'timestamp' && value != null && ts && (
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
  format,
  sample,
  normalizedTs,
  compound = [],
}: {
  fields: ExtractionField[]
  format: DataFormat
  sample: string
  normalizedTs: string
  compound?: CompoundRule[]
}) {
  const firstValue = (role: FieldRole): string => {
    const f = fields.find((x) => x.role === role)
    if (!f) return ''
    return valueOf(format, sample, f)
  }
  // The STEP a real import would write: a matching compound rule wins over the plain
  // step field, so the preview reflects the rules as you build them.
  const namedValues: Record<string, string> = {}
  for (const f of fields) {
    const nm = f.name.trim()
    if (!nm) continue
    const v = valueOf(format, sample, f)
    if (v) namedValues[nm] = v
  }
  const compoundStep = deriveCompoundStep(compound, namedValues)

  const metas = fields.filter((f) => f.role === 'meta')
  const metaCell = (i: number) => {
    const f = metas[i]
    if (!f) return null
    return { name: f.title || f.name, value: valueOf(format, sample, f) }
  }

  const rows: { col: string; note?: string; value: string; muted?: boolean }[] = [
    { col: 'PROJECT_ID', value: '(set when the source runs)', muted: true },
    // The original id is shown here; it's stored MD5-hashed in JOURNEYS.
    { col: 'EVENT_ID', note: 'original — stored as MD5', value: firstValue('id') },
    { col: 'STEP', note: compoundStep ? 'compound' : undefined, value: compoundStep ?? firstValue('step') },
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
  // Metas and helpers can both occur several times and are referenced by name (helpers
  // by compound rules), so each needs a distinct default rather than the role name.
  if (role !== 'meta' && role !== 'aux') return role
  const prefix = role === 'aux' ? 'helper' : 'meta'
  const taken = new Set(existing.map((f) => f.name.trim()))
  let n = existing.filter((f) => f.role === role).length + 1
  while (taken.has(`${prefix}_${n}`)) n += 1
  return `${prefix}_${n}`
}
