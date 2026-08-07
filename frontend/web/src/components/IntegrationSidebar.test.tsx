/** The integration console's Connections section: a developer manages connections here
 *  the same way they can in the main app, rather than having to switch surfaces to add
 *  the destination they are about to import into. Editing is gated on *ownership*, not
 *  on merely being assigned the connection. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    listConnections: vi.fn(async () => []),
    refreshConnections: vi.fn(),
    listManageableConnections: vi.fn(async () => []),
    listAssignableUsers: vi.fn(async () => []),
    listSources: vi.fn(async () => []),
    listSourceTypes: vi.fn(async () => []),
  },
}))

import { useStore } from '../store'
import { IntegrationSidebar } from './IntegrationSidebar'
import { renderSettled, resetStoreOutsideRender } from '../test/renderSettled'

const ASSIGNED = {
  id: 'c1', name: 'Prod DB', comment: '', host: 'db', port: 8563,
  schema: 'MINING', hasLLM: false, llmURL: null,
}
const OWNED = { ...ASSIGNED, useTLS: false, certModeRaw: 'verify', assignments: ['dev'] }

function setUser(over: Record<string, unknown>) {
  useStore.setState({
    connections: [ASSIGNED] as never,
    connection: { isConnected: false, activeProfileId: null, lastError: null } as never,
    manageableConnections: [],
    authIsAdmin: false,
    authIsPower: false,
    authIsDeveloper: false,
    ...over,
  } as never)
}

afterEach(() => {
  // Unmount before resetting the store, so setUser() can't re-render the still-mounted
  // sidebar outside act().
  resetStoreOutsideRender(() => setUser({}))
  vi.clearAllMocks()
})

describe('IntegrationSidebar connections', () => {
  it('lets a developer create a connection from the console', async () => {
    setUser({ authIsDeveloper: true })
    await renderSettled(<IntegrationSidebar />)

    fireEvent.click(screen.getByTitle('New connection'))
    // The shared editor opens in "new" mode.
    await waitFor(() => expect(screen.getByText(/New connection/i)).toBeTruthy())
  })

  it('offers ✎ only for a connection the developer owns', async () => {
    // Assigned but owned by someone else → no edit affordance.
    setUser({ authIsDeveloper: true, manageableConnections: [] })
    const { unmount } = await renderSettled(<IntegrationSidebar />)
    expect(screen.queryByTitle('Edit connection')).toBeNull()
    unmount()

    setUser({ authIsDeveloper: true, manageableConnections: [OWNED] as never })
    await renderSettled(<IntegrationSidebar />)
    expect(screen.getByTitle('Edit connection')).toBeTruthy()
  })

  it('editing does not also connect/disconnect the card underneath', async () => {
    setUser({ authIsDeveloper: true, manageableConnections: [OWNED] as never })
    await renderSettled(<IntegrationSidebar />)

    fireEvent.click(screen.getByTitle('Edit connection'))
    // The card's own click handler would have started a connect.
    expect(useStore.getState().connection.activeProfileId).toBeNull()
  })

  it('hides connection management from a user without the capability', async () => {
    setUser({}) // no role flags
    await renderSettled(<IntegrationSidebar />)
    expect(screen.queryByTitle('New connection')).toBeNull()
    expect(screen.queryByTitle('Edit connection')).toBeNull()
  })
})
