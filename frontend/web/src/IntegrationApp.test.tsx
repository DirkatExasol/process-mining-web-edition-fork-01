/** IntegrationApp tests — the console's access gate: sign-in when there is no
 *  session, an access-denied panel for a signed-in user without the role, and the
 *  data-source shell for a power/developer/admin user. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'

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
// LoginView (rendered by IntegrationApp when unauthenticated) fires these three on mount.
const loginViewMocks = [
  api.directoryStatus,
  api.licenseStatus,
  api.loginAppearance,
] as unknown as ReturnType<typeof vi.fn>[]

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
  // Unmount FIRST, then reset the store. Otherwise resetting authUser re-renders the
  // still-mounted IntegrationApp into mounting LoginView, whose async effects then fire
  // outside act() and log a spurious act(...) warning. With nothing mounted, the reset
  // touches no component.
  cleanup()
  useStore.setState({ authUser: null, authIsPower: false, authIsDeveloper: false, authIsAdmin: false })
  vi.clearAllMocks()
})

// IntegrationApp's mount effect runs an async bootstrap (checkSession → store updates →
// optionally refreshConnections → setReady) and then renders LoginView, which has its own
// async mount effects. Render inside act() and let that whole cascade settle here, so
// every resulting setState lands wrapped rather than escaping to log an act(...) warning.
async function renderApp() {
  let result: ReturnType<typeof render>
  await act(async () => {
    result = render(<IntegrationApp />)
    // The cascade is staged: checkSession resolves, setReady(true) re-renders, and only
    // THEN does the child (LoginView, or the console) mount and fire its own effects. Let
    // a macrotask pass so that late mount happens, then await the exact promises the
    // child's mount effects returned — their `.then(setState)` resolves before this await,
    // so every update lands inside act rather than escaping to log an act(...) warning.
    await new Promise((res) => setTimeout(res))
    await Promise.allSettled(
      loginViewMocks.flatMap((m) => m.mock.results.map((r) => r.value)),
    )
  })
  return result!
}

describe('IntegrationApp', () => {
  it('shows the sign-in screen when there is no session', async () => {
    session.mockResolvedValue({ ...SESSION_BASE })
    await renderApp()
    // LoginView renders a Sign in control.
    await waitFor(() => expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy())
    expect(screen.queryByText(/Data sources/i)).toBeNull()
  })

  it('shows the abstraction-layer console for a developer', async () => {
    session.mockResolvedValue({
      ...SESSION_BASE, authenticated: true, username: 'dev', isDeveloper: true,
    })
    await renderApp()
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /Abstraction layer/i })).toBeTruthy(),
    )
    expect(screen.getByText(/\(Developer\)/)).toBeTruthy()
  })

  it('denies a signed-in user without the role', async () => {
    session.mockResolvedValue({
      ...SESSION_BASE, authenticated: true, username: 'plain',
    })
    await renderApp()
    await waitFor(() => expect(screen.getByText(/Access denied/i)).toBeTruthy())
  })
})
