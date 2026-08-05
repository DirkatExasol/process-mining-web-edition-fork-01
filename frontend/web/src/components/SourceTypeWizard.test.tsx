import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    parseSegment: vi.fn(async () => ({ regex: '(x)', value: 'x' })),
    parseTimestamp: vi.fn(async () => ({ format: '%Y-%m-%d', normalized: '2026-08-03 00:00:00' })),
    createSourceType: vi.fn(async () => ({})),
    updateSourceType: vi.fn(async () => ({})),
  },
}))

import { api } from '../api'
import { SourceTypeWizard } from './SourceTypeWizard'

afterEach(() => vi.clearAllMocks())

describe('SourceTypeWizard', () => {
  it('maps a field manually and posts the spec on save', async () => {
    const onSaved = vi.fn()
    render(<SourceTypeWizard onClose={() => {}} onSaved={onSaved} />)

    // Step 1: name + sample → Next (no auto-detect option anymore).
    fireEvent.change(screen.getByPlaceholderText(/Apache access log/i), {
      target: { value: 'App JSON log' },
    })
    fireEvent.change(screen.getByPlaceholderText(/OrderReceived/i), {
      target: { value: '2026-08-03 INFO Started' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))

    // Step 2 opens with the Timestamp tab active; add a field and type its regex.
    fireEvent.click(screen.getByRole('button', { name: /Add field/i }))
    fireEvent.change(screen.getByPlaceholderText(/one capture group/i), {
      target: { value: '(\\d{4}-\\d{2}-\\d{2})' },
    })

    // The regex matches the sample and the timestamp is normalised for the preview.
    await waitFor(() => expect(screen.getByText(/matches: 2026-08-03/)).toBeTruthy())
    expect(screen.getByText(/Example JOURNEYS record/)).toBeTruthy()
    await waitFor(() => expect(screen.getByText('2026-08-03 00:00:00')).toBeTruthy())

    // Step 2 → review → save.
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
    fireEvent.click(screen.getByRole('button', { name: /Create source type/i }))

    await waitFor(() => expect(api.createSourceType).toHaveBeenCalled())
    const body = (api.createSourceType as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(body.name).toBe('App JSON log')
    expect(body.sample).toBe('2026-08-03 INFO Started')
    expect(body.fields[0]).toMatchObject({ role: 'timestamp', regex: '(\\d{4}-\\d{2}-\\d{2})' })
    expect(onSaved).toHaveBeenCalled()
  })
})
