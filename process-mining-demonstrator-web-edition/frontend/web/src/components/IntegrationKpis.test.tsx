import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import { IntegrationKpis, relativeTime } from './IntegrationKpis'
import type { PipelineRun } from '../integration/runHistory'

const run = (over: Partial<PipelineRun>): PipelineRun =>
  ({
    key: Math.random().toString(), state: 'completed', sourceName: 's', sourceTypeName: 't',
    extractorName: 'File', connectionName: 'c', connectionId: 'c1', schema: 'S',
    recordsPushed: 0, recordsDone: 0, recordsTotal: 0, lastError: null,
    startedAt: null, finishedAt: null, trigger: 'manual', eventsWritten: 0, eventsSkipped: 0,
    ...over,
  }) as PipelineRun

const tile = (label: string) => screen.getByText(label).closest('.kpi-tile') as HTMLElement

describe('IntegrationKpis', () => {
  it('splits manual vs watchdog runs and sums events', () => {
    const runs = [
      run({ trigger: 'manual', eventsWritten: 100, eventsSkipped: 3 }),
      run({ trigger: 'watchdog', eventsWritten: 20, eventsSkipped: 1 }),
      run({ trigger: 'watchdog', eventsWritten: 5, eventsSkipped: 0 }),
    ]
    render(<IntegrationKpis runs={runs} status={null} />)

    expect(within(tile('Manual imports')).getByText('1')).toBeTruthy()
    expect(within(tile('Watchdog imports')).getByText('2')).toBeTruthy()
    expect(within(tile('Events pushed')).getByText('125')).toBeTruthy()
    expect(within(tile('Events skipped')).getByText('4')).toBeTruthy()
  })

  it('shows active watchdogs out of the total, green when any are on', () => {
    const status = { watchdogsActive: 2, watchdogsTotal: 3, watchdogEnabled: true } as never
    render(<IntegrationKpis runs={[]} status={status} />)
    const t = tile('Watchdogs active')
    expect(within(t).getByText('2 / 3')).toBeTruthy()
    expect(t.querySelector('.kpi-value')?.getAttribute('style')).toContain('--green')
  })

  it('flags a deployment-wide disabled watchdog loop', () => {
    const status = { watchdogsActive: 1, watchdogsTotal: 2, watchdogEnabled: false } as never
    render(<IntegrationKpis runs={[]} status={status} />)
    // The label says "off" so a count that never polls can't read as healthy.
    expect(within(tile('Watchdogs (off)')).getByText('1 / 2')).toBeTruthy()
  })

  it('shows zeros and an em dash with no history', () => {
    render(<IntegrationKpis runs={[]} status={null} />)
    expect(within(tile('Manual imports')).getByText('0')).toBeTruthy()
    expect(within(tile('Last import')).getByText('—')).toBeTruthy()
  })

  it('reports a live run instead of the last finish time', () => {
    const status = { state: 'running' } as never
    render(<IntegrationKpis runs={[run({ finishedAt: new Date().toISOString() })]} status={status} />)
    expect(within(tile('Last import')).getByText('running…')).toBeTruthy()
  })

  it('formats the age of the last import', () => {
    const now = Date.UTC(2026, 0, 2, 12, 0, 0)
    const at = (ms: number) => new Date(now - ms).toISOString()
    expect(relativeTime(at(10_000), now)).toBe('just now')
    expect(relativeTime(at(12 * 60_000), now)).toBe('12m ago')
    expect(relativeTime(at(3 * 3600_000), now)).toBe('3h ago')
    expect(relativeTime(at(3 * 86_400_000), now)).toBe('3d ago')
    expect(relativeTime(null, now)).toBe('—')
  })
})
