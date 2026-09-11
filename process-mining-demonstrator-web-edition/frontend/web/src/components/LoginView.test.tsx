/** LoginView tests — the directory-server availability indicator, which appears
 *  only when a directory is configured and reflects its reachability. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  ApiError: class ApiError extends Error {},
  api: {
    directoryStatus: vi.fn(),
    licenseStatus: vi.fn(),
    loginAppearance: vi.fn(),
    login: vi.fn(),
    verifyMfa: vi.fn(),
    mfaEnrollBegin: vi.fn(),
    mfaEnrollFinish: vi.fn(),
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
  passkeysUsable: vi.fn(() => true),
  authenticateWithPasskey: vi.fn(),
}))

import { api } from '../api'
import { authenticateWithPasskey, passkeysUsable } from '../passkey'
import { useStore } from '../store'
import { LoginView } from './LoginView'

const login = api.login as unknown as ReturnType<typeof vi.fn>
const verifyMfa = api.verifyMfa as unknown as ReturnType<typeof vi.fn>

// Some tests leave a two-factor step pending on the shared store; reset it so the next
// test starts on the username/password form. Wrap it in act(): cancelMfa() mutates the
// store, which synchronously re-renders the still-mounted LoginView (it subscribes via
// useStore), and that update must be wrapped or React logs a spurious act(...) warning.
afterEach(() => act(() => useStore.getState().cancelMfa()))

const directoryStatus = api.directoryStatus as unknown as ReturnType<typeof vi.fn>
const licenseStatus = api.licenseStatus as unknown as ReturnType<typeof vi.fn>
// LoginView gates the passkey button on passkeysUsable() (browser + valid host).
const usable = passkeysUsable as unknown as ReturnType<typeof vi.fn>
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

// LoginView fires three independent effects on mount (loginAppearance, directoryStatus,
// licenseStatus), each resolving into a setState. A test that only awaits one of them
// would let the other two update state outside act(), which React flags. Render inside an
// async act() so all three settle before the test proceeds — no "not wrapped in act(...)".
const loginAppearance = api.loginAppearance as unknown as ReturnType<typeof vi.fn>

// LoginView fires three fire-and-forget mount effects (loginAppearance, directoryStatus,
// licenseStatus), each resolving a promise into a setState. Render inside act() and, still
// inside it, await the exact promises those effects returned — each effect's
// `.then(setState)` is registered before this await, so it resolves first and lands while
// act is active. Rendering outside act would let those resolutions escape at the first
// `await`, before act engages, which is what logs "update … not wrapped in act(...)".
async function renderLogin(onSignedIn: () => void = () => {}) {
  let result: ReturnType<typeof render>
  await act(async () => {
    result = render(<LoginView onSignedIn={onSignedIn} />)
    await Promise.allSettled(
      [loginAppearance, directoryStatus, licenseStatus].flatMap((m) =>
        m.mock.results.map((r) => r.value),
      ),
    )
  })
  return result!
}

describe('LoginView directory indicator', () => {
  it('shows a green "available" indicator when the directory is reachable', async () => {
    directoryStatus.mockResolvedValue({ configured: true, available: true })
    await renderLogin()
    const label = await screen.findByText('Directory server available')
    // The label sits next to an LED dot (its previous sibling).
    const dot = label.previousElementSibling as HTMLElement
    expect(dot).toBeTruthy()
    expect(dot.style.background).toContain('var(--green)')
  })

  it('shows a red "unavailable" indicator when the directory does not answer', async () => {
    directoryStatus.mockResolvedValue({ configured: true, available: false })
    await renderLogin()
    const label = await screen.findByText('Directory server unavailable')
    const dot = label.previousElementSibling as HTMLElement
    expect(dot.style.background).toContain('var(--red)')
  })

  it('renders nothing when no directory is configured', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    await renderLogin()
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
    await renderLogin()
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
    await renderLogin()
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
    await renderLogin()
    await screen.findByText('No License installed')
  })

  it('shows no demo label when a license is installed', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    licenseStatus.mockResolvedValue({
      state: 'valid',
      demoMode: false,
      remainingSeconds: null,
    })
    await renderLogin()
    await waitFor(() => expect(licenseStatus).toHaveBeenCalled())
    expect(screen.queryByText(/Demo Mode/)).toBeNull()
  })
})

describe('LoginView passkey button', () => {
  it('is hidden when passkeys are not usable here (unsupported browser or IP host)', async () => {
    // passkeysUsable() is false for both an unsupported browser and a bare-IP host.
    usable.mockReturnValue(false)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    await renderLogin()
    await waitFor(() => expect(directoryStatus).toHaveBeenCalled())
    expect(screen.queryByText(/Sign with Passkey/)).toBeNull()
    usable.mockReturnValue(true) // restore for later tests
  })

  it('stays disabled until a username is entered', async () => {
    usable.mockReturnValue(true)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    await renderLogin()
    const btn = (await screen.findByText(/Sign with Passkey/)).closest('button')!
    expect(btn.disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    expect(btn.disabled).toBe(false)
  })

  it('drives the passkey ceremony and signs in on success', async () => {
    usable.mockReturnValue(true)
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
    await renderLogin(onSignedIn)
    const btn = (await screen.findByText(/Sign with Passkey/)).closest('button')!
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.click(btn)
    await waitFor(() => expect(authPasskey).toHaveBeenCalledWith('alice'))
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })

  it('shows an error when the passkey ceremony fails', async () => {
    usable.mockReturnValue(true)
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    authPasskey.mockRejectedValue(new Error('Passkey sign-in failed.'))
    const onSignedIn = vi.fn()
    await renderLogin(onSignedIn)
    const btn = (await screen.findByText(/Sign with Passkey/)).closest('button')!
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.click(btn)
    await screen.findByText('Passkey sign-in failed.')
    expect(onSignedIn).not.toHaveBeenCalled()
  })
})

describe('LoginView two-factor step', () => {
  const user = {
    username: 'alice',
    isAdmin: false,
    isPower: false,
    displayName: null,
    authSource: null,
    passkeyAllowed: false,
    mfaAllowed: true,
    mfaEnabled: true,
  }

  it('shows the code step after a password login that needs a second factor', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    login.mockResolvedValue({ mfaRequired: true, username: 'alice' })
    const onSignedIn = vi.fn()
    await renderLogin(onSignedIn)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    // The password form gives way to the code field; not signed in yet.
    await screen.findByLabelText('Authentication code')
    expect(onSignedIn).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Password')).toBeNull()
  })

  it('verifies the code and signs in', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    login.mockResolvedValue({ mfaRequired: true, username: 'alice' })
    verifyMfa.mockResolvedValue(user)
    const onSignedIn = vi.fn()
    await renderLogin(onSignedIn)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    const codeField = await screen.findByLabelText('Authentication code')
    fireEvent.change(codeField, { target: { value: '123456' } })
    fireEvent.click(screen.getByText(/Verify/))
    await waitFor(() => expect(verifyMfa).toHaveBeenCalledWith('123456'))
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })

  it('lets the user go back to the password form', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    login.mockResolvedValue({ mfaRequired: true, username: 'alice' })
    await renderLogin()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))
    await screen.findByLabelText('Authentication code')
    fireEvent.click(screen.getByText('Back'))
    // Back to the username/password form.
    await screen.findByLabelText('Password')
  })
})

describe('LoginView forced 2FA enrolment', () => {
  const enrollBegin = api.mfaEnrollBegin as unknown as ReturnType<typeof vi.fn>
  const enrollFinish = api.mfaEnrollFinish as unknown as ReturnType<typeof vi.fn>

  it('forces enrolment, then shows recovery codes and signs in', async () => {
    directoryStatus.mockResolvedValue({ configured: false, available: false })
    login.mockResolvedValue({ mfaSetupRequired: true, username: 'alice' })
    enrollBegin.mockResolvedValue({
      secret: 'JBSWY3DPEHPK3PXP',
      otpauthUri: 'otpauth://totp/x',
      qrSvg: '<svg data-testid="qr"></svg>',
    })
    enrollFinish.mockResolvedValue({
      username: 'alice',
      isAdmin: false,
      isPower: false,
      displayName: null,
      authSource: null,
      passkeyAllowed: false,
      mfaAllowed: true,
      mfaEnabled: true,
      recoveryCodes: ['aaaa-bbbb', 'cccc-dddd'],
    })
    const onSignedIn = vi.fn()
    await renderLogin(onSignedIn)

    // Password step → the server says 2FA must be set up first.
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /Sign in/ }))

    // The QR + code field appear; not signed in yet.
    const codeField = await screen.findByLabelText('6-digit code')
    await waitFor(() => expect(enrollBegin).toHaveBeenCalled())
    expect(screen.getByText(/JBSWY3DPEHPK3PXP/)).toBeTruthy()
    expect(onSignedIn).not.toHaveBeenCalled()

    // Confirm the code → recovery codes shown, still on the login screen.
    fireEvent.change(codeField, { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirm/ }))
    await screen.findByText(/save your recovery codes/i)
    expect(screen.getByText('aaaa-bbbb')).toBeTruthy()
    expect(onSignedIn).not.toHaveBeenCalled() // not until "Continue"

    // Continue → enter the app.
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }))
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })
})
