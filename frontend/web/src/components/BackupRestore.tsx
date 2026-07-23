/** Backup & restore — port of BackupRestoreView.swift.
 *
 * The exported file is byte-compatible with the macOS app's backups, including
 * the optional AES-256-GCM envelope. */

import { useState } from 'react'
import { api } from '../api'
import { hydrateSettings } from '../settings'
import { useStore } from '../store'
import { formatDateTime } from '../graph/format'
import { Divider, Sheet, Spinner } from './ui'

type Summary = {
  createdAt?: string
  includesPasswords?: boolean
  includesUsername?: boolean
  includesLlmApiKey?: boolean
  connectionCount?: number
  projectCount?: number
  hasLayouts?: boolean
  hasNorms?: boolean
  hasHappyPaths?: boolean
  hasFilterGroups?: boolean
  connectionNames?: string[]
}

const RESTORE_OPTIONS = [
  ['appSettings', 'App settings & preferences'],
  ['connections', 'Connections & servers'],
  ['username', 'Usernames'],
  ['llmApiKey', 'LLM API keys'],
  ['passwords', 'Database passwords'],
  ['layouts', 'Saved node layouts'],
  ['norms', 'Target norms'],
  ['happyPaths', 'Happy paths'],
  ['filterPresets', 'Filter presets'],
] as const

export function BackupRestore({ onClose }: { onClose: () => void }) {
  const store = useStore()
  const [tab, setTab] = useState<'export' | 'restore'>('export')

  // Export state
  const [includePasswords, setIncludePasswords] = useState(false)
  const [includeUsername, setIncludeUsername] = useState(true)
  const [includeLlmApiKey, setIncludeLlmApiKey] = useState(false)
  const [exportPassword, setExportPassword] = useState('')
  const [exporting, setExporting] = useState(false)

  // Restore state
  const [fileName, setFileName] = useState('')
  const [fileContent, setFileContent] = useState('')
  const [restorePassword, setRestorePassword] = useState('')
  const [summary, setSummary] = useState<Summary | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [options, setOptions] = useState<Record<string, boolean>>(
    Object.fromEntries(RESTORE_OPTIONS.map(([key]) => [key, true])),
  )
  const [busy, setBusy] = useState(false)

  const doExport = async () => {
    setExporting(true)
    try {
      const blob = await api.exportBackup({
        includePasswords,
        includeUsername,
        includeLlmApiKey,
        password: exportPassword,
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      const stamp = new Date().toISOString().slice(0, 10)
      anchor.download = `ProcessMining-Backup-${stamp}.json`
      anchor.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  const readFile = async (file: File) => {
    const buffer = await file.arrayBuffer()
    let binary = ''
    const bytes = new Uint8Array(buffer)
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
    const base64 = btoa(binary)
    setFileName(file.name)
    setFileContent(base64)
    setSummary(null)
    setRestoreError(null)
    void inspect(base64, restorePassword)
  }

  const inspect = async (content: string, password: string) => {
    setBusy(true)
    setRestoreError(null)
    try {
      setSummary((await api.inspectBackup(content, password)) as Summary)
    } catch (error) {
      setSummary(null)
      setRestoreError(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  const doRestore = async () => {
    setBusy(true)
    setRestoreError(null)
    try {
      await api.restoreBackup(fileContent, restorePassword, options)
      await hydrateSettings()
      await store.refreshConnections()
      onClose()
    } catch (error) {
      setRestoreError(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet
      title="Backup &amp; Restore"
      icon="🗄"
      onClose={onClose}
      footer={
        tab === 'export' ? (
          <>
            <button className="btn" onClick={onClose}>
              Close
            </button>
            <button
              className="btn prominent"
              disabled={exporting}
              onClick={() => void doExport()}
            >
              {exporting && <Spinner />} Export backup
            </button>
          </>
        ) : (
          <>
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn prominent"
              disabled={!summary || busy}
              onClick={() => void doRestore()}
            >
              {busy && <Spinner />} Restore
            </button>
          </>
        )
      }
    >
      <div className="segmented" style={{ alignSelf: 'flex-start' }}>
        <button
          className={tab === 'export' ? 'active' : ''}
          onClick={() => setTab('export')}
        >
          Export
        </button>
        <button
          className={tab === 'restore' ? 'active' : ''}
          onClick={() => setTab('restore')}
        >
          Restore
        </button>
      </div>

      {tab === 'export' ? (
        <>
          <div className="t-footnote fg-secondary">
            Exports connections, filter presets, happy paths, target norms, node
            layouts, LLM prompt templates and app preferences as a single JSON file.
          </div>
          <label className="row t-callout" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={includeUsername}
              onChange={(e) => setIncludeUsername(e.target.checked)}
            />
            Include database usernames
          </label>
          <label className="row t-callout" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={includePasswords}
              onChange={(e) => setIncludePasswords(e.target.checked)}
            />
            Include database passwords
          </label>
          <label className="row t-callout" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={includeLlmApiKey}
              onChange={(e) => setIncludeLlmApiKey(e.target.checked)}
            />
            Include LLM API keys
          </label>

          {(includePasswords || includeLlmApiKey) && !exportPassword && (
            <div className="legal-note t-caption">
              ⚠ Secrets will be written in plain text unless you set an encryption
              password below.
            </div>
          )}

          <div className="field">
            <span className="field-label">
              Encryption password (optional, AES-256-GCM)
            </span>
            <input
              className="text-input"
              type="password"
              value={exportPassword}
              autoComplete="new-password"
              onChange={(e) => setExportPassword(e.target.value)}
            />
          </div>
        </>
      ) : (
        <>
          <div className="field">
            <span className="field-label">Backup file</span>
            <input
              type="file"
              accept=".json,application/json"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void readFile(file)
              }}
            />
            {fileName && <span className="t-caption fg-secondary">{fileName}</span>}
          </div>

          <div className="field">
            <span className="field-label">Password (if the backup is encrypted)</span>
            <div className="row" style={{ gap: 8 }}>
              <input
                className="text-input"
                type="password"
                value={restorePassword}
                autoComplete="off"
                onChange={(e) => setRestorePassword(e.target.value)}
              />
              <button
                className="btn small"
                disabled={!fileContent || busy}
                onClick={() => void inspect(fileContent, restorePassword)}
              >
                {busy && <Spinner />} Inspect
              </button>
            </div>
          </div>

          {restoreError && <div className="t-caption fg-red">{restoreError}</div>}

          {summary && (
            <>
              <Divider />
              <div className="t-headline">Backup contents</div>
              <div className="col t-footnote" style={{ gap: 3 }}>
                <span>Created: {formatDateTime(summary.createdAt)}</span>
                <span>Connections: {summary.connectionCount ?? 0}</span>
                <span>Projects with settings: {summary.projectCount ?? 0}</span>
                <span>
                  Includes: {summary.includesUsername ? 'usernames' : '—'},{' '}
                  {summary.includesPasswords ? 'passwords' : 'no passwords'},{' '}
                  {summary.includesLlmApiKey ? 'API keys' : 'no API keys'}
                </span>
                {summary.connectionNames && summary.connectionNames.length > 0 && (
                  <span className="fg-secondary">
                    Overwrites: {summary.connectionNames.join(', ')}
                  </span>
                )}
              </div>

              <Divider />
              <div className="t-headline">Restore</div>
              {RESTORE_OPTIONS.map(([key, label]) => (
                <label key={key} className="row t-callout" style={{ gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={options[key]}
                    onChange={(e) =>
                      setOptions((o) => ({ ...o, [key]: e.target.checked }))
                    }
                  />
                  {label}
                </label>
              ))}
            </>
          )}
        </>
      )}
    </Sheet>
  )
}
