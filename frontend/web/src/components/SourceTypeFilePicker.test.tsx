/** SourceTypeFilePicker — the source-type wizard's file chooser: list sandbox files,
 *  detect the record delimiter, preview records, and pick one by click or drag-and-drop. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    listIntegrationFiles: vi.fn(async () => [
      { name: 'apache.log', size: 4863, modified: 0 },
      { name: 'sub/app.log', size: 128, modified: 0 },
    ]),
    detectRecords: vi.fn(async (_path: string, delimiter = '') => ({
      delimiter: delimiter || 'crlf',
      candidates: [
        { id: 'crlf', label: 'CRLF (\\r\\n) — Windows line ending', count: 4 },
        { id: 'lf', label: 'LF (\\n) — Unix newline', count: 0 },
      ],
      records: ['rec one', 'rec two', 'rec three'],
      truncated: true,
      encoding: 'utf-8',
    })),
  },
}))

import { api } from '../api'
import { SourceTypeFilePicker } from './SourceTypeFilePicker'

afterEach(() => vi.clearAllMocks())

function openAndPickFile() {
  fireEvent.click(screen.getByRole('button', { name: /Choose a file/i }))
  return screen.findByRole('button', { name: /apache\.log/i })
}

describe('SourceTypeFilePicker', () => {
  it('lists sandbox files and detects records on selection', async () => {
    render(<SourceTypeFilePicker selected="" onPick={() => {}} />)
    const fileBtn = await openAndPickFile()
    expect(screen.getByRole('button', { name: /sub\/app\.log/i })).toBeTruthy()

    fireEvent.click(fileBtn)
    await waitFor(() => expect(api.detectRecords).toHaveBeenCalledWith('apache.log', '', 5))
    // The detected delimiter and the record previews appear.
    await waitFor(() => expect(screen.getByText(/CRLF/)).toBeTruthy())
    expect(screen.getByText('rec one')).toBeTruthy()
    expect(screen.getByText('rec three')).toBeTruthy()
  })

  it('re-detects when the delimiter is changed', async () => {
    render(<SourceTypeFilePicker selected="" onPick={() => {}} />)
    fireEvent.click(await openAndPickFile())
    await waitFor(() => expect(screen.getByText('rec one')).toBeTruthy())

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'lf' } })
    await waitFor(() => expect(api.detectRecords).toHaveBeenCalledWith('apache.log', 'lf', 5))
  })

  it('picks a record by clicking it', async () => {
    const onPick = vi.fn()
    render(<SourceTypeFilePicker selected="" onPick={onPick} />)
    fireEvent.click(await openAndPickFile())
    const rec = await screen.findByText('rec two')

    fireEvent.click(rec)
    expect(onPick).toHaveBeenCalledWith('rec two')
  })

  it('exposes the record on drag so it can be dropped into the example box', async () => {
    render(<SourceTypeFilePicker selected="" onPick={() => {}} />)
    fireEvent.click(await openAndPickFile())
    await screen.findByText('rec one')

    // Dragging a card puts the record on the dataTransfer; the wizard's example textarea
    // is the drop target (tested there). Here we just assert the card is draggable and
    // carries the record.
    const store: Record<string, string> = {}
    const dataTransfer = {
      setData: (k: string, v: string) => { store[k] = v },
      getData: (k: string) => store[k] ?? '',
      effectAllowed: '',
      dropEffect: '',
    }
    const card = screen.getByText('rec three').closest('[role="button"]') as HTMLElement
    expect(card.getAttribute('draggable')).toBe('true')
    fireEvent.dragStart(card, { dataTransfer })
    expect(store['text/plain']).toBe('rec three')
  })

  it('highlights the selected card and does not render a separate drop box', async () => {
    render(<SourceTypeFilePicker selected="rec two" onPick={() => {}} />)
    fireEvent.click(await openAndPickFile())
    await screen.findByText('rec one')
    // No redundant drop box — selection is shown only by the highlighted card.
    expect(screen.queryByText(/Drop a record here/i)).toBeNull()
    expect(screen.queryByText(/Record selected/i)).toBeNull()
    // "rec two" appears exactly once — the highlighted card.
    expect(screen.getAllByText('rec two')).toHaveLength(1)
    const card = screen.getByText('rec two').closest('.card') as HTMLElement
    expect(card.className).toContain('selected')
  })
})
