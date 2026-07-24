/** LoginView tests — the directory-server availability indicator, which appears
 *  only when a directory is configured and reflects its reachability. */

import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    directoryStatus: vi.fn(),
    login: vi.fn(),
    session: vi.fn(),
    logout: vi.fn(),
    listConnections: vi.fn(),
    connectionStatus: vi.fn(),
    listManageableConnections: vi.fn(),
    listAssignableUsers: vi.fn(),
  },
}))

import { api } from '../api'
import { LoginView } from './LoginView'

const directoryStatus = api.directoryStatus as unknown as ReturnType<typeof vi.fn>

describe('LoginView directory indicator', () => {
  it('shows a green "available" indicator when the directory is reachable', async () => {
    directoryStatus.mockResolvedValue({ configured: true, available: true })
    render(<LoginView onSignedIn={() => {}} />)
    const label = await screen.findByText('Directory server available')
    // The label sits next to an LED dot (its previous sibling).
    const dot = label.previousElementSibling as HTMLElement
    expect(dot).toBeTruthy()
    expect(dot.style.background).toContain('var(--green)')
  })

  it('shows a red "unavailable" indicator when the directory does not answer', async () => {
    directoryStatus.mockResolvedValue({ configured: true, available: false })
    render(<LoginView onSignedIn={() => {}} />)
    const label = await screen.findByText('Directory server unavailable')
    const dot = label.previousElementSibling as HTMLElement
    expect(dot.style.background).toContain('var(--red)')
  })

  it('renders nothing when no directory is configured', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    render(<LoginView onSignedIn={() => {}} />)
    // Give the effect a chance to resolve, then assert the indicator is absent.
    await waitFor(() => expect(directoryStatus).toHaveBeenCalled())
    expect(screen.queryByText(/Directory server/)).toBeNull()
  })
})
