/** IntegrationPipeline — the accumulating ingestion flowchart. jsdom can't lay out
 *  ReactFlow, but node CONTENT still renders, so we assert the Source node shows its
 *  imported-row total and the latest import date/time. */

import { afterEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IntegrationPipeline } from './IntegrationPipeline'
import { useStore } from '../store'
import type { PipelineRun } from '../integration/runHistory'

function run(over: Partial<PipelineRun> = {}): PipelineRun {
  return {
    key: over.startedAt ?? 'k',
    state: 'completed',
    sourceName: 'Access log',
    sourceTypeName: 'Apache',
    extractorName: 'File',
    connectionName: 'Prod DB',
    connectionId: 'c1',
    schema: 'MINING',
    recordsPushed: 100,
    recordsDone: 100,
    recordsTotal: 100,
    lastError: null,
    startedAt: '2026-08-06T09:00:00Z',
    finishedAt: '2026-08-06T09:00:05Z',
    trigger: 'manual',
    eventsWritten: 100,
    eventsSkipped: 0,
    ...over,
  } as PipelineRun
}

afterEach(() => useStore.setState({ connections: [], authUser: null } as never))

describe('IntegrationPipeline source node', () => {
  it('shows the imported-row total and the latest import date/time on the Source node', () => {
    render(<IntegrationPipeline runs={[run()]} live={null} />)

    // Rows imported on the Source node.
    expect(screen.getAllByText(/100 rows imported/).length).toBeGreaterThanOrEqual(1)

    // Latest import stamp — the finishedAt of the newest run, formatted locally.
    const expected = new Date('2026-08-06T09:00:05Z').toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
    })
    expect(screen.getByText(new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeTruthy()
  })

  it('uses the NEWEST run of a source for the stamp when it has run several times', () => {
    // Two runs of the same source; the pipeline aggregates by name, newest wins the stamp.
    const older = run({ startedAt: '2026-08-01T08:00:00Z', finishedAt: '2026-08-01T08:00:03Z', recordsPushed: 40 })
    const newer = run({ startedAt: '2026-08-06T09:00:00Z', finishedAt: '2026-08-06T09:00:05Z', recordsPushed: 60 })
    // runHistory stores newest-first.
    render(<IntegrationPipeline runs={[newer, older]} live={null} />)

    // Totals accumulate across both runs …
    expect(screen.getAllByText(/100 rows imported/).length).toBeGreaterThanOrEqual(1)
    // … and the stamp is the newer run's time, not the older one.
    const newest = new Date('2026-08-06T09:00:05Z').toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
    })
    expect(screen.getByText(new RegExp(newest.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeTruthy()
  })

  it('shows no stamp on the empty idle skeleton', () => {
    render(<IntegrationPipeline runs={[]} live={null} />)
    expect(screen.queryByText(/🕒/)).toBeNull()
  })

  it('renders the Abstraction layer hub wider than the other nodes', () => {
    render(<IntegrationPipeline runs={[run()]} live={null} />)
    // The hub node carries the "wide" modifier; the ordinary nodes do not.
    const hub = screen.getByText('Ingest & normalise').closest('.ipipe-node') as HTMLElement
    expect(hub.className).toContain('wide')
    const source = screen.getByText('Access log').closest('.ipipe-node') as HTMLElement
    expect(source.className).not.toContain('wide')
  })
})
