/** Shared node/edge note plumbing — ports `handleNodeNoteEdit` /
 *  `handleEdgeNoteEdit` from ProcessMapView.swift.
 *
 * Zero existing notes opens the editor to create one; one or more open the list
 * sheet, which shows every note for the target plus a "New note" button — so a node
 * or edge can carry more than one note. */

import { useCallback, useState, type ReactNode } from 'react'
import {
  NoteEditorSheet,
  NoteListSheet,
  type NoteEditorTarget,
} from '../components/NoteEditor'
import { useStore } from '../store'
import type { NoteTarget, ProcessNote, ProcessTransition } from '../types'

function notesForTarget(notes: ProcessNote[], target: NoteTarget): ProcessNote[] {
  return notes.filter((n) =>
    target.type === 'edge'
      ? n.target.type === 'edge' &&
        n.target.from === target.from &&
        n.target.to === target.to
      : n.target.type === 'node' && n.target.value === target.value,
  )
}

export function useNoteHandlers(): {
  openNodeNotes: (node: string) => void
  openEdgeNotes: (transition: ProcessTransition) => void
  element: ReactNode
} {
  const store = useStore()
  const [editor, setEditor] = useState<NoteEditorTarget | null>(null)
  const [listTarget, setListTarget] = useState<NoteTarget | null>(null)

  const open = useCallback(
    (target: NoteTarget) => {
      if (notesForTarget(store.projectNotes, target).length === 0) {
        // Nothing yet — go straight to creating the first note.
        setEditor({ target, existing: null, snapshot: store.currentFilterSnapshot() })
      } else {
        // One or more — show the list (with a "New note" button) so the user can
        // read any existing note AND add another to the same node/edge.
        setListTarget(target)
      }
    },
    [store],
  )

  const openNodeNotes = useCallback(
    (node: string) => open({ type: 'node', value: node }),
    [open],
  )

  const openEdgeNotes = useCallback(
    (transition: ProcessTransition) =>
      open({ type: 'edge', from: transition.fromStep, to: transition.toStep }),
    [open],
  )

  // Derive the list's notes from the live store so adding a note refreshes it.
  const listNotes = listTarget
    ? notesForTarget(store.projectNotes, listTarget)
    : []

  const element = (
    <>
      {editor && <NoteEditorSheet item={editor} onClose={() => setEditor(null)} />}
      {listTarget && (
        <NoteListSheet
          target={listTarget}
          notes={listNotes}
          snapshot={store.currentFilterSnapshot()}
          onClose={() => setListTarget(null)}
        />
      )}
    </>
  )

  return { openNodeNotes, openEdgeNotes, element }
}
