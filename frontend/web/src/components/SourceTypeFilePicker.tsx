/** Source-type wizard, step 1 helper: choose a file from the sandboxed sources
 *  directory, auto-detect its record delimiter (LF / CRLF / CR / FF / …), preview the
 *  first few records, and pick one to use as the example the mapping step works from.
 *
 *  A record is picked by dragging its card onto the drop target (or clicking it — the
 *  same action, keyboard/pointer-friendly). The chosen record's text is handed back via
 *  `onPick`, which the wizard uses as its `sample`. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import type { IntegrationFile, RecordDetection } from '../types'

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const DRAG_MIME = 'application/x-pmw-record'

export function SourceTypeFilePicker({
  selected,
  onPick,
}: {
  /** The record text currently chosen (shown in the drop target). */
  selected: string
  onPick: (record: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<IntegrationFile[] | null>(null)
  const [filesError, setFilesError] = useState<string | null>(null)
  const [path, setPath] = useState('')
  const [detection, setDetection] = useState<RecordDetection | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [detectError, setDetectError] = useState<string | null>(null)

  // Load the sandbox file list the first time the picker is opened.
  useEffect(() => {
    if (!open || files !== null) return
    let alive = true
    void (async () => {
      try {
        const list = await api.listIntegrationFiles()
        if (alive) setFiles(list)
      } catch (e) {
        if (alive) setFilesError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      alive = false
    }
  }, [open, files])

  const detect = async (p: string, delimiter = '') => {
    setDetecting(true)
    setDetectError(null)
    try {
      setDetection(await api.detectRecords(p, delimiter, 5))
    } catch (e) {
      setDetection(null)
      setDetectError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetecting(false)
    }
  }

  const chooseFile = (p: string) => {
    setPath(p)
    setOpen(false)
    void detect(p)
  }

  return (
    <div className="col" style={{ gap: 8 }}>
      {/* File chooser */}
      <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button className="btn small" onClick={() => setOpen((o) => !o)}>
          📄 Choose a file…
        </button>
        {path && (
          <span className="t-caption2 fg-secondary" style={{ minWidth: 0, wordBreak: 'break-all' }}>
            {path}
          </span>
        )}
        {detecting && <span className="t-caption2 fg-tertiary">Reading…</span>}
      </div>

      {open && (
        <div
          className="card-list"
          style={{ maxHeight: 200, border: '1px solid var(--border)', borderRadius: 8, padding: 4 }}
        >
          {filesError && <div className="t-caption fg-red" style={{ padding: 6 }}>{filesError}</div>}
          {files && files.length === 0 && !filesError && (
            <div className="t-caption2 fg-tertiary" style={{ padding: 6 }}>
              No files in the sources directory. Place log files there (the mounted
              <code> integration_files</code> volume in Docker), or paste an example below.
            </div>
          )}
          {(files ?? []).map((f) => (
            <button
              key={f.name}
              className="card"
              style={{ textAlign: 'left', minHeight: 0, cursor: 'pointer' }}
              onClick={() => chooseFile(f.name)}
            >
              <span aria-hidden style={{ fontSize: 15 }}>📄</span>
              <div className="card-body">
                <span className="card-title" style={{ wordBreak: 'break-all' }}>{f.name}</span>
                <span className="card-sub">{humanSize(f.size)}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {detectError && <div className="t-caption fg-red">{detectError}</div>}

      {detection && (
        <>
          {/* Delimiter selector */}
          <label className="col" style={{ gap: 4 }}>
            <span className="t-caption fg-secondary">Record delimiter (auto-detected)</span>
            <select
              className="text-input"
              value={detection.delimiter}
              onChange={(e) => void detect(path, e.target.value)}
              disabled={detecting}
            >
              {detection.candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                  {c.count > 0 ? ` — ${c.count.toLocaleString()} found` : ''}
                </option>
              ))}
            </select>
          </label>

          {/* Draggable record cards */}
          <span className="t-caption fg-secondary">
            Click a record (or drag it into the example box below) to use it. The chosen
            one is highlighted.
          </span>
          <div className="col" style={{ gap: 6 }}>
            {detection.records.map((rec, i) => (
              <div
                key={i}
                role="button"
                tabIndex={0}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(DRAG_MIME, rec)
                  e.dataTransfer.setData('text/plain', rec)
                  e.dataTransfer.effectAllowed = 'copy'
                }}
                onClick={() => onPick(rec)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onPick(rec)
                  }
                }}
                className={`card${selected === rec ? ' selected' : ''}`}
                style={{
                  cursor: 'grab', minHeight: 0, alignItems: 'flex-start',
                  fontFamily: 'var(--mono, monospace)', fontSize: 11.5,
                }}
                title="Click, or drag into the example box below, to use this record"
              >
                <span aria-hidden className="t-caption2 fg-tertiary" style={{ marginTop: 1 }}>
                  ⠿ {i + 1}
                </span>
                <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', flex: 1 }}>{rec}</span>
              </div>
            ))}
            {detection.records.length === 0 && (
              <span className="t-caption2 fg-tertiary">
                No records found with this delimiter — try another above.
              </span>
            )}
            {detection.truncated && (
              <span className="t-caption2 fg-tertiary">Showing the first 5 records.</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
