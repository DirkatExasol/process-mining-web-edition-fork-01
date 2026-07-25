/** NoteEditor tests — the threaded editor: anyone who can see a note may add a
 *  comment and toggle resolved, but only the author may change importance/sharing
 *  or delete it. History is read-only. */

import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { useStore } from '../store'
import type { FilterSnapshot, ProcessNote } from '../types'
import { NoteEditorSheet, type NoteEditorTarget } from './NoteEditor'

const SNAPSHOT = {
  fromDate: '2026-01-01',
  toDate: '2026-02-01',
  includedSteps: [],
  excludedSteps: [],
  meta1: '',
  meta2: '',
  meta3: '',
} as unknown as FilterSnapshot

function existingNote(username: string): ProcessNote {
  return {
    id: 'n1',
    text: 'original observation',
    createdAt: '2026-07-25T18:00:00',
    editedAt: null,
    target: { type: 'node', value: 'STEP_A' },
    filterSnapshot: SNAPSHOT,
    username,
    lastEditedBy: '',
    isShared: true,
    importance: 'NORMAL',
    resolved: false,
  }
}

function item(username: string): NoteEditorTarget {
  const note = existingNote(username)
  return { target: note.target, existing: note, snapshot: SNAPSHOT }
}

const btn = (name: string | RegExp) =>
  screen.getByRole('button', { name }) as HTMLButtonElement

beforeEach(() => {
  useStore.setState({ authUser: null })
})

describe('NoteEditor — author', () => {
  it('can delete and change importance', () => {
    useStore.setState({ authUser: 'alice' })
    render(<NoteEditorSheet item={item('alice')} onClose={() => {}} />)
    expect(screen.getByText('Delete')).toBeTruthy()
    expect(btn(/Urgent/).disabled).toBe(false) // importance selector enabled
  })
})

describe('NoteEditor — non-author', () => {
  it('cannot delete or change importance, but can add a comment', () => {
    useStore.setState({ authUser: 'bob' })
    render(<NoteEditorSheet item={item('alice')} onClose={() => {}} />)

    // No delete; importance selector locked.
    expect(screen.queryByText('Delete')).toBeNull()
    expect(btn(/Urgent/).disabled).toBe(true)

    // History is read-only.
    const history = screen.getByDisplayValue('original observation') as HTMLTextAreaElement
    expect(history.readOnly).toBe(true)

    // Save is disabled until a comment is typed, then enabled.
    const save = btn('Save')
    expect(save.disabled).toBe(true)
    fireEvent.change(screen.getByPlaceholderText('Add a note or comment…'), {
      target: { value: 'looks fixed to me' },
    })
    expect(save.disabled).toBe(false)
  })

  it('can toggle resolved even without a comment', () => {
    useStore.setState({ authUser: 'bob' })
    render(<NoteEditorSheet item={item('alice')} onClose={() => {}} />)
    const save = btn('Save')
    expect(save.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText(/Mark this note/))
    expect(save.disabled).toBe(false)
  })
})
