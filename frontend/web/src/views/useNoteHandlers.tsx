/** Shared node/edge note plumbing — ports `handleNodeNoteEdit` /
 *  `handleEdgeNoteEdit` from ProcessMapView.swift.
 *
 * Zero existing notes opens the editor, one opens it pre-filled, several open
 * the list sheet. */

import { useCallback, useState, type ReactNode } from 'react'
import {
  NoteEditorSheet,
  NoteListSheet,
  type NoteEditorTarget,
} from '../components/NoteEditor'
import { useStore } from '../store'
import type { NoteTarget, ProcessNote, ProcessTransition } from '../types'

interface NoteListState {
  target: NoteTarget
  notes: ProcessNote[]
}

export function useNoteHandlers(): {
  openNodeNotes: (node: string) => void
  openEdgeNotes: (transition: ProcessTransition) => void
  element: ReactNode
} {
  const store = useStore()
  const [editor, setEditor] = useState<NoteEditorTarget | null>(null)
  const [list, setList] = useState<NoteListState | null>(null)

  const open = useCallback(
    (target: NoteTarget, matching: ProcessNote[]) => {
      const snapshot = store.currentFilterSnapshot()
      if (matching.length === 0) {
        setEditor({ target, existing: null, snapshot })
      } else if (matching.length === 1) {
        setEditor({
          target,
          existing: matching[0],
          snapshot: matching[0].filterSnapshot,
        })
      } else {
        setList({ target, notes: matching })
      }
    },
    [store],
  )

  const openNodeNotes = useCallback(
    (node: string) => {
      const matching = store.projectNotes.filter(
        (n) => n.target.type === 'node' && n.target.value === node,
      )
      open({ type: 'node', value: node }, matching)
    },
    [open, store.projectNotes],
  )

  const openEdgeNotes = useCallback(
    (transition: ProcessTransition) => {
      const matching = store.projectNotes.filter(
        (n) =>
          n.target.type === 'edge' &&
          n.target.from === transition.fromStep &&
          n.target.to === transition.toStep,
      )
      open(
        { type: 'edge', from: transition.fromStep, to: transition.toStep },
        matching,
      )
    },
    [open, store.projectNotes],
  )

  const element = (
    <>
      {editor && <NoteEditorSheet item={editor} onClose={() => setEditor(null)} />}
      {list && (
        <NoteListSheet
          target={list.target}
          notes={list.notes}
          snapshot={store.currentFilterSnapshot()}
          onClose={() => setList(null)}
        />
      )}
    </>
  )

  return { openNodeNotes, openEdgeNotes, element }
}
