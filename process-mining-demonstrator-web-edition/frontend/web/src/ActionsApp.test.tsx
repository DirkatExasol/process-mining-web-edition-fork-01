/** ActionsApp tests — the surface's access gate and that the builder actually
 *  renders its body (connection picker), not just the brand logo. */

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
    listActions: vi.fn(async () => ({ actions: [] })),
  },
}))

vi.mock('./passkey', () => ({
  passkeysSupported: vi.fn(() => false),
  passkeysUsable: vi.fn(() => false),
  authenticateWithPasskey: vi.fn(),
}))

import { api } from './api'
import { useStore } from './store'
import { ActionsApp } from './ActionsApp'

const session = api.session as unknown as ReturnType<typeof vi.fn>
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
  actionsEnabled: true,
  passkeyAllowed: false,
  mfaAllowed: false,
  mfaEnabled: false,
}

afterEach(() => {
  cleanup()
  useStore.setState({ authUser: null, authIsPower: false, authIsDeveloper: false, authIsAdmin: false })
  vi.clearAllMocks()
})

async function renderApp() {
  await act(async () => {
    render(<ActionsApp />)
    await new Promise((res) => setTimeout(res))
    await Promise.allSettled(loginViewMocks.flatMap((m) => m.mock.results.map((r) => r.value)))
  })
}

describe('ActionsApp', () => {
  it('shows the sign-in screen when there is no session', async () => {
    session.mockResolvedValue({ ...SESSION_BASE })
    await renderApp()
    await waitFor(() => expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy())
  })

  it('renders the builder body for a developer (left-panel sections, not just the logo)', async () => {
    session.mockResolvedValue({ ...SESSION_BASE, authenticated: true, username: 'dev', isDeveloper: true })
    await renderApp()
    // The left-panel section headers prove the sidebar rendered beyond the header logo.
    await waitFor(() => expect(screen.getByText('Connections')).toBeTruthy())
    expect(screen.getByText('Projects')).toBeTruthy()
    // The shared identity/auth footer is pinned at the bottom (role shown).
    expect(screen.getByText(/\(Developer\)/)).toBeTruthy()
  })

  it('denies a signed-in user without the role', async () => {
    session.mockResolvedValue({ ...SESSION_BASE, authenticated: true, username: 'plain' })
    await renderApp()
    await waitFor(() => expect(screen.getByText(/Access denied/i)).toBeTruthy())
  })
})
