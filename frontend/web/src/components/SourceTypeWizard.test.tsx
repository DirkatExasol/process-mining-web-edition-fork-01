import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    parseDetect: vi.fn(async () => ({
      fields: [{ name: 'timestamp', role: 'timestamp', regex: '(\\d{4}-\\d{2}-\\d{2})' }],
    })),
    parseSegment: vi.fn(async () => ({ regex: '(x)', value: 'x' })),
    createSourceType: vi.fn(async () => ({})),
    updateSourceType: vi.fn(async () => ({})),
  },
}))

import { api } from '../api'
import { SourceTypeWizard } from './SourceTypeWizard'

afterEach(() => vi.clearAllMocks())

describe('SourceTypeWizard', () => {
  it('auto-detects fields and posts the spec on save', async () => {
    const onSaved = vi.fn()
    render(<SourceTypeWizard onClose={() => {}} onSaved={onSaved} />)

    // Step 1: name + sample (auto-detect is the default) → Next
    fireEvent.change(screen.getByPlaceholderText(/Apache access log/i), {
      target: { value: 'App JSON log' },
    })
    fireEvent.change(screen.getByPlaceholderText(/OrderReceived/i), {
      target: { value: '2026-08-03 INFO Started' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))

    // Auto-detect ran and produced a field row.
    await waitFor(() => expect(api.parseDetect).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/matches: 2026-08-03/)).toBeTruthy())

    // Step 2 → review → save
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
    fireEvent.click(screen.getByRole('button', { name: /Create source type/i }))

    await waitFor(() => expect(api.createSourceType).toHaveBeenCalled())
    const body = (api.createSourceType as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(body.name).toBe('App JSON log')
    expect(body.sample).toBe('2026-08-03 INFO Started')
    expect(body.fields[0]).toMatchObject({ role: 'timestamp' })
    expect(onSaved).toHaveBeenCalled()
  })
})
