/** Notes list — port of `commentsContent` from ProcessMapView.swift. */

import { useMemo, useState } from 'react'
import {
  NoteEditorSheet,
  snapshotSummary,
  type NoteEditorTarget,
} from '../components/NoteEditor'
import { Unavailable } from '../components/ui'
import { formatDateTime } from '../graph/format'
import { useStore } from '../store'
import { noteTargetLabel } from '../types'

export function NotesView() {
  const store = useStore()
  const [editing, setEditing] = useState<NoteEditorTarget | null>(null)
  const [search, setSearch] = useState('')

  const notes = useMemo(() => {
    const term = search.trim().toLowerCase()
    return [...store.projectNotes]
      .filter(
        (n) =>
          !term ||
          n.text.toLowerCase().includes(term) ||
          noteTargetLabel(n.target).toLowerCase().includes(term),
      )
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  }, [store.projectNotes, search])

  if (store.projectNotes.length === 0) {
    return (
      <Unavailable
        glyph="🗒"
        title="No Notes"
        description="Click a node or an edge on the process map and choose “Show Notes” to add one."
      />
    )
  }

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      <div
        className="row"
        style={{
          padding: '8px 16px',
          gap: 12,
          background: 'var(--bg-tertiary-grouped)',
          borderBottom: '1px solid var(--separator-soft)',
        }}
      >
        <div className="search-row" style={{ flex: 1, maxWidth: 360 }}>
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
        <span className="t-caption fg-secondary">
          {notes.length} of {store.projectNotes.length}
        </span>
        <span className="spacer" />
        <button className="btn small" onClick={() => void store.loadNotes()}>
          ↻ Reload
        </button>
      </div>

      <div className="scroll-view">
        {notes.map((note) => (
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

      {editing && <NoteEditorSheet item={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}
