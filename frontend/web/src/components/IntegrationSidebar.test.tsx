/** The integration console's Connections section: a developer manages connections here
 *  the same way they can in the main app, rather than having to switch surfaces to add
 *  the destination they are about to import into. Editing is gated on *ownership*, not
 *  on merely being assigned the connection. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

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
  vi.clearAllMocks()
  setUser({})
})

describe('IntegrationSidebar connections', () => {
  it('lets a developer create a connection from the console', async () => {
    setUser({ authIsDeveloper: true })
    render(<IntegrationSidebar />)

    fireEvent.click(screen.getByTitle('New connection'))
    // The shared editor opens in "new" mode.
    await waitFor(() => expect(screen.getByText(/New connection/i)).toBeTruthy())
  })

  it('offers ✎ only for a connection the developer owns', () => {
    // Assigned but owned by someone else → no edit affordance.
    setUser({ authIsDeveloper: true, manageableConnections: [] })
    const { unmount } = render(<IntegrationSidebar />)
    expect(screen.queryByTitle('Edit connection')).toBeNull()
    unmount()

    setUser({ authIsDeveloper: true, manageableConnections: [OWNED] as never })
    render(<IntegrationSidebar />)
    expect(screen.getByTitle('Edit connection')).toBeTruthy()
  })

  it('editing does not also connect/disconnect the card underneath', () => {
    setUser({ authIsDeveloper: true, manageableConnections: [OWNED] as never })
    render(<IntegrationSidebar />)

    fireEvent.click(screen.getByTitle('Edit connection'))
    // The card's own click handler would have started a connect.
    expect(useStore.getState().connection.activeProfileId).toBeNull()
  })

  it('hides connection management from a user without the capability', () => {
    setUser({}) // no role flags
    render(<IntegrationSidebar />)
    expect(screen.queryByTitle('New connection')).toBeNull()
    expect(screen.queryByTitle('Edit connection')).toBeNull()
  })
})
