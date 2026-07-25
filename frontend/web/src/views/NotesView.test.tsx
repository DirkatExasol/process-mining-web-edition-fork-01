/** NotesView tests — the notes overview badge (author + importance) and the
 *  importance / user / time filters. */

import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'

import { useStore } from '../store'
import type { FilterSnapshot, ProcessNote } from '../types'
import { NotesView } from './NotesView'

const SNAPSHOT = {
  fromDate: '2026-01-01',
  toDate: '2026-02-01',
  includedSteps: [],
  excludedSteps: [],
  meta1: '',
  meta2: '',
  meta3: '',
} as unknown as FilterSnapshot

function note(overrides: Partial<ProcessNote>): ProcessNote {
  return {
    id: 'n1',
    text: 'A note',
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

/** The scroll-view holding the note cards (excludes the toolbar/dropdowns). */
function noteList() {
  return document.querySelector('.scroll-view') as HTMLElement
}

beforeEach(() => {
  useStore.setState({ projectNotes: [] })
})

describe('NotesView author badge', () => {
  it('shows the resolved real name (authorName) when present', () => {
    useStore.setState({
      projectNotes: [note({ authorName: 'John Smith', username: 'jsmith' })],
    })
    render(<NotesView />)
    expect(within(noteList()).getByText('John Smith')).toBeTruthy()
    expect(within(noteList()).queryByText('jsmith')).toBeNull()
  })

  it('falls back to the login username when no real name is resolved', () => {
    useStore.setState({
      projectNotes: [note({ authorName: '', username: 'jsmith' })],
    })
    render(<NotesView />)
    expect(within(noteList()).getByText('jsmith')).toBeTruthy()
  })
})

describe('NotesView importance', () => {
  it('shows an importance badge for non-normal notes only', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', importance: 'URGENT', text: 'urgent one' }),
        note({ id: 'b', importance: 'NORMAL', text: 'normal one' }),
      ],
    })
    render(<NotesView />)
    expect(screen.getByTitle('Importance: Urgent')).toBeTruthy()
    expect(screen.queryByTitle('Importance: Normal')).toBeNull()
  })

  it('filters the list by importance', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', importance: 'URGENT', text: 'urgent one' }),
        note({ id: 'b', importance: 'NORMAL', text: 'normal one' }),
      ],
    })
    render(<NotesView />)
    const list = noteList()
    expect(within(list).getByText('urgent one')).toBeTruthy()
    expect(within(list).getByText('normal one')).toBeTruthy()

    const [importanceSelect] = screen.getAllByRole('combobox')
    fireEvent.change(importanceSelect, { target: { value: 'URGENT' } })
    expect(within(noteList()).getByText('urgent one')).toBeTruthy()
    expect(within(noteList()).queryByText('normal one')).toBeNull()
  })
})

describe('NotesView resolved status', () => {
  it('shows a Resolved indicator on resolved notes', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', resolved: true, text: 'done one' }),
        note({ id: 'b', resolved: false, text: 'open one' }),
      ],
    })
    render(<NotesView />)
    expect(within(noteList()).getByText('✓ Resolved')).toBeTruthy()
    // Only the resolved note carries the indicator.
    expect(within(noteList()).getAllByText('✓ Resolved')).toHaveLength(1)
  })

  it('filters by resolved status', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', resolved: true, text: 'done one' }),
        note({ id: 'b', resolved: false, text: 'open one' }),
      ],
    })
    render(<NotesView />)
    const statusSelect = screen.getAllByRole('combobox')[3] // [imp, user, time, status]
    fireEvent.change(statusSelect, { target: { value: 'RESOLVED' } })
    const list = noteList()
    expect(within(list).getByText('done one')).toBeTruthy()
    expect(within(list).queryByText('open one')).toBeNull()
  })
})

describe('NotesView pagination', () => {
  it('pages the list and resizes with the per-page control', () => {
    const many = Array.from({ length: 12 }, (_, i) =>
      note({
        id: `n${i}`,
        text: `note ${i}`,
        createdAt: `2026-07-${String(i + 1).padStart(2, '0')}T00:00:00`,
      }),
    )
    useStore.setState({ projectNotes: many })
    render(<NotesView />)

    const cardCount = () => noteList().querySelectorAll('.note-card').length
    expect(cardCount()).toBe(10) // default page size
    expect(screen.getByText('Page 1 of 2')).toBeTruthy()
    expect(screen.getByText(/1.10 of 12/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(cardCount()).toBe(2)
    expect(screen.getByText('Page 2 of 2')).toBeTruthy()

    // Resizing to 5/page resets back to the first page.
    const perPage = screen.getAllByRole('combobox')[4] // [imp, user, time, status, perPage]
    fireEvent.change(perPage, { target: { value: '5' } })
    expect(cardCount()).toBe(5)
    expect(screen.getByText('Page 1 of 3')).toBeTruthy()
  })
})

describe('NotesView user filter', () => {
  it('filters the list by note author', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', username: 'alice', authorName: 'Alice A', text: 'by alice' }),
        note({ id: 'b', username: 'bob', authorName: 'Bob B', text: 'by bob' }),
      ],
    })
    render(<NotesView />)
    const userSelect = screen.getAllByRole('combobox')[1] // [importance, user, time]
    fireEvent.change(userSelect, { target: { value: 'bob' } })
    const list = noteList()
    expect(within(list).getByText('by bob')).toBeTruthy()
    expect(within(list).queryByText('by alice')).toBeNull()
  })
})
