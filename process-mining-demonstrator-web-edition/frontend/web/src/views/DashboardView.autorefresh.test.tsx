/** Dashboard auto-refresh — the interval timer re-fetches the whole dashboard, and the
 *  manual ↻ Refresh button does so on demand. The pure notification filters are covered in
 *  DashboardView.notifications.test.ts; this focuses on the timer + refresh wiring. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'

const dashboard = vi.fn(async () => ({ connections: [] }))
vi.mock('../api', () => ({
  api: {
    dashboard: (...a: unknown[]) => dashboard(...(a as [])),
    listNotifications: vi.fn(async () => ({ rules: [], canManage: false })),
    patchSettings: vi.fn(async () => ({})), // the debounced settings flush calls this
    settings: vi.fn(async () => ({})),
  },
}))

import { DashboardView } from './DashboardView'
import { writeSetting } from '../settings'

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  dashboard.mockClear()
  writeSetting('dashboard.autoRefreshSecs', 0) // off by default
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Dashboard auto-refresh', () => {
  it('does not auto-refresh when the interval is Off', async () => {
    render(<DashboardView />)
    await act(async () => {}) // flush the initial load
    expect(dashboard).toHaveBeenCalledTimes(1) // the mount fetch only
    await advance(120_000)
    expect(dashboard).toHaveBeenCalledTimes(1) // …nothing more
  })

  it('re-fetches the dashboard once per interval when an interval is set', async () => {
    writeSetting('dashboard.autoRefreshSecs', 30)
    render(<DashboardView />)
    await act(async () => {}) // initial load
    const initial = dashboard.mock.calls.length
    await advance(29_999)
    expect(dashboard).toHaveBeenCalledTimes(initial) // not before the interval elapses
    await advance(2)
    expect(dashboard).toHaveBeenCalledTimes(initial + 1) // one tick → one re-fetch
    await advance(30_000)
    expect(dashboard).toHaveBeenCalledTimes(initial + 2)
  })

  it('the manual Refresh button re-fetches immediately', async () => {
    render(<DashboardView />)
    await act(async () => {}) // initial load (groups resolve → header renders)
    await act(async () => {}) // a second flush to settle the resolved state
    const before = dashboard.mock.calls.length
    await act(async () => {
      fireEvent.click(screen.getByText('Refresh'))
    })
    expect(dashboard.mock.calls.length).toBe(before + 1)
  })
})
