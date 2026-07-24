/** Sampling section — each created sample outlines its strategy + journey count. */

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SamplingSection } from './SamplingSection'
import { useStore } from '../store'

describe('SamplingSection', () => {
  it('outlines the sampling strategy (as a badge) and the journey count of a sample', () => {
    useStore.setState({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      sampleCounts: { SAMPLE_1: 1500 } as any,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      sampleMethods: { SAMPLE_1: 'temporal' } as any,
    })
    render(<SamplingSection />)

    expect(screen.getByText('1,500 journeys')).toBeInTheDocument()
    const badge = screen.getByText('Temporal Stratified')
    expect(badge).toHaveClass('sample-method-tag')
  })

  it('shows "Not created" for empty sample slots', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useStore.setState({ sampleCounts: {} as any, sampleMethods: {} as any })
    render(<SamplingSection />)
    expect(screen.getAllByText('Not created')).toHaveLength(3)
  })
})
