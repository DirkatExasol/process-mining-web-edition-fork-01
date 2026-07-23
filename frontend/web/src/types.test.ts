/** Model-helper tests — the TypeScript mirrors of ProcessTransition /
 *  ProcessGraph / SampleSet / NoteTarget behaviour. */

import { describe, expect, it } from 'vitest'
import {
  isTimeBased,
  maxMetricValue,
  metricValue,
  noteTargetKey,
  noteTargetLabel,
  sampleLabel,
  sampleShortLabel,
  type ProcessGraph,
  type ProcessTransition,
} from './types'

const t: ProcessTransition = {
  fromStep: 'A',
  toStep: 'B',
  occurrences: 7,
  avgSecs: 1.0,
  minSecs: 0.5,
  maxSecs: 3.0,
  stdDevSecs: 0.25,
}

describe('metricValue', () => {
  it('maps each metric to the right field', () => {
    expect(metricValue(t, 'Count')).toBe(7)
    expect(metricValue(t, 'Avg Time')).toBe(1.0)
    expect(metricValue(t, 'Min Time')).toBe(0.5)
    expect(metricValue(t, 'Max Time')).toBe(3.0)
    expect(metricValue(t, 'Std Dev')).toBe(0.25)
  })
})

describe('isTimeBased', () => {
  it('is false only for Count', () => {
    expect(isTimeBased('Count')).toBe(false)
    for (const m of ['Avg Time', 'Min Time', 'Max Time', 'Std Dev'] as const) {
      expect(isTimeBased(m)).toBe(true)
    }
  })
})

describe('maxMetricValue', () => {
  const graph: ProcessGraph = {
    steps: {},
    transitions: [
      { fromStep: 'A', toStep: 'B', occurrences: 3, avgSecs: 2, minSecs: 1, maxSecs: 4, stdDevSecs: null },
      { fromStep: 'B', toStep: 'C', occurrences: 9, avgSecs: 5, minSecs: 2, maxSecs: 8, stdDevSecs: null },
    ],
  }

  it('reports the maximum per metric', () => {
    expect(maxMetricValue(graph, 'Count')).toBe(9)
    expect(maxMetricValue(graph, 'Avg Time')).toBe(5)
    expect(maxMetricValue(graph, 'Max Time')).toBe(8)
  })

  it('falls back to 1 for an empty graph', () => {
    expect(maxMetricValue({ steps: {}, transitions: [] }, 'Count')).toBe(1)
  })
})

describe('SampleSet labels', () => {
  it('formats long and short labels', () => {
    expect(sampleLabel('ORIGINAL')).toBe('Original Data')
    expect(sampleShortLabel('SAMPLE_2')).toBe('Sample 2')
  })
})

describe('NoteTarget helpers', () => {
  it('builds keys and labels for nodes and edges', () => {
    expect(noteTargetKey({ type: 'node', value: 'Checkout' })).toBe('node:Checkout')
    expect(noteTargetLabel({ type: 'node', value: 'Checkout' })).toBe('Checkout')
    expect(noteTargetKey({ type: 'edge', from: 'A', to: 'B' })).toBe('edge:A->B')
    expect(noteTargetLabel({ type: 'edge', from: 'A', to: 'B' })).toBe('A → B')
  })
})
