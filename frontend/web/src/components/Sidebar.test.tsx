/** Sidebar Configuration section — guards the removal of the obsolete client-side
 *  "Require authentication" toggle (sign-in is managed centrally in the admin now). */

import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Sidebar } from './Sidebar'
import { useStore } from '../store'

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
  it('shows the Metrics and Sampling sections in chart modes', () => {
    useStore.setState({ activeChartMode: 'A-Chart' })
    render(<Sidebar onCollapse={() => {}} />)
    expect(screen.getByText('Metrics')).toBeInTheDocument()
    expect(screen.getByText('Sampling')).toBeInTheDocument()
  })

  it('hides Metrics (fixed to Avg Time) and Sampling in Individual Journey mode', () => {
    useStore.setState({ activeChartMode: 'Individual Journey' })
    render(<Sidebar onCollapse={() => {}} />)
    expect(screen.queryByText('Metrics')).toBeNull()
    expect(screen.queryByText('Sampling')).toBeNull()
  })
})
