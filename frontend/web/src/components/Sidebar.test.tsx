/** Sidebar Configuration section — guards the removal of the obsolete client-side
 *  "Require authentication" toggle (sign-in is managed centrally in the admin now). */

import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Sidebar } from './Sidebar'
import { useStore } from '../store'
import type { FilterGroup } from '../types'

const preset = (id: string, name: string): FilterGroup => ({
  id,
  name,
  fromDate: '',
  toDate: '',
  includedSteps: [],
  excludedSteps: [],
  meta1: '',
  meta2: '',
  meta3: '',
  minSteps: 0,
  maxSteps: 0,
  minJourneyTime: 0,
  maxJourneyTime: 0,
  minScore: 0,
  maxScore: 0,
})

describe('Sidebar Configuration', () => {
  it('no longer offers a "Require authentication" toggle, but keeps the other config toggles', () => {
    render(<Sidebar onCollapse={() => {}} />)

    // Open the Configuration accordion (others collapse).
    fireEvent.click(screen.getByRole('button', { name: /Configuration/i }))

    expect(screen.queryByText('Require authentication')).toBeNull()
    // Sanity: neighbouring toggles are still present.
    expect(screen.getByText('Colorise edges by weight')).toBeInTheDocument()
    expect(screen.getByText('Optimise layout')).toBeInTheDocument()
  })
})

describe('Sidebar Metrics section', () => {
  it('shows the Metrics and Sampling sections for a power user in chart modes', () => {
    useStore.setState({ activeChartMode: 'A-Chart', authIsPower: true, authIsAdmin: false })
    render(<Sidebar onCollapse={() => {}} />)
    expect(screen.getByText('Metrics')).toBeInTheDocument()
    expect(screen.getByText('Sampling')).toBeInTheDocument()
  })

  it('hides Sampling from a regular (non-power, non-admin) user', () => {
    useStore.setState({ activeChartMode: 'A-Chart', authIsPower: false, authIsAdmin: false })
    render(<Sidebar onCollapse={() => {}} />)
    expect(screen.getByText('Metrics')).toBeInTheDocument() // still visible to everyone
    expect(screen.queryByText('Sampling')).toBeNull() // power/admin only
  })

  it('hides Metrics (fixed to Avg Time) and Sampling in Individual Journey mode', () => {
    useStore.setState({
      activeChartMode: 'Individual Journey',
      authIsPower: true,
      authIsAdmin: false,
    })
    render(<Sidebar onCollapse={() => {}} />)
    expect(screen.queryByText('Metrics')).toBeNull()
    expect(screen.queryByText('Sampling')).toBeNull()
  })

  it('auto-opens the Filters (Event ID) section in Individual Journey mode', () => {
    useStore.setState({ activeChartMode: 'Individual Journey' })
    render(<Sidebar onCollapse={() => {}} />)
    // The Filters section is expanded on entry, revealing the Event ID field.
    expect(screen.getByText('Event ID')).toBeInTheDocument()
  })
})

describe('Sidebar filter presets', () => {
  it('lists saved presets alphabetically ascending (A→Z)', () => {
    useStore.setState({
      activeChartMode: 'A-Chart',
      filterGroups: [preset('g1', 'Zeta'), preset('g2', 'Alpha'), preset('g3', 'Mid')],
      selectedFilterGroupId: null,
    })
    render(<Sidebar onCollapse={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Filters/i }))

    const names = screen
      .getAllByText(/^(Alpha|Mid|Zeta)$/)
      .map((el) => el.textContent)
    expect(names).toEqual(['Alpha', 'Mid', 'Zeta'])
  })

  it('caps the visible preset list to four rows and scrolls the rest', () => {
    useStore.setState({
      activeChartMode: 'A-Chart',
      filterGroups: Array.from({ length: 7 }, (_, i) =>
        preset(`g${i}`, `Preset ${String.fromCharCode(65 + i)}`),
      ),
      selectedFilterGroupId: null,
    })
    render(<Sidebar onCollapse={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Filters/i }))

    // All seven presets render (none are dropped)…
    expect(screen.getAllByText(/^Preset [A-G]$/)).toHaveLength(7)
    // …but their container is a fixed-height scroll area sized for four rows.
    const scroller = screen.getByText('Preset A').closest('[style*="overflow"]') as HTMLElement
    expect(scroller.style.overflowY).toBe('auto')
    expect(scroller.style.maxHeight).toBe(`${4 * 32 + 3 * 4}px`)
  })
})
