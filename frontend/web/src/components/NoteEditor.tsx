/** Sticky-note editor and per-target note list — ports `NoteEditorSheet` and
 *  `NoteListSheet` from ProcessMapView.swift. */

import { useState } from 'react'
import { formatDateTime } from '../graph/format'
import { useStore } from '../store'
import {
  noteTargetLabel,
  NOTE_IMPORTANCE_LEVELS,
  NOTE_IMPORTANCE_META,
  normalizeImportance,
  type FilterSnapshot,
  type NoteImportance,
  type NoteTarget,
  type ProcessNote,
} from '../types'
import { ConfirmSheet, Divider, Sheet } from './ui'

/** A pill badge for a note's importance. Renders nothing for the default NORMAL. */
export function ImportanceBadge({ level }: { level: NoteImportance }) {
  if (level === 'NORMAL') return null
  const m = NOTE_IMPORTANCE_META[level]
  return (
    <span
      title={`Importance: ${m.label}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        padding: '1px 7px',
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 600,
        color: m.color,
        background: m.bg,
        whiteSpace: 'nowrap',
      }}
    >
      <span aria-hidden>{m.glyph}</span>
      {m.label}
    </span>
  )
}

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
  const existing = item.existing
  const isNew = !existing

  // For a new note `draft` is the initial text; for an existing note it is the
  // comment to append to the thread (the history above is read-only).
  const [draft, setDraft] = useState('')
  const [isShared, setIsShared] = useState(existing?.isShared ?? false)
  const [importance, setImportance] = useState<NoteImportance>(
    normalizeImportance(existing?.importance),
  )
  const [resolved, setResolved] = useState(existing?.resolved ?? false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)

  // Anyone who can see a note may add a comment and toggle resolved; only the
  // author may change importance/sharing or delete it. A new note is the caller's.
  const currentUser = (store.authUser ?? '').toUpperCase()
  const isOwner = isNew || currentUser === (existing?.username ?? '').toUpperCase()

  const changed =
    draft.trim() !== '' ||
    (!isNew &&
      (resolved !== (existing?.resolved ?? false) ||
        (isOwner &&
          (importance !== normalizeImportance(existing?.importance) ||
            isShared !== (existing?.isShared ?? false)))))
  const canSave = isNew ? draft.trim() !== '' : changed

  const save = async () => {
    if (busy || !canSave) return
    setBusy(true)
    try {
      if (isNew) {
        await store.saveNote({
          id: crypto.randomUUID().toUpperCase(),
          text: draft,
          createdAt: new Date().toISOString(),
          editedAt: null,
          target: item.target,
          filterSnapshot: item.snapshot,
          username: '',
          lastEditedBy: '',
          isShared,
          importance,
          resolved: false,
        })
      } else {
        const body: {
          comment?: string
          resolved?: boolean
          importance?: string
          isShared?: boolean
        } = { resolved }
        if (draft.trim()) body.comment = draft.trim()
        if (isOwner) {
          body.importance = importance
          body.isShared = isShared
        }
        await store.updateNote(existing!.id, body)
      }
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Sheet
        title={isNew ? 'New Note' : 'Note'}
        icon="🗒"
        onClose={onClose}
        footer={
          <>
            {!isNew && isOwner && (
              <button
                className="btn destructive"
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </button>
            )}
            <span className="spacer" />
            <button className="btn" onClick={onClose}>
              {canSave ? 'Cancel' : 'Close'}
            </button>
            <button
              className="btn prominent"
              disabled={!canSave || busy}
              onClick={save}
            >
              Save
            </button>
          </>
        }
      >
        <div
          className="row t-caption fg-secondary"
          style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}
        >
          <span aria-hidden>{item.target.type === 'edge' ? '↝' : '⬭'}</span>
          <strong>{noteTargetLabel(item.target)}</strong>
          {!isNew && <ImportanceBadge level={importance} />}
          {!isNew && resolved && (
            <span title="Resolved" style={{ color: 'var(--green)', fontWeight: 600 }}>
              ✓ Resolved
            </span>
          )}
        </div>

        {!isNew && (
          <div className="col" style={{ gap: 4 }}>
            <span className="t-caption fg-secondary">Notes &amp; comments so far</span>
            <textarea
              className="text-input"
              style={{ minHeight: 180, resize: 'vertical' }}
              value={existing!.text}
              readOnly
            />
          </div>
        )}

        <div className="col" style={{ gap: 4 }}>
          <span className="t-caption fg-secondary">
            {isNew ? 'Note' : 'Add a comment'}
          </span>
          <textarea
            className="text-input"
            style={{ minHeight: isNew ? 160 : 84 }}
            value={draft}
            autoFocus
            placeholder={isNew ? 'Your note…' : 'Add a note or comment…'}
            onChange={(e) => setDraft(e.target.value)}
          />
        </div>

        {!isNew && (
          <label className="row t-callout" style={{ gap: 8 }}>
            <input
              type="checkbox"
              checked={resolved}
              onChange={(e) => setResolved(e.target.checked)}
            />
            Mark this note / issue as resolved
          </label>
        )}

        <div className="col" style={{ gap: 6 }}>
          <span className="t-caption fg-secondary">
            Importance{!isNew && !isOwner ? ' (set by the author)' : ''}
          </span>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            {NOTE_IMPORTANCE_LEVELS.map((lvl) => {
              const m = NOTE_IMPORTANCE_META[lvl]
              const active = importance === lvl
              return (
                <button
                  key={lvl}
                  type="button"
                  className="btn small"
                  disabled={!isOwner}
                  onClick={() => setImportance(lvl)}
                  style={{
                    borderColor: active ? m.color : undefined,
                    color: active ? m.color : undefined,
                    background: active ? m.bg : undefined,
                    fontWeight: active ? 700 : undefined,
                  }}
                >
                  {m.glyph} {m.label}
                </button>
              )
            })}
          </div>
        </div>

        <label className="row t-callout" style={{ gap: 8 }}>
          <input
            type="checkbox"
            checked={isShared}
            disabled={!isOwner}
            onChange={(e) => setIsShared(e.target.checked)}
          />
          Share with other users of this database
        </label>

        <Divider />
        <div className="col t-caption2 fg-tertiary" style={{ gap: 2 }}>
          <span>Filter context: {snapshotSummary(item.snapshot)}</span>
          {existing && (
            <>
              <span>
                Created {formatDateTime(existing.createdAt)}
                {existing.authorName || existing.username
                  ? ` by ${existing.authorName || existing.username}`
                  : ''}
              </span>
              {existing.editedAt && (
                <span>
                  Last activity {formatDateTime(existing.editedAt)}
                  {existing.lastEditedByName || existing.lastEditedBy
                    ? ` by ${existing.lastEditedByName || existing.lastEditedBy}`
                    : ''}
                </span>
              )}
            </>
          )}
        </div>
      </Sheet>

      {confirmDelete && existing && (
        <ConfirmSheet
          title="Delete this note?"
          message="This removes the note and its whole comment thread from the database for everyone who can see it."
          onCancel={() => setConfirmDelete(false)}
          onConfirm={async () => {
            await store.deleteNote(existing)
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
              <ImportanceBadge level={normalizeImportance(note.importance)} />
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
