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
    title: 'A title',
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

describe('NotesView title', () => {
  it('shows the note title as a separate heading', () => {
    useStore.setState({
      projectNotes: [note({ title: 'Bottleneck here', text: 'body text' })],
    })
    render(<NotesView />)
    expect(within(noteList()).getByText('Bottleneck here')).toBeTruthy()
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

    const importanceSelect = screen.getByRole('combobox', { name: /Importance/ })
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
    const statusSelect = screen.getByRole('combobox', { name: /Status/ })
    fireEvent.change(statusSelect, { target: { value: 'RESOLVED' } })
    const list = noteList()
    expect(within(list).getByText('done one')).toBeTruthy()
    expect(within(list).queryByText('open one')).toBeNull()
  })
})

describe('NotesView type filter', () => {
  it('filters by note target type (node vs edge)', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', text: 'node note', target: { type: 'node', value: 'STEP_A' } }),
        note({ id: 'b', text: 'edge note', target: { type: 'edge', from: 'A', to: 'B' } }),
      ],
    })
    render(<NotesView />)
    const type = screen.getByRole('combobox', { name: /Type/ })
    fireEvent.change(type, { target: { value: 'edge' } })
    const list = noteList()
    expect(within(list).getByText('edge note')).toBeTruthy()
    expect(within(list).queryByText('node note')).toBeNull()
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
    expect(cardCount()).toBe(5) // default page size
    expect(screen.getByText('Page 1 of 3')).toBeTruthy()
    expect(screen.getByText(/1.5 of 12/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(cardCount()).toBe(5)
    expect(screen.getByText('Page 2 of 3')).toBeTruthy()

    // Resizing to 20/page shows them all and resets to the first page.
    const perPage = screen.getByRole('combobox', { name: /Per page/ })
    fireEvent.change(perPage, { target: { value: '20' } })
    expect(cardCount()).toBe(12)
    expect(screen.getByText('Page 1 of 1')).toBeTruthy()
  })
})

describe('NotesView KPIs / sort / grouping', () => {
  it('shows a per-importance count in the KPI strip', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', importance: 'URGENT' }),
        note({ id: 'b', importance: 'URGENT' }),
        note({ id: 'c', importance: 'INFO' }),
      ],
    })
    render(<NotesView />)
    const strip = document.querySelector('.kpi-strip') as HTMLElement
    // The Urgent tile reads 2, the Info tile 1 (and Normal/Important 0).
    const urgent = within(strip).getByText('Urgent').closest('.kpi-tile') as HTMLElement
    expect(within(urgent).getByText('2')).toBeTruthy()
    const info = within(strip).getByText('Info').closest('.kpi-tile') as HTMLElement
    expect(within(info).getByText('1')).toBeTruthy()
  })

  it('shows Total and Resolved KPI counts', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', resolved: true }),
        note({ id: 'b', resolved: false }),
        note({ id: 'c', resolved: true }),
      ],
    })
    render(<NotesView />)
    const strip = document.querySelector('.kpi-strip') as HTMLElement
    const total = within(strip).getByText('Total Notes').closest('.kpi-tile') as HTMLElement
    expect(within(total).getByText('3')).toBeTruthy()
    const resolved = within(strip).getByText('Resolved').closest('.kpi-tile') as HTMLElement
    expect(within(resolved).getByText('2')).toBeTruthy()
  })

  it('sorts by date, newest or oldest first', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'old', text: 'older', createdAt: '2026-01-01T00:00:00' }),
        note({ id: 'new', text: 'newer', createdAt: '2026-06-01T00:00:00' }),
      ],
    })
    render(<NotesView />)
    const texts = () =>
      [...noteList().querySelectorAll('.n-text')].map((e) => e.textContent)
    expect(texts()).toEqual(['newer', 'older']) // newest first (default)

    const sort = screen.getByRole('combobox', { name: /Sort/ })
    fireEvent.change(sort, { target: { value: 'oldest' } })
    expect(texts()).toEqual(['older', 'newer'])
  })

  it('shows importance group headers when grouping is on', () => {
    useStore.setState({
      projectNotes: [
        note({ id: 'a', importance: 'NORMAL', text: 'plain' }),
        note({ id: 'b', importance: 'URGENT', text: 'urgent' }),
      ],
    })
    render(<NotesView />)
    expect(noteList().querySelector('.note-group-header')).toBeNull() // off by default

    fireEvent.click(screen.getByLabelText('Group by importance'))
    const headers = [...noteList().querySelectorAll('.note-group-header')].map(
      (e) => e.textContent,
    )
    // Highest importance group first.
    expect(headers[0]).toContain('Urgent')
    expect(headers.some((h) => h?.includes('Normal'))).toBe(true)
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
    const userSelect = screen.getByRole('combobox', { name: /User/ })
    fireEvent.change(userSelect, { target: { value: 'bob' } })
    const list = noteList()
    expect(within(list).getByText('by bob')).toBeTruthy()
    expect(within(list).queryByText('by alice')).toBeNull()
  })
})
