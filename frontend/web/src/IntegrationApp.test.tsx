/** IntegrationApp tests — the console's access gate: sign-in when there is no
 *  session, an access-denied panel for a signed-in user without the role, and the
 *  data-source shell for a power/developer/admin user. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('./api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    session: vi.fn(),
    directoryStatus: vi.fn(async () => ({ configured: false, available: false })),
    licenseStatus: vi.fn(async () => ({ state: 'valid', demoMode: false, remainingSeconds: null })),
    loginAppearance: vi.fn(async () => ({ type: 'default', color: '', image: '' })),
    login: vi.fn(),
    logout: vi.fn(async () => {}),
    settings: vi.fn(async () => ({})),
    listConnections: vi.fn(async () => []),
    connectionStatus: vi.fn(async () => ({ isConnected: false, activeProfileId: null, lastError: null })),
    integrationStatus: vi.fn(async () => ({
      state: 'idle', extractorId: null, extractorName: null, connectionId: null,
      schema: null, recordsPushed: 0, tablesTouched: [], startedAt: null, finishedAt: null,
      lastError: null, messages: [], registeredExtractors: 0, activeConnectionId: null,
      activeSchema: null, connected: false,
    })),
    integrationExtractors: vi.fn(async () => []),
    listSourceTypes: vi.fn(async () => []),
    createSourceType: vi.fn(),
    deleteSourceType: vi.fn(async () => ({ ok: true })),
    listSources: vi.fn(async () => []),
    createSource: vi.fn(),
    deleteSource: vi.fn(async () => ({ ok: true })),
    listManageableConnections: vi.fn(async () => []),
    listAssignableUsers: vi.fn(async () => []),
  },
}))

vi.mock('./passkey', () => ({
  passkeysSupported: vi.fn(() => false),
  passkeysUsable: vi.fn(() => false),
  authenticateWithPasskey: vi.fn(),
}))

import { api } from './api'
import { useStore } from './store'
import { IntegrationApp } from './IntegrationApp'

const session = api.session as unknown as ReturnType<typeof vi.fn>

const SESSION_BASE = {
  authenticated: false,
  username: null,
  isAdmin: false,
  isPower: false,
  isDeveloper: false,
  displayName: null,
  authSource: null,
  requireLogin: true,
  idleTimeoutMins: 0,
  passkeyAllowed: false,
  mfaAllowed: false,
  mfaEnabled: false,
}

afterEach(() => {
  useStore.setState({ authUser: null, authIsPower: false, authIsDeveloper: false, authIsAdmin: false })
  vi.clearAllMocks()
})

describe('IntegrationApp', () => {
  it('shows the sign-in screen when there is no session', async () => {
    session.mockResolvedValue({ ...SESSION_BASE })
    render(<IntegrationApp />)
    // LoginView renders a Sign in control.
    await waitFor(() => expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy())
    expect(screen.queryByText(/Data sources/i)).toBeNull()
  })

  it('shows the abstraction-layer console for a developer', async () => {
    session.mockResolvedValue({
      ...SESSION_BASE, authenticated: true, username: 'dev', isDeveloper: true,
    })
    render(<IntegrationApp />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /Abstraction layer/i })).toBeTruthy(),
    )
    expect(screen.getByText(/\(Developer\)/)).toBeTruthy()
  })

  it('denies a signed-in user without the role', async () => {
    session.mockResolvedValue({
      ...SESSION_BASE, authenticated: true, username: 'plain',
    })
    render(<IntegrationApp />)
    await waitFor(() => expect(screen.getByText(/Access denied/i)).toBeTruthy())
  })
})
