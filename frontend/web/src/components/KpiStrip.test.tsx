/** KPI "Active Sample" tile — reflects the side's data source: a sample set, or a
 *  Sim-A/Sim-B simulation. */

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KpiStrip } from './KpiStrip'
import { useStore } from '../store'
import { EMPTY_GRAPH } from '../types'

const inputs = {
  graph: EMPTY_GRAPH,
  journeyCount: null,
  durations: { minSecs: null, avgSecs: null, stdDevSecs: null, maxSecs: null },
  goodness: null,
  side: 'a' as const,
  loading: false,
}

describe('KpiStrip Active Sample', () => {
  it('shows the sample-set label when the source is a sample set', () => {
    useStore.setState({
      abDataSourceA: { kind: 'sampleSet', sampleSet: 'SAMPLE_1' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      sampleCounts: { SAMPLE_1: 123 } as any,
    })
    render(<KpiStrip {...inputs} />)
    expect(screen.getByText('Sample 1')).toBeInTheDocument()
    expect(screen.getByText('123')).toBeInTheDocument()
  })

  it('shows Sim-A and its journey count when the source is a simulation', () => {
    useStore.setState({
      abDataSourceA: { kind: 'simulation', slot: 'Sim-A' },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      simResultA: { totalJourneys: 4200 } as any,
    })
    render(<KpiStrip {...inputs} />)
    expect(screen.getByText('Sim-A')).toBeInTheDocument()
    expect(screen.getByText('4,200')).toBeInTheDocument()
  })
})
