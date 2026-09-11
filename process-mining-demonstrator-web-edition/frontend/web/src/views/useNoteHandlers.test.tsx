/** useNoteHandlers — a node/edge with one or more notes opens the list sheet (so a
 *  second note can be added); an empty target opens the editor to create the first. */

import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { useStore } from '../store'
import type { FilterSnapshot, ProcessNote } from '../types'
import { useNoteHandlers } from './useNoteHandlers'

const SNAPSHOT = {
  fromDate: '2026-01-01',
  toDate: '2026-02-01',
  includedSteps: [],
  excludedSteps: [],
  meta1: '',
  meta2: '',
  meta3: '',
} as unknown as FilterSnapshot

function nodeNote(overrides: Partial<ProcessNote>): ProcessNote {
  return {
    id: 'n1',
    title: 'T',
    text: 'body',
    createdAt: '2026-07-25T18:00:00',
    editedAt: null,
    target: { type: 'node', value: 'STEP_A' },
    filterSnapshot: SNAPSHOT,
    username: 'jsmith',
    lastEditedBy: '',
    isShared: false,
    importance: 'NORMAL',
    resolved: false,
    ...overrides,
  }
}

function Harness() {
  const h = useNoteHandlers()
  return (
    <>
      <button onClick={() => h.openNodeNotes('STEP_A')}>open</button>
      {h.element}
    </>
  )
}

beforeEach(() => {
  useStore.setState({ projectNotes: [], authUser: 'jsmith' })
})

describe('useNoteHandlers', () => {
  it('opens the list (with a New note button) when the node already has a note', () => {
    useStore.setState({ projectNotes: [nodeNote({ id: 'a' })] })
    render(<Harness />)
    fireEvent.click(screen.getByText('open'))
    // The list sheet — not the single-note editor — so another note can be added.
    expect(screen.getByText('＋ New note')).toBeTruthy()
  })

  it('opens the editor to create the first note on an empty node', () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('open'))
    expect(screen.getByText('New Note')).toBeTruthy() // editor sheet title
    expect(screen.queryByText('＋ New note')).toBeNull()
  })
})
