/** Sparkline — the weekly ingest mini-chart with a dashed flat tail for the recency gap. */

import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Sparkline } from './Sparkline'

describe('Sparkline', () => {
  it('draws a line through active weeks and a dashed gap when the tail is zero', () => {
    const { container } = render(<Sparkline values={[2, 5, 3, 0, 0]} label="x" />)
    expect(container.querySelector('polyline.spark-line')).toBeTruthy()
    // Trailing zeros (last ingest two weeks before "now") → a dashed gap segment.
    expect(container.querySelector('line.spark-gap')).toBeTruthy()
    // The marker sits on the most recent non-zero week.
    expect(container.querySelector('circle.spark-dot')).toBeTruthy()
  })

  it('shows no line and a flat baseline when there are no ingests at all', () => {
    const { container } = render(<Sparkline values={[0, 0, 0]} />)
    expect(container.querySelector('polyline.spark-line')).toBeNull()
    expect(container.querySelector('circle.spark-dot')).toBeNull()
    expect(container.querySelector('line.spark-gap')).toBeTruthy()
  })

  it('has no gap segment when the most recent week has ingests', () => {
    const { container } = render(<Sparkline values={[1, 2, 4]} />)
    expect(container.querySelector('polyline.spark-line')).toBeTruthy()
    expect(container.querySelector('line.spark-gap')).toBeNull()
  })
})
