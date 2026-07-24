/** Power-user connection editor.
 *
 * Lets a *power* user (or an admin) create and edit database/LLM connections
 * from the app, and assign them to other users — the same shape the admin
 * interface exposes, scoped to connections the user owns. */

import { useState } from 'react'
import type { ManagedConnection } from '../types'
import { useStore } from '../store'
import { ConfirmSheet, Sheet } from './ui'

const CERT_MODES = [
  { value: 'verify', label: 'Verify (system trust store)' },
  { value: 'fingerprint', label: 'Pin fingerprint' },
  { value: 'insecure', label: 'Accept any (insecure)' },
]

type Draft = {
  id: string | null
  name: string
  comment: string
  host: string
  port: number
  username: string
  schema: string
  useTLS: boolean
  certModeRaw: string
  fingerprint: string
  minRSAKeySizeBits: number
  llmURL: string
  llmModel: string
  assignments: string[]
}

function draftFrom(conn: ManagedConnection | null): Draft {
  return {
    id: conn?.id ?? null,
    name: conn?.name ?? '',
    comment: conn?.comment ?? '',
    host: conn?.host ?? '',
    port: conn?.port ?? 8563,
    username: conn?.username ?? '',
    schema: conn?.schema ?? '',
    useTLS: conn?.useTLS ?? false,
    certModeRaw: conn?.certModeRaw || 'verify',
    fingerprint: conn?.fingerprint ?? '',
    minRSAKeySizeBits: conn?.minRSAKeySizeBits ?? 2048,
    llmURL: conn?.llmURL ?? '',
    llmModel: conn?.llmModel ?? '',
    assignments: conn?.assignments ?? [],
  }
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="col" style={{ gap: 4 }}>
      <span className="t-caption fg-secondary">{label}</span>
      {children}
    </label>
  )
}

export function ConnectionEditor({
  connection,
  onClose,
}: {
  connection: ManagedConnection | null
  onClose: () => void
}) {
  const store = useStore()
  const isNew = connection === null
  const hasPassword = connection?.hasPassword ?? false
  const hasLLMKey = connection?.hasLLMKey ?? false

  const [draft, setDraft] = useState<Draft>(() => draftFrom(connection))
  // Secrets are write-only: left blank keeps the stored value untouched.
  const [password, setPassword] = useState('')
  const [passwordTouched, setPasswordTouched] = useState(false)
  const [llmKey, setLlmKey] = useState('')
  const [llmKeyTouched, setLlmKeyTouched] = useState(false)

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Test outcome shown next to the Test button — green ok, orange one component
  // failed, red both failed.
  const [testResult, setTestResult] = useState<{
    tone: 'ok' | 'warn' | 'bad'
    text: string
  } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  const body = (): Record<string, unknown> => {
    const b: Record<string, unknown> = {
      id: draft.id,
      name: draft.name.trim(),
      comment: draft.comment.trim(),
      host: draft.host.trim(),
      port: draft.port,
      username: draft.username.trim(),
      schema: draft.schema.trim(),
      useTLS: draft.useTLS,
      certModeRaw: draft.certModeRaw,
      fingerprint: draft.fingerprint.trim(),
      minRSAKeySizeBits: draft.minRSAKeySizeBits,
      llmURL: draft.llmURL.trim(),
      llmModel: draft.llmModel.trim(),
      assignments: draft.assignments,
    }
    if (passwordTouched) b.password = password
    if (llmKeyTouched) b.llmKey = llmKey
    return b
  }

  const runTest = async () => {
    setBusy(true)
    setError(null)
    setTestResult(null)
    const res = await store.testManagedConnection({
      host: draft.host.trim(),
      port: draft.port,
      username: draft.username.trim(),
      password,
      schema: draft.schema.trim(),
      useTLS: draft.useTLS,
      certModeRaw: draft.certModeRaw,
      fingerprint: draft.fingerprint.trim(),
      minRSAKeySizeBits: draft.minRSAKeySizeBits,
      llmURL: draft.llmURL.trim(),
      llmKey,
    })
    setBusy(false)
    const llmConsidered = draft.llmURL.trim() !== ''
    const dbOk = !res.dbError
    const llmOk = !llmConsidered || !res.llmError
    const parts: string[] = []
    parts.push(res.dbError ? `Database: ${res.dbError}` : 'Database OK')
    if (llmConsidered) {
      parts.push(
        res.llmError
          ? `LLM: ${res.llmError}`
          : `LLM OK${res.llmModels.length ? ` (${res.llmModels.length} models)` : ''}`,
      )
    }
    const failures = (dbOk ? 0 : 1) + (llmConsidered && !llmOk ? 1 : 0)
    const total = llmConsidered ? 2 : 1
    const tone = failures === 0 ? 'ok' : failures >= total ? 'bad' : 'warn'
    setTestResult({ tone, text: parts.join('  ·  ') })
  }

  const save = async () => {
    if (!draft.name.trim()) {
      setError('Name is required.')
      return
    }
    setBusy(true)
    setError(null)
    const { ok, error: err } = await store.saveManagedConnection(body())
    setBusy(false)
    if (ok) onClose()
    else setError(err)
  }

  const remove = async () => {
    if (!draft.id) return
    setBusy(true)
    const ok = await store.deleteManagedConnection(draft.id)
    setBusy(false)
    if (ok) onClose()
    else {
      setConfirmDelete(false)
      setError('Delete failed.')
    }
  }

  const toggleAssignment = (username: string) =>
    set(
      'assignments',
      draft.assignments.includes(username)
        ? draft.assignments.filter((u) => u !== username)
        : [...draft.assignments, username],
    )

  return (
    <Sheet
      title={isNew ? 'New Connection' : 'Edit Connection'}
      icon="⛁"
      wide
      onClose={onClose}
      footer={
        <>
          <button className="btn" disabled={busy} onClick={() => void runTest()}>
            Test
          </button>
          {testResult && (
            <span
              className="t-caption2"
              title={testResult.text}
              style={{
                maxWidth: 300,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                color:
                  testResult.tone === 'ok'
                    ? 'var(--green)'
                    : testResult.tone === 'warn'
                      ? 'var(--orange)'
                      : 'var(--red)',
              }}
            >
              {testResult.text}
            </span>
          )}
          {!isNew && (
            <button
              className="btn"
              style={{ color: 'var(--red)' }}
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
            >
              Delete
            </button>
          )}
          <span className="spacer" />
          <button className="btn" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button className="btn prominent" disabled={busy} onClick={() => void save()}>
            Save
          </button>
        </>
      }
    >
      <div className="col" style={{ gap: 12 }}>
        {error && <span className="t-caption fg-red">{error}</span>}

        <Field label="Name">
          <input
            className="text-input"
            value={draft.name}
            onChange={(e) => set('name', e.target.value)}
          />
        </Field>
        <Field label="Comment">
          <input
            className="text-input"
            value={draft.comment}
            onChange={(e) => set('comment', e.target.value)}
          />
        </Field>

        <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
          Database
        </span>
        <div className="row" style={{ gap: 8 }}>
          <Field label="Host">
            <input
              className="text-input"
              value={draft.host}
              onChange={(e) => set('host', e.target.value)}
            />
          </Field>
          <div style={{ width: 96 }}>
            <Field label="Port">
              <input
                className="text-input"
                type="number"
                value={draft.port}
                onChange={(e) => set('port', Number(e.target.value) || 0)}
              />
            </Field>
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <Field label="Username">
            <input
              className="text-input"
              value={draft.username}
              autoComplete="off"
              onChange={(e) => set('username', e.target.value)}
            />
          </Field>
          <Field label="Schema">
            <input
              className="text-input"
              value={draft.schema}
              onChange={(e) => set('schema', e.target.value)}
            />
          </Field>
        </div>
        <Field label="Password">
          <input
            className="text-input"
            type="password"
            value={password}
            autoComplete="new-password"
            placeholder={hasPassword ? '•••••• (unchanged)' : ''}
            onChange={(e) => {
              setPassword(e.target.value)
              setPasswordTouched(true)
            }}
          />
        </Field>

        <label className="row" style={{ gap: 8 }}>
          <input
            type="checkbox"
            style={{ width: 'auto' }}
            checked={draft.useTLS}
            onChange={(e) => set('useTLS', e.target.checked)}
          />
          <span className="t-caption">Use TLS</span>
        </label>
        {draft.useTLS && (
          <div className="col" style={{ gap: 12, paddingLeft: 8 }}>
            <Field label="Certificate mode">
              <select
                className="text-input"
                value={draft.certModeRaw}
                onChange={(e) => set('certModeRaw', e.target.value)}
              >
                {CERT_MODES.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Fingerprint (SHA-256)">
              <input
                className="text-input"
                value={draft.fingerprint}
                placeholder="optional"
                onChange={(e) => set('fingerprint', e.target.value)}
              />
            </Field>
            <Field label="Minimum RSA key size">
              <input
                className="text-input"
                type="number"
                value={draft.minRSAKeySizeBits}
                onChange={(e) => set('minRSAKeySizeBits', Number(e.target.value) || 0)}
              />
            </Field>
          </div>
        )}

        <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
          LLM (optional)
        </span>
        <Field label="Server URL">
          <input
            className="text-input"
            value={draft.llmURL}
            placeholder="https://…"
            onChange={(e) => set('llmURL', e.target.value)}
          />
        </Field>
        <Field label="Model">
          <input
            className="text-input"
            value={draft.llmModel}
            onChange={(e) => set('llmModel', e.target.value)}
          />
        </Field>
        <Field label="API key">
          <input
            className="text-input"
            type="password"
            value={llmKey}
            autoComplete="new-password"
            placeholder={hasLLMKey ? '•••••• (unchanged)' : ''}
            onChange={(e) => {
              setLlmKey(e.target.value)
              setLlmKeyTouched(true)
            }}
          />
        </Field>

        <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
          Assigned users
        </span>
        {store.assignableUsers.length === 0 ? (
          <span className="t-caption2 fg-tertiary">No users available.</span>
        ) : (
          <div
            className="col"
            style={{
              gap: 2,
              maxHeight: 160,
              overflowY: 'auto',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 8,
            }}
          >
            {store.assignableUsers.map((username) => (
              <label key={username} className="row" style={{ gap: 8 }}>
                <input
                  type="checkbox"
                  style={{ width: 'auto' }}
                  checked={draft.assignments.includes(username)}
                  onChange={() => toggleAssignment(username)}
                />
                <span className="t-caption">{username}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {confirmDelete && (
        <ConfirmSheet
          title="Delete connection?"
          message={`“${draft.name}” will be removed for all assigned users. This cannot be undone.`}
          confirmLabel="Delete"
          destructive
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => void remove()}
        />
      )}
    </Sheet>
  )
}
