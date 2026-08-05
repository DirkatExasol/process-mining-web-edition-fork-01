import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    createSource: vi.fn(async () => ({})),
    updateSource: vi.fn(async () => ({})),
    listSourceTypes: vi.fn(async () => []),
    previewSource: vi.fn(async () => ({ lines: ['line one', 'line two'], truncated: true })),
  },
}))

import { api } from '../api'
import { SourceWizard } from './SourceWizard'

afterEach(() => vi.clearAllMocks())

describe('SourceWizard', () => {
  it('creates a File source with its config', async () => {
    const onSaved = vi.fn()
    render(<SourceWizard onClose={() => {}} onSaved={onSaved} />)

    // Step 1: File is preselected → Next
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))

    // Step 2: name + the file path field
    fireEvent.change(screen.getByPlaceholderText(/access log/i), {
      target: { value: 'Access log' },
    })
    fireEvent.change(screen.getByPlaceholderText(/\/var\/log/i), {
      target: { value: '/data/logs/access.log' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))

    // Step 3: review → create
    fireEvent.click(screen.getByRole('button', { name: /Create source/i }))

    await waitFor(() => expect(api.createSource).toHaveBeenCalled())
    const body = (api.createSource as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]
    expect(body).toMatchObject({ name: 'Access log', kind: 'file' })
    expect(body.config.path).toBe('/data/logs/access.log')
    expect(onSaved).toHaveBeenCalled()
  })

  it('lists future kinds as coming soon', () => {
    render(<SourceWizard onClose={() => {}} onSaved={() => {}} />)
    expect(screen.getAllByText(/coming soon/i).length).toBeGreaterThan(0)
  })
})
