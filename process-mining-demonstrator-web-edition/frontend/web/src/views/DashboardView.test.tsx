/** DashboardView — the direct-login overview: per-process cards with events, last-ingest
 *  and an ingest sparkline, the overall card, and the add/reorder metric toolbar. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

const dashboard = vi.fn()
const listNotifications = vi.fn(
  async (): Promise<{ rules: unknown[]; canManage: boolean }> => ({ rules: [], canManage: false }),
)
const toggleProjectNotifications = vi.fn(async () => ({ changed: 1, enabled: true }))
const checkNotification = vi.fn(async (): Promise<unknown> => ({}))
const checkAllNotifications = vi.fn(
  async (): Promise<{ rules: unknown[]; canManage: boolean }> => ({ rules: [], canManage: false }),
)
vi.mock('../api', () => ({
  api: {
    dashboard: () => dashboard(),
    listNotifications: () => listNotifications(),
    toggleProjectNotifications: (...a: unknown[]) => toggleProjectNotifications(...(a as [])),
    notificationSteps: vi.fn(async () => ({ steps: [] })),
    checkNotification: (...a: unknown[]) => checkNotification(...(a as [])),
    checkAllNotifications: () => checkAllNotifications(),
    saveNotification: vi.fn(async () => ({})),
    updateNotification: vi.fn(async () => ({})),
    deleteNotification: vi.fn(async () => ({})),
    setNotificationEnabled: vi.fn(async () => ({})),
    // writeSetting flushes through here (debounced) when a metric is toggled.
    patchSettings: vi.fn(async () => ({})),
    settings: vi.fn(async () => ({})),
  },
}))

import { DashboardView, reorderKeys } from './DashboardView'
import { renderSettled, resetStoreOutsideRender } from '../test/renderSettled'
import { useStore } from '../store'
import { writeSetting } from '../settings'

afterEach(() => {
  writeSetting('dashboard.extraMetrics', [])
  writeSetting('dashboard.tileOrder', [])
  resetStoreOutsideRender(() =>
    useStore.setState({ authUser: null, notificationsEnabled: false } as never),
  )
  listNotifications.mockResolvedValue({ rules: [], canManage: false })
})

const rule = (over: Record<string, unknown> = {}) => ({
  id: 'r1', connectionId: 'c1', connectionName: 'Prod DB', projectId: 1,
  projectTitle: 'Bookstore', kind: 'transition_metric', name: '', severity: 'INFO',
  intervalSecs: 300, enabled: true,
  config: { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 7200 },
  state: {},
  ...over,
})

describe('reorderKeys (tile drag order)', () => {
  it('moves the dragged key to sit immediately before the drop target', () => {
    expect(reorderKeys(['a', 'b', 'c', 'd'], 'd', 'b')).toEqual(['a', 'd', 'b', 'c'])
    expect(reorderKeys(['a', 'b', 'c'], 'a', 'c')).toEqual(['b', 'a', 'c'])
    expect(reorderKeys(['a', 'b', 'c'], 'b', 'b')).toEqual(['a', 'b', 'c']) // no-op
    expect(reorderKeys(['a', 'b', 'c'], 'x', 'b')).toEqual(['a', 'x', 'b', 'c']) // unknown drag inserted
  })
})

const ONE_GROUP = {
  connections: [
    {
      id: 'c1', name: 'Prod DB', schema: 'MINING', error: null,
      projects: [
        {
          projectId: 1, title: 'Bookstore', titleShort: 'BOOK',
          journeys: 10, events: 40, firstEventAt: '2026-07-01T09:00:00',
          lastEventAt: '2026-09-14T10:00:00', steps: 6,
          openNotes: { URGENT: 2, INFO: 1 },
          timeline: [
            { week: '2026-09-07', events: 40 },
            { week: '2026-09-14', events: 0 },
          ],
        },
      ],
    },
    { id: 'c2', name: 'Sandbox', schema: 'SBX', error: 'schema unreachable', projects: [] },
  ],
}

describe('DashboardView', () => {
  it('renders the overview card, a process tile with events + sparkline, and a connection error note', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    const { container } = await renderSettled(<DashboardView />)

    // Overall overview strip.
    expect(await screen.findByText('Processes')).toBeTruthy()
    expect(screen.getByText('Connections')).toBeTruthy()
    // Process card with its event count and always-on metrics.
    expect(screen.getByText('Bookstore')).toBeTruthy()
    expect(screen.getAllByText('40').length).toBeGreaterThan(0) // card events + overview total
    expect(screen.getAllByText('Events').length).toBeGreaterThan(0)
    expect(screen.getByText('Last log')).toBeTruthy()
    // Sparklines are rendered (overview + the one process).
    expect(container.querySelectorAll('svg.spark').length).toBe(2)
    // An unreadable connection is listed in the error note (no group headers now).
    expect(screen.getByText(/schema unreachable/)).toBeTruthy()
  })

  it('adds an extra metric column when its chip is clicked', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    await renderSettled(<DashboardView />)
    await screen.findByText('Bookstore')

    // "Journeys" is offered as an addable chip; clicking it shows the metric on the card
    // (it then appears both as the selected chip and as the card's metric label).
    expect(screen.queryByText('Journeys')).toBeNull()
    fireEvent.click(screen.getByText('+ Journeys'))
    await waitFor(() => expect(screen.getAllByText('Journeys').length).toBeGreaterThanOrEqual(1))
  })

  it('shows open notes by severity when that metric is added', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    const { container } = await renderSettled(<DashboardView />)
    await screen.findByText('Bookstore')

    fireEvent.click(screen.getByText('+ Open notes'))
    // The card renders a per-severity count chip per non-zero severity (URGENT 2, INFO 1).
    await waitFor(() => expect(container.querySelectorAll('.dash-notes .note-sev').length).toBe(2))
    const chip = container.querySelector('.dash-notes .note-sev[title*="Urgent"]')
    expect(chip?.textContent).toContain('2')
  })

  it('opens the process (connect + select) when a card is clicked', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    const connect = vi.fn(async () => true)
    const select = vi.fn(async () => {})
    useStore.setState({ connectConnection: connect, selectProject: select } as never)
    // The project must be findable after connect for selectProject to fire.
    useStore.setState({ projects: [{ projectId: 1, title: 'Bookstore', titleShort: 'BOOK' }] } as never)

    await renderSettled(<DashboardView />)
    fireEvent.click(await screen.findByText('Bookstore'))
    await waitFor(() => expect(connect).toHaveBeenCalledWith(expect.objectContaining({ id: 'c1' })))
    await waitFor(() => expect(select).toHaveBeenCalledWith(expect.objectContaining({ projectId: 1 })))
  })
})

describe('DashboardView — Notifications section', () => {
  it('is hidden when the feature is off', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    useStore.setState({ notificationsEnabled: false } as never)
    await renderSettled(<DashboardView />)
    await screen.findByText('Bookstore')
    expect(screen.queryByText('Notifications')).toBeNull()
    expect(listNotifications).not.toHaveBeenCalled()
  })

  it('shows a blue stats strip and firing cards first, with the gauge/breach value, for managers', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    useStore.setState({ notificationsEnabled: true } as never)
    const cfg = { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 960 }
    const healthy = rule({ id: 'ok', severity: 'INFO', config: cfg, state: { lastRunAt: '2026-09-14T10:00:00Z', lastValue: 600, triggered: false } })
    const firing = rule({ id: 'fire', severity: 'URGENT', config: cfg, state: { triggered: true, triggeredAt: '2026-09-14T10:55:00Z', lastValue: 1020 } })
    // Returned unsorted: the view must float the firing one to the top.
    listNotifications.mockResolvedValue({ rules: [healthy, firing], canManage: true })

    const { container } = await renderSettled(<DashboardView />)
    expect(await screen.findByText('Notifications')).toBeTruthy()
    expect(screen.getByText('＋ Create / Edit')).toBeTruthy()
    // The blue stats strip.
    expect(screen.getByText('Rules')).toBeTruthy()
    expect(screen.getByText('Connections watched')).toBeTruthy()
    // The firing card: gauge limit label, last value in minutes, and the over-limit breach.
    expect(screen.getAllByText('limit 16:00').length).toBeGreaterThan(0)
    expect(screen.getByText('17:00 min')).toBeTruthy()
    expect(screen.getByText(/60 s/)).toBeTruthy()
    expect(screen.getByText(/6\.3%/)).toBeTruthy()
    // Two cards; the firing (Triggered) one is first.
    const cards = [...container.querySelectorAll('.nc')]
    expect(cards.length).toBe(2)
    expect(cards[0].querySelector('.ncp-triggered')).toBeTruthy()
    expect(cards[0].classList.contains('alert')).toBe(true)
  })

  it('refreshes every rule from the summary strip', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    useStore.setState({ notificationsEnabled: true } as never)
    const cfg = { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 960 }
    const r = rule({ id: 'r1', config: cfg, state: { lastRunAt: 'x', lastValue: 600, triggered: false } })
    listNotifications.mockResolvedValue({ rules: [r], canManage: true })
    checkAllNotifications.mockResolvedValue({
      rules: [{ ...r, state: { triggered: true, triggeredAt: '2026-09-14T10:55:00Z', lastValue: 1020, lastRunAt: 'x' } }],
      canManage: true,
    })

    await renderSettled(<DashboardView />)
    await screen.findByText('Notifications')
    fireEvent.click(screen.getByText('Refresh all'))
    await waitFor(() => expect(checkAllNotifications).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText('17:00 min')).toBeTruthy())
  })

  it('refreshes a single card on demand via the ↻ button', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    useStore.setState({ notificationsEnabled: true } as never)
    const cfg = { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 960 }
    const r = rule({ id: 'r1', config: cfg, state: { lastRunAt: 'x', lastValue: 600, triggered: false } })
    listNotifications.mockResolvedValue({ rules: [r], canManage: true })
    // The refresh returns the rule now triggered at 17:00.
    checkNotification.mockResolvedValue({
      ...r,
      state: { triggered: true, triggeredAt: '2026-09-14T10:55:00Z', lastValue: 1020, lastRunAt: 'x' },
    })

    const { container } = await renderSettled(<DashboardView />)
    await screen.findByText('Notifications')
    fireEvent.click(container.querySelector('.nc-refresh') as HTMLElement)
    await waitFor(() => expect(checkNotification).toHaveBeenCalledWith('r1'))
    // The card updates in place with the fresh value.
    await waitFor(() => expect(screen.getByText('17:00 min')).toBeTruthy())
  })

  it('hides Create/Edit and the per-card toggle for non-managers', async () => {
    dashboard.mockResolvedValue(ONE_GROUP)
    useStore.setState({ notificationsEnabled: true } as never)
    listNotifications.mockResolvedValue({ rules: [rule()], canManage: false })
    const { container } = await renderSettled(<DashboardView />)
    await screen.findByText('Notifications')
    expect(screen.queryByText('＋ Create / Edit')).toBeNull()
    expect(container.querySelector('.nc-sw')).toBeNull()
  })
})
