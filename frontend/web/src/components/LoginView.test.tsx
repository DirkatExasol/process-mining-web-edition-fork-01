/** LoginView tests — the directory-server availability indicator, which appears
 *  only when a directory is configured and reflects its reachability. */

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    directoryStatus: vi.fn(),
    licenseStatus: vi.fn(),
    loginAppearance: vi.fn(),
    login: vi.fn(),
    session: vi.fn(),
    logout: vi.fn(),
    listConnections: vi.fn(),
    connectionStatus: vi.fn(),
    listManageableConnections: vi.fn(),
    listAssignableUsers: vi.fn(),
  },
}))

vi.mock('../passkey', () => ({
  passkeysSupported: vi.fn(() => true),
  authenticateWithPasskey: vi.fn(),
}))

import { api } from '../api'
import { authenticateWithPasskey, passkeysSupported } from '../passkey'
import { LoginView } from './LoginView'

const directoryStatus = api.directoryStatus as unknown as ReturnType<typeof vi.fn>
const licenseStatus = api.licenseStatus as unknown as ReturnType<typeof vi.fn>
const supported = passkeysSupported as unknown as ReturnType<typeof vi.fn>
const authPasskey = authenticateWithPasskey as unknown as ReturnType<typeof vi.fn>

// Most tests don't care about the license label; default it to "licensed".
licenseStatus.mockResolvedValue({
  state: 'valid',
  demoMode: false,
  remainingSeconds: null,
})

// The login background is fetched on mount; default it to the theme colour.
;(api.loginAppearance as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
  type: 'default',
  color: '',
  image: '',
})

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

describe('LoginView demo-mode label', () => {
  it('shows the remaining minutes when no license is installed', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    licenseStatus.mockResolvedValue({
      state: 'missing',
      demoMode: true,
      remainingSeconds: 25 * 60 + 5, // 25m05s → rounds up to 26 min
    })
    render(<LoginView onSignedIn={() => {}} />)
    await screen.findByText(/Demo Mode/)
    expect(screen.getByText(/remaining time: 26 min/)).toBeTruthy()
  })

  it('shows "No License installed" when the demo window is spent', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    licenseStatus.mockResolvedValue({
      state: 'missing',
      demoMode: true,
      remainingSeconds: 0,
    })
    render(<LoginView onSignedIn={() => {}} />)
    await screen.findByText('No License installed')
    expect(screen.queryByText(/Demo Mode/)).toBeNull()
    expect(screen.queryByText(/remaining time/)).toBeNull()
  })

  it('shows "No License installed" for an expired license with no demo left', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    licenseStatus.mockResolvedValue({
      state: 'expired',
      demoMode: true,
      remainingSeconds: null,
    })
    render(<LoginView onSignedIn={() => {}} />)
    await screen.findByText('No License installed')
  })

  it('shows no demo label when a license is installed', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    licenseStatus.mockResolvedValue({
      state: 'valid',
      demoMode: false,
      remainingSeconds: null,
    })
    render(<LoginView onSignedIn={() => {}} />)
    await waitFor(() => expect(licenseStatus).toHaveBeenCalled())
    expect(screen.queryByText(/Demo Mode/)).toBeNull()
  })
})

describe('LoginView passkey button', () => {
  it('is hidden when the browser does not support passkeys', async () => {
    supported.mockReturnValue(false)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    render(<LoginView onSignedIn={() => {}} />)
    await waitFor(() => expect(directoryStatus).toHaveBeenCalled())
    expect(screen.queryByText(/Sign with Passkey/)).toBeNull()
    supported.mockReturnValue(true) // restore for later tests
  })

  it('stays disabled until a username is entered', async () => {
    supported.mockReturnValue(true)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    render(<LoginView onSignedIn={() => {}} />)
    const btn = (await screen.findByText(/Sign with Passkey/)).closest('button')!
    expect(btn.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    expect(btn.disabled).toBe(false)
  })

  it('drives the passkey ceremony and signs in on success', async () => {
    supported.mockReturnValue(true)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    authPasskey.mockResolvedValue({
      username: 'alice',
      isAdmin: false,
      isPower: false,
      displayName: null,
      authSource: null,
      passkeyAllowed: true,
    })
    const onSignedIn = vi.fn()
    render(<LoginView onSignedIn={onSignedIn} />)
    const btn = (await screen.findByText(/Sign with Passkey/)).closest('button')!
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.click(btn)
    await waitFor(() => expect(authPasskey).toHaveBeenCalledWith('alice'))
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })

  it('shows an error when the passkey ceremony fails', async () => {
    supported.mockReturnValue(true)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    authPasskey.mockRejectedValue(new Error('Passkey sign-in failed.'))
    const onSignedIn = vi.fn()
    render(<LoginView onSignedIn={onSignedIn} />)
    const btn = (await screen.findByText(/Sign with Passkey/)).closest('button')!
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.click(btn)
    await screen.findByText('Passkey sign-in failed.')
    expect(onSignedIn).not.toHaveBeenCalled()
  })
})
