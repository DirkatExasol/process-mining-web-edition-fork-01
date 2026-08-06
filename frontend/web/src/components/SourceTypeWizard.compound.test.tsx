/** A field referenced by a compound rule is locked against deletion, and renaming it
 *  carries the reference into the rules instead of orphaning them. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    parseSegment: vi.fn(async () => ({ regex: '(x)', value: 'x' })),
    parseTimestamp: vi.fn(async () => ({ format: '%Y', normalized: '2026-01-01 00:00:00' })),
    createSourceType: vi.fn(async () => ({})),
    updateSourceType: vi.fn(async () => ({})),
  },
}))

import { api } from '../api'
import { SourceTypeWizard } from './SourceTypeWizard'
import type { SourceType } from '../types'

/** A saved source type whose rule references the "status" helper field. */
const EXISTING = {
  id: 'st1', owner: 'dev', name: 'Apache', createdAt: '',
  sample: 'POST /shop/login?userId=1 HTTP/1.1" 200',
  fields: [
    { id: 'f1', name: 'step', role: 'step', regex: '/shop/([a-z]+)' },
    { id: 'f2', name: 'status', role: 'aux', regex: 'HTTP/1\\.1" (\\d{3})' },
  ],
  compound: [
    { id: 'c1', step: 'login successful', when: [{ field: 'status', op: 'eq', value: '200' }] },
  ],
} as unknown as SourceType

const helperRow = () =>
  screen.getByDisplayValue('status').closest('.field-row') as HTMLElement

/** Open the wizard on the mapping step, with the Helper tab active. */
function openOnHelperTab() {
  render(<SourceTypeWizard existing={EXISTING} onClose={() => {}} onSaved={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
  fireEvent.click(screen.getByRole('button', { name: /Helper/i }))
}

afterEach(() => vi.clearAllMocks())

describe('a field used by a compound rule', () => {
  it('is locked instead of deletable, and names the rule', () => {
    openOnHelperTab()
    const row = helperRow()

    expect(within(row).queryByLabelText(/Remove field/i)).toBeNull()
    const lock = within(row).getByLabelText(/Locked — used by 1 compound rule/i)
    expect(lock.textContent).toContain('🔒')
    // The consequence is stated in the row itself, not only in a tooltip.
    expect(within(row).getByText(/Used by 1 compound rule/i).textContent)
      .toContain('login successful')
  })

  it('renaming it carries the rule reference along', async () => {
    openOnHelperTab()
    fireEvent.change(within(helperRow()).getByDisplayValue('status'), {
      target: { value: 'httpStatus' },
    })

    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
    fireEvent.click(screen.getByRole('button', { name: /Save changes/i }))

    await waitFor(() => expect(api.updateSourceType).toHaveBeenCalled())
    const body = (api.updateSourceType as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1]
    // The rule now points at the new name — not the old, now-nonexistent one.
    expect(body.compound[0].when[0].field).toBe('httpStatus')
    expect(body.fields.find((f: { role: string }) => f.role === 'aux').name).toBe('httpStatus')
  })

  it('an unreferenced field stays deletable', () => {
    render(<SourceTypeWizard existing={EXISTING} onClose={() => {}} onSaved={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /^Next$/ }))
    fireEvent.click(screen.getByRole('button', { name: /STEP/ }))
    // The STEP field is not referenced by the rule above.
    const row = screen.getByDisplayValue('/shop/([a-z]+)').closest('.field-row') as HTMLElement
    expect(within(row).getByLabelText(/Remove field/i)).toBeTruthy()
  })
})
