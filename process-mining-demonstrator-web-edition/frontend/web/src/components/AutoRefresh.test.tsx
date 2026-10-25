/** A-Chart auto-refresh — the controller fires reloadGraph on the interval (A-Chart only),
 *  and the config UI's Refresh now triggers an immediate reload. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'

// autoRefreshReload refreshes the unfiltered totals via api.sampleCounts before reloading.
vi.mock('../api', () => ({
  api: {
    sampleCounts: vi.fn(async () => ({ counts: { ORIGINAL: 7 }, methods: {} })),
    patchSettings: vi.fn(async () => ({})), // the debounced settings flush calls this
    settings: vi.fn(async () => ({})),
  },
}))

import { AutoRefreshController, AutoRefreshOverlay } from './AutoRefresh'
import { useStore } from '../store'
import { writeSetting } from '../settings'

const reloadGraph = vi.fn(async () => {})

beforeEach(() => {
  vi.useFakeTimers()
  reloadGraph.mockClear()
  writeSetting('achart.autoRefreshSecs', 0)
  useStore.setState({
    activeChartMode: 'A-Chart',
    connection: { ...useStore.getState().connection, isConnected: true },
    selectedProject: { projectId: 1, title: 'P', titleShort: 'P' },
    autoRefreshNextAt: null,
    autoRefreshKick: 0,
    reloadGraph,
  } as never)
})

afterEach(() => {
  vi.useRealTimers()
})

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms)
  })
}

describe('AutoRefresh', () => {
  it('fires reloadGraph once per interval while in A-Chart', async () => {
    writeSetting('achart.autoRefreshSecs', 5)
    render(<AutoRefreshController />)
    await advance(4999)
    expect(reloadGraph).not.toHaveBeenCalled() // not before the interval elapses
    await advance(2)
    expect(reloadGraph).toHaveBeenCalledTimes(1)
    await advance(5000)
    expect(reloadGraph).toHaveBeenCalledTimes(2)
  })

  it('does not auto-refresh outside A-Chart', async () => {
    writeSetting('achart.autoRefreshSecs', 5)
    useStore.setState({ activeChartMode: 'B-Chart' } as never)
    render(<AutoRefreshController />)
    await advance(12_000)
    expect(reloadGraph).not.toHaveBeenCalled()
  })

  it('does nothing when the interval is Off', async () => {
    render(<AutoRefreshController />)
    await advance(12_000)
    expect(reloadGraph).not.toHaveBeenCalled()
  })

  it('the A-Chart overlay Refresh button reloads immediately', async () => {
    writeSetting('achart.autoRefreshSecs', 5) // overlay shows only when an interval is set
    render(<AutoRefreshOverlay />)
    // autoRefreshReload awaits api.sampleCounts, then reloadGraph — flush microtasks.
    await act(async () => {
      fireEvent.click(screen.getByText('↻ Refresh'))
    })
    expect(reloadGraph).toHaveBeenCalledTimes(1)
  })

  it('the overlay is hidden when auto-refresh is Off', () => {
    const { container } = render(<AutoRefreshOverlay />)
    expect(container.querySelector('.ar-pill')).toBeNull()
  })
})
