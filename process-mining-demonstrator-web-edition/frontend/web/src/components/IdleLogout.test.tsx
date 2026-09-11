/** IdleLogout — signs the user out after the configured idle window. The integration
 *  console passes alwaysRequireAuth so it applies even when the global requireLogin is
 *  off (the console is always role-gated). */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'
import { IdleLogout } from './IdleLogout'
import { useStore } from '../store'

const logout = vi.fn(async () => {})

beforeEach(() => {
  vi.useFakeTimers()
  logout.mockClear()
  useStore.setState({
    authUser: 'dev',
    requireLogin: true,
    idleTimeoutMins: 1, // 60 s idle window
    logout,
  } as never)
})

afterEach(() => {
  vi.useRealTimers()
})

async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms)
  })
}

describe('IdleLogout', () => {
  it('signs out after the idle window elapses', async () => {
    render(<IdleLogout />)
    await advance(61_000)
    expect(logout).toHaveBeenCalledWith({ inactivity: true })
  })

  it('does not sign out while the user stays active', async () => {
    render(<IdleLogout />)
    // Poke activity before the window closes, twice.
    await advance(40_000)
    act(() => window.dispatchEvent(new Event('keydown')))
    await advance(40_000)
    act(() => window.dispatchEvent(new Event('keydown')))
    await advance(40_000)
    expect(logout).not.toHaveBeenCalled()
  })

  it('is disabled on the main app when requireLogin is off', async () => {
    useStore.setState({ requireLogin: false } as never)
    render(<IdleLogout />)
    await advance(61_000)
    expect(logout).not.toHaveBeenCalled()
  })

  it('still fires with alwaysRequireAuth even when requireLogin is off (integration console)', async () => {
    useStore.setState({ requireLogin: false } as never)
    render(<IdleLogout alwaysRequireAuth />)
    await advance(61_000)
    expect(logout).toHaveBeenCalledWith({ inactivity: true })
  })

  it('is disabled when no idle timeout is configured', async () => {
    useStore.setState({ idleTimeoutMins: 0 } as never)
    render(<IdleLogout alwaysRequireAuth />)
    await advance(120_000)
    expect(logout).not.toHaveBeenCalled()
  })
})
