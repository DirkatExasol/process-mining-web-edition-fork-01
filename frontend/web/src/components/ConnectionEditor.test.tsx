/** ConnectionEditor tests — the power-user connection form: it saves the entered
 *  fields through the store, and its Test result is coloured by outcome. */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const saveManagedConnection = vi.fn().mockResolvedValue({ ok: true, error: null })
const deleteManagedConnection = vi.fn().mockResolvedValue(true)
const testManagedConnection = vi.fn()

vi.mock('../store', () => ({
  useStore: () => ({
    assignableUsers: ['alice', 'bob'],
    saveManagedConnection,
    deleteManagedConnection,
    testManagedConnection,
  }),
}))

import { ConnectionEditor } from './ConnectionEditor'

beforeEach(() => vi.clearAllMocks())

describe('ConnectionEditor', () => {
  it('saves the entered database fields and closes', async () => {
    const onClose = vi.fn()
    render(<ConnectionEditor connection={null} onClose={onClose} />)

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Prod' } })
    fireEvent.change(screen.getByLabelText('Host'), { target: { value: 'db.local' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(saveManagedConnection).toHaveBeenCalled())
    expect(saveManagedConnection).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Prod', host: 'db.local' }),
    )
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('offers the assignable users as checkboxes', () => {
    render(<ConnectionEditor connection={null} onClose={() => {}} />)
    expect(screen.getByLabelText('alice')).toBeInTheDocument()
    expect(screen.getByLabelText('bob')).toBeInTheDocument()
  })

  it('shows a green Test result when both database and LLM are OK', async () => {
    testManagedConnection.mockResolvedValue({ dbError: null, llmError: null, llmModels: [] })
    render(<ConnectionEditor connection={null} onClose={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Test' }))

    const result = await screen.findByText(/Database OK/)
    expect(result.style.color).toContain('var(--green)')
  })

  it('shows a red Test result when the database probe fails (no LLM configured)', async () => {
    testManagedConnection.mockResolvedValue({
      dbError: 'refused',
      llmError: null,
      llmModels: [],
    })
    render(<ConnectionEditor connection={null} onClose={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Test' }))

    const result = await screen.findByText(/Database: refused/)
    expect(result.style.color).toContain('var(--red)')
  })
})
