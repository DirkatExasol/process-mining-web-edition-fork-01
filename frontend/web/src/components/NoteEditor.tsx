/** Sticky-note editor and per-target note list — ports `NoteEditorSheet` and
 *  `NoteListSheet` from ProcessMapView.swift. */

import { useState } from 'react'
import { formatDateTime } from '../graph/format'
import { useStore } from '../store'
import {
  noteTargetLabel,
  type FilterSnapshot,
  type NoteTarget,
  type ProcessNote,
} from '../types'
import { ConfirmSheet, Divider, Sheet } from './ui'

export function snapshotSummary(snapshot: FilterSnapshot): string {
  const parts = [`${snapshot.fromDate?.slice(0, 10)} – ${snapshot.toDate?.slice(0, 10)}`]
  if (snapshot.includedSteps.length)
    parts.push(`include: ${snapshot.includedSteps.join(', ')}`)
  if (snapshot.excludedSteps.length)
    parts.push(`exclude: ${snapshot.excludedSteps.join(', ')}`)
  if (snapshot.meta1) parts.push(`M1: ${snapshot.meta1}`)
  if (snapshot.meta2) parts.push(`M2: ${snapshot.meta2}`)
  if (snapshot.meta3) parts.push(`M3: ${snapshot.meta3}`)
  return parts.join(' · ')
}

export interface NoteEditorTarget {
  target: NoteTarget
  existing: ProcessNote | null
  snapshot: FilterSnapshot
}

export function NoteEditorSheet({
  item,
  onClose,
}: {
  item: NoteEditorTarget
  onClose: () => void
}) {
  const store = useStore()
  const [text, setText] = useState(item.existing?.text ?? '')
  const [isShared, setIsShared] = useState(item.existing?.isShared ?? false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const save = async () => {
    const note: ProcessNote = item.existing
      ? { ...item.existing, text, isShared }
      : {
          id: crypto.randomUUID().toUpperCase(),
          text,
          createdAt: new Date().toISOString(),
          editedAt: null,
          target: item.target,
          filterSnapshot: item.snapshot,
          username: '',
          lastEditedBy: '',
          isShared,
        }
    await store.saveNote(note)
    onClose()
  }

  return (
    <>
      <Sheet
        title={item.existing ? 'Edit Note' : 'New Note'}
        icon="🗒"
        onClose={onClose}
        footer={
          <>
            {item.existing && (
              <button
                className="btn destructive"
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </button>
            )}
            <span className="spacer" />
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button className="btn prominent" disabled={!text.trim()} onClick={save}>
              Save
            </button>
          </>
        }
      >
        <div className="row t-caption fg-secondary" style={{ gap: 6 }}>
          <span aria-hidden>{item.target.type === 'edge' ? '↝' : '⬭'}</span>
          <strong>{noteTargetLabel(item.target)}</strong>
        </div>

        <textarea
          className="text-input"
          style={{ minHeight: 160 }}
          value={text}
          autoFocus
          placeholder="Your note…"
          onChange={(e) => setText(e.target.value)}
        />

        <label className="row t-callout" style={{ gap: 8 }}>
          <input
            type="checkbox"
            checked={isShared}
            onChange={(e) => setIsShared(e.target.checked)}
          />
          Share with other users of this database
        </label>

        <Divider />
        <div className="col t-caption2 fg-tertiary" style={{ gap: 2 }}>
          <span>Filter context: {snapshotSummary(item.snapshot)}</span>
          {item.existing && (
            <>
              <span>
                Created {formatDateTime(item.existing.createdAt)}
                {item.existing.authorName || item.existing.username
                  ? ` by ${item.existing.authorName || item.existing.username}`
                  : ''}
              </span>
              {item.existing.editedAt && (
                <span>
                  Edited {formatDateTime(item.existing.editedAt)}
                  {item.existing.lastEditedByName || item.existing.lastEditedBy
                    ? ` by ${
                        item.existing.lastEditedByName || item.existing.lastEditedBy
                      }`
                    : ''}
                </span>
              )}
            </>
          )}
        </div>
      </Sheet>

      {confirmDelete && item.existing && (
        <ConfirmSheet
          title="Delete this note?"
          message="This removes the note from the database for everyone who can see it."
          onCancel={() => setConfirmDelete(false)}
          onConfirm={async () => {
            await store.deleteNote(item.existing as ProcessNote)
            setConfirmDelete(false)
            onClose()
          }}
        />
      )}
    </>
  )
}

export function NoteListSheet({
  target,
  notes,
  snapshot,
  onClose,
}: {
  target: NoteTarget
  notes: ProcessNote[]
  snapshot: FilterSnapshot
  onClose: () => void
}) {
  const [editing, setEditing] = useState<NoteEditorTarget | null>(null)

  return (
    <>
      <Sheet
        title={`Notes — ${noteTargetLabel(target)}`}
        icon="🗒"
        onClose={onClose}
        footer={
          <>
            <button
              className="btn prominent"
              onClick={() => setEditing({ target, existing: null, snapshot })}
            >
              ＋ New note
            </button>
            <button className="btn" onClick={onClose}>
              Close
            </button>
          </>
        }
      >
        {notes.map((note) => (
          <button
            key={note.id}
            className="note-card"
            style={{ textAlign: 'left', cursor: 'pointer' }}
            onClick={() =>
              setEditing({ target, existing: note, snapshot: note.filterSnapshot })
            }
          >
            <div className="n-head">
              <span>{note.authorName || note.username || '—'}</span>
              <span className="spacer" />
              {note.isShared && <span title="Shared">👥</span>}
              <span>{formatDateTime(note.createdAt)}</span>
            </div>
            <div className="n-text">{note.text}</div>
            <div className="n-meta">{snapshotSummary(note.filterSnapshot)}</div>
          </button>
        ))}
      </Sheet>

      {editing && <NoteEditorSheet item={editing} onClose={() => setEditing(null)} />}
    </>
  )
}
