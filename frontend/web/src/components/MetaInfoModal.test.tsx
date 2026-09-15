/** MetaInfoModal — the node "Meta Infos" panel: tabs per META column, searchable values,
 *  and include/exclude toggles that call handleMetaAction. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, cleanup } from '@testing-library/react'

const handleMetaAction = vi.fn()
const clearMetaFilters = vi.fn()
const state = {
  meta1Title: 'Payment', meta2Title: 'Segment', meta3Title: 'Channel',
  meta1Values: ['Visa', 'SEPA', 'Apple Pay'],
  meta2Values: ['Retail', 'Business'],
  meta3Values: [],
  metaFilters: { included: [['Visa'], [], []], excluded: [[], ['Business'], []] },
  handleMetaAction,
  clearMetaFilters,
}

vi.mock('../store', () => ({
  useStore: (sel: (s: typeof state) => unknown) => sel(state),
}))

import { MetaInfoModal } from './MetaInfoModal'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('MetaInfoModal', () => {
  it('lists Meta_1 values, toggles include/exclude, and searches', () => {
    render(<MetaInfoModal onClose={() => {}} />)

    // Tab labels use the META titles.
    expect(screen.getByRole('button', { name: /Payment/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Segment/ })).toBeTruthy()
    // Meta_1 values are listed; clicking Include on a value calls handleMetaAction(0, …).
    expect(screen.getByText('SEPA')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Include SEPA' }))
    expect(handleMetaAction).toHaveBeenCalledWith(0, 'SEPA', 'include')
    fireEvent.click(screen.getByRole('button', { name: 'Exclude Visa' }))
    expect(handleMetaAction).toHaveBeenCalledWith(0, 'Visa', 'exclude')

    // Search narrows the list.
    fireEvent.change(screen.getByPlaceholderText(/Search Payment values/), { target: { value: 'app' } })
    expect(screen.getByText('Apple Pay')).toBeTruthy()
    expect(screen.queryByText('SEPA')).toBeNull()

    // Clear button reflects the active-count (1 included + 1 excluded = 2) and clears.
    fireEvent.click(screen.getByRole('button', { name: /Clear meta filters \(2\)/ }))
    expect(clearMetaFilters).toHaveBeenCalled()
  })

  it('switches to an empty column and shows the no-values note', () => {
    render(<MetaInfoModal onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Channel/ }))
    expect(screen.getByText(/No values in this column/)).toBeTruthy()
  })
})
