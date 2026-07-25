/** Notes list — port of `commentsContent` from ProcessMapView.swift. */

import { useEffect, useMemo, useState } from 'react'
import {
  ImportanceBadge,
  NoteEditorSheet,
  snapshotSummary,
  type NoteEditorTarget,
} from '../components/NoteEditor'
import { Unavailable } from '../components/ui'
import { formatDateTime } from '../graph/format'
import { useStore } from '../store'
import {
  NOTE_IMPORTANCE_LEVELS,
  NOTE_IMPORTANCE_META,
  noteTargetLabel,
  normalizeImportance,
  type NoteImportance,
} from '../types'

type TimeWindow = 'ALL' | '7' | '30' | '90'
const TIME_LABELS: Record<TimeWindow, string> = {
  ALL: 'Any time',
  '7': 'Last 7 days',
  '30': 'Last 30 days',
  '90': 'Last 90 days',
}

export function NotesView() {
  const store = useStore()
  const [editing, setEditing] = useState<NoteEditorTarget | null>(null)
  const [search, setSearch] = useState('')
  const [importance, setImportance] = useState<'ALL' | NoteImportance>('ALL')
  const [author, setAuthor] = useState<string>('ALL')
  const [time, setTime] = useState<TimeWindow>('ALL')
  const [status, setStatus] = useState<'ALL' | 'OPEN' | 'RESOLVED'>('ALL')
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(0)

  // Distinct note authors (by stable login username), labelled with the real name.
  const authors = useMemo(() => {
    const byUser = new Map<string, string>()
    for (const n of store.projectNotes) {
      const key = n.username ?? ''
      if (!byUser.has(key)) byUser.set(key, n.authorName || n.username || '—')
    }
    return [...byUser.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [store.projectNotes])

  const notes = useMemo(() => {
    const term = search.trim().toLowerCase()
    const cutoff = time === 'ALL' ? null : Date.now() - Number(time) * 86_400_000
    return [...store.projectNotes]
      .filter((n) => {
        if (
          term &&
          !n.text.toLowerCase().includes(term) &&
          !noteTargetLabel(n.target).toLowerCase().includes(term)
        )
          return false
        if (importance !== 'ALL' && normalizeImportance(n.importance) !== importance)
          return false
        if (author !== 'ALL' && (n.username ?? '') !== author) return false
        if (status === 'OPEN' && n.resolved) return false
        if (status === 'RESOLVED' && !n.resolved) return false
        if (cutoff !== null && new Date(n.createdAt).getTime() < cutoff) return false
        return true
      })
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  }, [store.projectNotes, search, importance, author, time, status])

  // Any filter change or a resized page resets to the first page.
  useEffect(() => setPage(0), [search, importance, author, time, status, pageSize])

  if (store.projectNotes.length === 0) {
    return (
      <Unavailable
        glyph="🗒"
        title="No Notes"
        description="Click a node or an edge on the process map and choose “Show Notes” to add one."
      />
    )
  }

  const selectStyle: React.CSSProperties = { padding: '4px 8px', fontSize: 13 }

  const pageCount = Math.max(1, Math.ceil(notes.length / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const pageNotes = notes.slice(safePage * pageSize, safePage * pageSize + pageSize)
  const firstShown = notes.length === 0 ? 0 : safePage * pageSize + 1
  const lastShown = Math.min(notes.length, (safePage + 1) * pageSize)

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      <div
        className="row"
        style={{
          padding: '8px 16px',
          gap: 10,
          flexWrap: 'wrap',
          alignItems: 'center',
          background: 'var(--bg-tertiary-grouped)',
          borderBottom: '1px solid var(--separator-soft)',
        }}
      >
        <div className="search-row" style={{ flex: '1 1 200px', maxWidth: 320 }}>
          <span aria-hidden className="fg-secondary">
            🔍
          </span>
          <input
            value={search}
            placeholder="Filter notes"
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button className="fg-secondary" onClick={() => setSearch('')}>
              ⊗
            </button>
          )}
        </div>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Importance
          <select
            className="text-input"
            style={selectStyle}
            value={importance}
            onChange={(e) => setImportance(e.target.value as 'ALL' | NoteImportance)}
          >
            <option value="ALL">All</option>
            {NOTE_IMPORTANCE_LEVELS.map((lvl) => (
              <option key={lvl} value={lvl}>
                {NOTE_IMPORTANCE_META[lvl].label}
              </option>
            ))}
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          User
          <select
            className="text-input"
            style={selectStyle}
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
          >
            <option value="ALL">All</option>
            {authors.map(([user, label]) => (
              <option key={user} value={user}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Time
          <select
            className="text-input"
            style={selectStyle}
            value={time}
            onChange={(e) => setTime(e.target.value as TimeWindow)}
          >
            {(Object.keys(TIME_LABELS) as TimeWindow[]).map((w) => (
              <option key={w} value={w}>
                {TIME_LABELS[w]}
              </option>
            ))}
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Status
          <select
            className="text-input"
            style={selectStyle}
            value={status}
            onChange={(e) => setStatus(e.target.value as 'ALL' | 'OPEN' | 'RESOLVED')}
          >
            <option value="ALL">All</option>
            <option value="OPEN">Open</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Per page
          <select
            className="text-input"
            style={selectStyle}
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
          >
            {[5, 10, 20].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        <span className="t-caption fg-secondary">
          {notes.length} of {store.projectNotes.length}
        </span>
        <span className="spacer" />
        <button className="btn small" onClick={() => void store.loadNotes()}>
          ↻ Reload
        </button>
      </div>

      <div className="scroll-view">
        {notes.length === 0 && (
          <div
            className="t-caption fg-secondary"
            style={{ padding: '16px', textAlign: 'center' }}
          >
            No notes match the current filters.
          </div>
        )}
        {pageNotes.map((note) => (
          <button
            key={note.id}
            className="note-card"
            style={{ textAlign: 'left', cursor: 'pointer' }}
            onClick={() =>
              setEditing({
                target: note.target,
                existing: note,
                snapshot: note.filterSnapshot,
              })
            }
          >
            <div className="n-head">
              <span aria-hidden>{note.target.type === 'edge' ? '↝' : '⬭'}</span>
              <strong>{noteTargetLabel(note.target)}</strong>
              <ImportanceBadge level={normalizeImportance(note.importance)} />
              {note.resolved && (
                <span
                  title="Resolved"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 3,
                    padding: '1px 7px',
                    borderRadius: 999,
                    fontSize: 11,
                    fontWeight: 600,
                    color: 'var(--green)',
                    background: 'rgba(48,209,88,0.16)',
                  }}
                >
                  ✓ Resolved
                </span>
              )}
              <span className="spacer" />
              {note.isShared && <span title="Shared with other users">👥</span>}
              <span>{note.authorName || note.username || '—'}</span>
              <span>{formatDateTime(note.createdAt)}</span>
            </div>
            <div className="n-text">{note.text}</div>
            <div className="n-meta">{snapshotSummary(note.filterSnapshot)}</div>
          </button>
        ))}
      </div>

      {notes.length > 0 && (
        <div
          className="row"
          style={{
            padding: '8px 16px',
            gap: 10,
            alignItems: 'center',
            background: 'var(--bg-tertiary-grouped)',
            borderTop: '1px solid var(--separator-soft)',
          }}
        >
          <button
            className="btn small"
            disabled={safePage === 0}
            onClick={() => setPage(safePage - 1)}
          >
            ‹ Prev
          </button>
          <span className="t-caption fg-secondary">
            Page {safePage + 1} of {pageCount}
          </span>
          <button
            className="btn small"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(safePage + 1)}
          >
            Next ›
          </button>
          <span className="spacer" />
          <span className="t-caption fg-secondary">
            {firstShown}–{lastShown} of {notes.length}
          </span>
        </div>
      )}

      {editing && <NoteEditorSheet item={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}
