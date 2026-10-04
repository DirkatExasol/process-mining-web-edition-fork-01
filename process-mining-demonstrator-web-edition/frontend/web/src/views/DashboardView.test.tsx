/** DashboardView — the direct-login overview: per-process cards with events, last-ingest
 *  and an ingest sparkline, the overall card, and the add/reorder metric toolbar. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

const dashboard = vi.fn()
vi.mock('../api', () => ({
  api: {
    dashboard: () => dashboard(),
    // writeSetting flushes through here (debounced) when a metric is toggled.
    patchSettings: vi.fn(async () => ({})),
    settings: vi.fn(async () => ({})),
  },
}))

import { DashboardView } from './DashboardView'
import { renderSettled, resetStoreOutsideRender } from '../test/renderSettled'
import { useStore } from '../store'
import { writeSetting } from '../settings'

afterEach(() => {
  writeSetting('dashboard.extraMetrics', [])
  resetStoreOutsideRender(() => useStore.setState({ authUser: null } as never))
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
  it('renders the overview card, a process card with events + sparkline, and a group error', async () => {
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
    // An unreadable connection degrades to a per-group error.
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
