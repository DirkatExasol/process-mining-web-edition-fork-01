/** SourceTypeFilePicker — the source-type wizard's file chooser: list sandbox files,
 *  detect the data format (text / JSON / XML) and — for text — the record delimiter,
 *  preview records, and pick one by click or drag-and-drop. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const textStructure = {
  format: 'text' as const,
  delimiter: 'crlf',
  candidates: [
    { id: 'crlf', label: 'CRLF (\\r\\n) — Windows line ending', count: 4 },
    { id: 'lf', label: 'LF (\\n) — Unix newline', count: 0 },
  ],
  records: ['rec one', 'rec two', 'rec three'],
  fields: [],
  truncated: true,
  encoding: 'utf-8',
}

const jsonStructure = {
  format: 'json' as const,
  shape: 'array' as const,
  records: ['{\n  "caseId": "c1"\n}'],
  fields: [{ name: 'caseid', role: 'id' as const, path: 'caseId', sample: 'c1' }],
  truncated: false,
  encoding: 'utf-8',
}

vi.mock('../api', () => ({
  api: {
    listIntegrationFiles: vi.fn(async () => [
      { name: 'apache.log', size: 4863, modified: 0 },
      { name: 'events.json', size: 128, modified: 0 },
    ]),
    detectStructure: vi.fn(async (path: string) =>
      path === 'events.json' ? jsonStructure : textStructure,
    ),
    detectRecords: vi.fn(async (_path: string, delimiter = '') => ({
      ...textStructure,
      delimiter: delimiter || 'crlf',
    })),
  },
}))

import { api } from '../api'
import { SourceTypeFilePicker } from './SourceTypeFilePicker'

afterEach(() => vi.clearAllMocks())

function openAndPickFile(name = /apache\.log/i) {
  fireEvent.click(screen.getByRole('button', { name: /Choose a file/i }))
  return screen.findByRole('button', { name })
}

describe('SourceTypeFilePicker', () => {
  it('lists sandbox files and detects records on selection', async () => {
    render(<SourceTypeFilePicker selected="" onPick={() => {}} />)
    const fileBtn = await openAndPickFile()
    expect(screen.getByRole('button', { name: /events\.json/i })).toBeTruthy()

    fireEvent.click(fileBtn)
    await waitFor(() => expect(api.detectStructure).toHaveBeenCalledWith('apache.log', 5))
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

  it('picks a record by clicking it, handing back the detection', async () => {
    const onPick = vi.fn()
    render(<SourceTypeFilePicker selected="" onPick={onPick} />)
    fireEvent.click(await openAndPickFile())
    const rec = await screen.findByText('rec two')

    fireEvent.click(rec)
    expect(onPick).toHaveBeenCalledWith('rec two', expect.objectContaining({ format: 'text' }))
  })

  it('detects a JSON file: no delimiter selector, records shown', async () => {
    const onPick = vi.fn()
    render(<SourceTypeFilePicker selected="" onPick={onPick} />)
    fireEvent.click(await openAndPickFile(/events\.json/i))
    await waitFor(() => expect(api.detectStructure).toHaveBeenCalledWith('events.json', 5))
    // JSON: a format badge, no delimiter combobox.
    await waitFor(() => expect(screen.getByText(/Detected JSON/i)).toBeTruthy())
    expect(screen.queryByRole('combobox')).toBeNull()
    fireEvent.click(screen.getByText(/"caseId": "c1"/))
    expect(onPick).toHaveBeenCalledWith(expect.stringContaining('caseId'), expect.objectContaining({ format: 'json' }))
  })

  it('exposes the record on drag so it can be dropped into the example box', async () => {
    render(<SourceTypeFilePicker selected="" onPick={() => {}} />)
    fireEvent.click(await openAndPickFile())
    await screen.findByText('rec one')

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
    expect(screen.queryByText(/Drop a record here/i)).toBeNull()
    expect(screen.getAllByText('rec two')).toHaveLength(1)
    const card = screen.getByText('rec two').closest('.card') as HTMLElement
    expect(card.className).toContain('selected')
  })
})
