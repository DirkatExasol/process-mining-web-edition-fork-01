/** Design an aggregate: collapse the selected connected steps into one Σ super-step,
 *  producing a new high-level project (Σ node) and a detail project (drill-down),
 *  written to a chosen (possibly new) schema/connection. Developer-only. */

import { useMemo, useState } from 'react'
import { api } from '../api'
import { validateAggregateSelection } from '../aggregate/connectivity'
import type { CreateAggregateResult } from '../aggregate/types'
import { useStore } from '../store'
import type { ProcessTransition } from '../types'
import { Sheet, Spinner } from '../components/ui'

function TargetRow({
  label,
  connId,
  schema,
  onConn,
  onSchema,
  connections,
}: {
  label: string
  connId: string
  schema: string
  onConn: (v: string) => void
  onSchema: (v: string) => void
  connections: { id: string; name: string }[]
}) {
  return (
    <div className="row" style={{ gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <div className="field" style={{ flex: '1 1 180px', margin: 0 }}>
        <label>{label} — connection</label>
        <select value={connId} onChange={(e) => onConn(e.target.value)}>
          {connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field" style={{ flex: '1 1 160px', margin: 0 }}>
        <label>{label} — schema</label>
        <input
          value={schema}
          onChange={(e) => onSchema(e.target.value)}
          placeholder="same as connection (or a new name)"
        />
      </div>
    </div>
  )
}

export function AggregateDialog({
  members,
  transitions,
  projectId,
  connectionId,
  projectTitle,
  onClose,
  onDone,
}: {
  members: string[]
  transitions: ProcessTransition[]
  projectId: string
  connectionId: string
  projectTitle: string
  onClose: () => void
  onDone: (result: CreateAggregateResult) => void
}) {
  const store = useStore()
  const validation = useMemo(
    () => validateAggregateSelection(members, transitions),
    [members, transitions],
  )

  const [sigmaName, setSigmaName] = useState(`Σ ${members[0] ?? 'Aggregate'}`)
  const [highName, setHighName] = useState(`${projectTitle} (aggregated)`)
  const [detailName, setDetailName] = useState(`${projectTitle} — ${members[0] ?? 'detail'}`)
  const [hiConn, setHiConn] = useState(connectionId)
  const [hiSchema, setHiSchema] = useState('')
  const [detConn, setDetConn] = useState(connectionId)
  const [detSchema, setDetSchema] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const conns = store.connections.map((c) => ({ id: c.id, name: c.name }))
  const canCreate =
    validation.ok && sigmaName.trim() && highName.trim() && detailName.trim() && !busy

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await api.createAggregate(projectId, {
        connectionId,
        members,
        sigmaName: sigmaName.trim(),
        highLevel: { name: highName.trim(), targetConnectionId: hiConn, targetSchema: hiSchema.trim() },
        detail: { name: detailName.trim(), targetConnectionId: detConn, targetSchema: detSchema.trim() },
      })
      onDone(result)
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      title="Create aggregate"
      icon="Σ"
      onClose={onClose}
      footer={
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          {busy && <Spinner />}
          {error && <span style={{ color: 'var(--red)', fontSize: 13 }}>{error}</span>}
          <span style={{ flex: 1 }} />
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" disabled={!canCreate} onClick={() => void create()}>
            Create
          </button>
        </div>
      }
    >
      {/* Members + validation */}
      <p className="fg-secondary" style={{ marginTop: 0, fontSize: 13 }}>
        Collapsing {members.length} steps into one Σ super-step:
      </p>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        {members.map((m) => (
          <span
            key={m}
            className="t-caption2"
            style={{
              background: 'var(--bg-tertiary-grouped, var(--bg-secondary))',
              borderRadius: 6,
              padding: '2px 8px',
              color: validation.isolated.includes(m) ? 'var(--red)' : 'inherit',
            }}
          >
            {m}
          </span>
        ))}
      </div>
      {!validation.ok && (
        <p style={{ color: 'var(--red)', fontSize: 13, margin: '0 0 12px' }}>
          {validation.isolated.length
            ? `These steps aren't connected to the rest of the selection: ${validation.isolated.join(', ')}. Remove them or extend the selection.`
            : validation.components > 1
              ? `The selection forms ${validation.components} separate groups — pick one interconnected group.`
              : 'Select at least two connected steps.'}
        </p>
      )}

      <div className="field" style={{ maxWidth: 360 }}>
        <label>Σ step name</label>
        <input value={sigmaName} onChange={(e) => setSigmaName(e.target.value)} />
      </div>

      <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 10 }}>
        <div className="field" style={{ maxWidth: 420 }}>
          <label>High-level project name (the map with the Σ node)</label>
          <input value={highName} onChange={(e) => setHighName(e.target.value)} />
        </div>
        <TargetRow
          label="High-level"
          connId={hiConn}
          schema={hiSchema}
          onConn={setHiConn}
          onSchema={setHiSchema}
          connections={conns}
        />
      </div>

      <div style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10 }}>
        <div className="field" style={{ maxWidth: 420 }}>
          <label>Detail project name (the drill-down sub-process)</label>
          <input value={detailName} onChange={(e) => setDetailName(e.target.value)} />
        </div>
        <TargetRow
          label="Detail"
          connId={detConn}
          schema={detSchema}
          onConn={setDetConn}
          onSchema={setDetSchema}
          connections={conns}
        />
      </div>

      <p className="fg-secondary" style={{ fontSize: 12, marginTop: 10 }}>
        Leave a schema blank to use the connection's own schema; type a new name to create a
        schema. The originals are untouched.
      </p>
    </Sheet>
  )
}
