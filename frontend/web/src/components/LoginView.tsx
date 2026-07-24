/** Main-app sign-in gate. Authenticates against the user store the admin manages
 *  (only enabled users get in). Shown when the admin requires login and the
 *  visitor has no valid session. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import { Logo } from './Logo'
import { Spinner } from './ui'

export function LoginView({ onSignedIn }: { onSignedIn: () => void }) {
  const store = useStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Directory (LDAP) availability — only rendered when a directory is configured.
  const [directory, setDirectory] = useState<{
    configured: boolean
    available: boolean
  } | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .directoryStatus()
      .then((s) => !cancelled && setDirectory(s))
      .catch(() => !cancelled && setDirectory(null))
    return () => {
      cancelled = true
    }
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || busy) return
    setBusy(true)
    setError(null)
    const message = await store.login(username.trim(), password)
    setBusy(false)
    if (message) {
      setError(message)
      setPassword('')
    } else {
      onSignedIn()
    }
  }

  return (
    <div
      className="scrim"
      style={{ background: 'var(--bg-grouped)', position: 'fixed', inset: 0 }}
    >
      <form
        className="splash"
        style={{ gap: 16, cursor: 'default' }}
        onSubmit={submit}
      >
        <div className="brand-logo" style={{ width: 64, height: 64 }}>
          <Logo />
        </div>
        <div className="col" style={{ gap: 2, alignItems: 'center' }}>
          <span className="t-title3">Process Mining Demonstrator</span>
          <span className="t-caption fg-secondary">Sign in to continue</span>
        </div>

        {store.signedOutForInactivity && !error && (
          <div
            className="t-footnote"
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(255,159,10,0.12)',
              border: '1px solid rgba(255,159,10,0.32)',
              color: 'var(--orange)',
            }}
          >
            You were signed out due to inactivity.
          </div>
        )}

        {error && (
          <div
            className="t-footnote"
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(255,59,48,0.12)',
              border: '1px solid rgba(255,59,48,0.32)',
              color: 'var(--red)',
            }}
          >
            {error}
          </div>
        )}

        <div className="field" style={{ width: '100%' }}>
          <label className="field-label" htmlFor="login-username">
            Username
          </label>
          <input
            id="login-username"
            className="text-input"
            value={username}
            autoFocus
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>

        <div className="field" style={{ width: '100%' }}>
          <label className="field-label" htmlFor="login-password">
            Password
          </label>
          <input
            id="login-password"
            className="text-input"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button
          className="btn prominent"
          type="submit"
          disabled={busy || !username.trim()}
          style={{ width: '100%', padding: '10px', fontSize: 15 }}
        >
          {busy && <Spinner />} Sign in
        </button>

        {directory?.configured && (
          <div
            className="row"
            style={{ gap: 6, alignItems: 'center', alignSelf: 'center' }}
            title={
              directory.available
                ? 'The user directory server responded to a connection test.'
                : 'The user directory server did not respond to a connection test.'
            }
          >
            <span
              aria-hidden
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                flex: '0 0 auto',
                background: directory.available ? 'var(--green)' : 'var(--red)',
                boxShadow: `0 0 6px ${
                  directory.available ? 'var(--green)' : 'var(--red)'
                }`,
              }}
            />
            <span className="t-caption2 fg-secondary">
              Directory server {directory.available ? 'available' : 'unavailable'}
            </span>
          </div>
        )}
      </form>
    </div>
  )
}
