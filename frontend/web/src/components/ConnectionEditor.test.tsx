/** ConnectionEditor tests — the power-user connection form: it saves the entered
 *  fields through the store, and its Test result is coloured by outcome. */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const saveManagedConnection = vi.fn().mockResolvedValue({ ok: true, error: null })
const deleteManagedConnection = vi.fn().mockResolvedValue(true)
const testManagedConnection = vi.fn()
const provisionSchema = vi.fn()
const generateDemo = vi.fn()

vi.mock('../store', () => ({
  useStore: () => ({
    assignableUsers: ['alice', 'bob'],
    saveManagedConnection,
    deleteManagedConnection,
    testManagedConnection,
    provisionSchema,
    generateDemo,
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

  it('provisions the schema with the entered credentials and reports what was created', async () => {
    provisionSchema.mockResolvedValue({
      ok: true,
      error: null,
      created: ['schema PM', 'PROJECTS', 'NOTES'],
    })
    render(<ConnectionEditor connection={null} onClose={() => {}} />)

    fireEvent.change(screen.getByLabelText('Schema'), { target: { value: 'PM' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create schema & tables' }))

    await waitFor(() => expect(provisionSchema).toHaveBeenCalled())
    expect(provisionSchema).toHaveBeenCalledWith(expect.objectContaining({ schema: 'PM' }))
    expect(await screen.findByText(/Created: schema PM, PROJECTS, NOTES/)).toBeInTheDocument()
  })

  it('disables schema provisioning until a schema name is entered', () => {
    render(<ConnectionEditor connection={null} onClose={() => {}} />)
    expect(screen.getByRole('button', { name: 'Create schema & tables' })).toBeDisabled()
  })

  it('generates the retail (bookstore) dataset from the Retail section, with a typed count', async () => {
    generateDemo.mockResolvedValue({
      ok: true,
      error: null,
      journeys: 250,
      project: 'Online Bookstore',
      message: 'Created 250 journeys for “Online Bookstore” in PM.JOURNEYS',
    })
    render(<ConnectionEditor connection={null} onClose={() => {}} />)

    fireEvent.click(screen.getByText('Demo Content'))
    const retail = screen.getByRole('group', { name: 'Online Bookstore' })
    fireEvent.change(within(retail).getByLabelText('Schema'), { target: { value: 'PM' } })

    // The count is a typed number field (not a stepper).
    const journeys = within(retail).getByLabelText('Journeys') as HTMLInputElement
    expect(journeys.type).toBe('number')
    fireEvent.change(journeys, { target: { value: '250' } })

    fireEvent.click(within(retail).getByRole('button', { name: /Generate/ }))

    await waitFor(() => expect(generateDemo).toHaveBeenCalled())
    expect(generateDemo).toHaveBeenCalledWith(
      expect.objectContaining({ dataset: 'retail', schema: 'PM', journeys: 250 }),
    )
    expect(await screen.findByText(/Created 250 journeys/)).toBeInTheDocument()
  })

  it('generates the finance (credit application) dataset from the Finance/Insurance section', async () => {
    generateDemo.mockResolvedValue({
      ok: true,
      error: null,
      journeys: 100,
      project: 'Online Credit Application',
      message: 'Created 100 journeys for “Online Credit Application” in PM.JOURNEYS',
    })
    render(<ConnectionEditor connection={null} onClose={() => {}} />)

    fireEvent.click(screen.getByText('Demo Content'))
    const finance = screen.getByRole('group', { name: 'Online Credit Application' })
    fireEvent.change(within(finance).getByLabelText('Schema'), { target: { value: 'PM' } })
    fireEvent.change(within(finance).getByLabelText('Journeys'), { target: { value: '100' } })
    fireEvent.click(within(finance).getByRole('button', { name: /Generate/ }))

    await waitFor(() =>
      expect(generateDemo).toHaveBeenCalledWith(
        expect.objectContaining({ dataset: 'finance', journeys: 100 }),
      ),
    )
  })

  it('generates the transportation (flight booking) dataset from the Transportation section', async () => {
    generateDemo.mockResolvedValue({
      ok: true,
      error: null,
      journeys: 300,
      project: 'Flight Booking & Management',
      message: 'Created 300 journeys for “Flight Booking & Management” in PM.JOURNEYS',
    })
    render(<ConnectionEditor connection={null} onClose={() => {}} />)

    fireEvent.click(screen.getByText('Demo Content'))
    const flight = screen.getByRole('group', { name: 'Flight Booking & Management' })
    fireEvent.change(within(flight).getByLabelText('Schema'), { target: { value: 'PM' } })
    fireEvent.change(within(flight).getByLabelText('Journeys'), { target: { value: '300' } })
    fireEvent.click(within(flight).getByRole('button', { name: /Generate/ }))

    await waitFor(() =>
      expect(generateDemo).toHaveBeenCalledWith(
        expect.objectContaining({ dataset: 'transportation', journeys: 300 }),
      ),
    )
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
