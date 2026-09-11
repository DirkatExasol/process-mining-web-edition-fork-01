/** Passkey self-management for the signed-in user: list the passkeys registered
 *  to this account, add a new one (Touch ID / Windows Hello / security key), or
 *  remove one. Only reachable when the admin has enabled passkeys for the user. */

import { useEffect, useState } from 'react'
import {
  deletePasskey,
  enrollPasskey,
  listPasskeys,
  passkeyDomainValid,
  passkeyErrorMessage,
  passkeysSupported,
  PASSKEY_DOMAIN_HINT,
  type PasskeyInfo,
} from '../passkey'
import { Sheet, Spinner } from './ui'

export function PasskeysSheet({ onClose }: { onClose: () => void }) {
  const [creds, setCreds] = useState<PasskeyInfo[] | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const domainOk = passkeyDomainValid()

  const reload = async () => {
    try {
      const { credentials } = await listPasskeys()
      setCreds(credentials)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setCreds([])
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  const add = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await enrollPasskey(name.trim() || 'Passkey')
      setName('')
      await reload()
    } catch (e) {
      // A user-cancelled ceremony is not worth surfacing as an error.
      if (e instanceof DOMException && (e.name === 'NotAllowedError' || e.name === 'AbortError')) {
        // stay silent
      } else {
        setError(passkeyErrorMessage(e))
      }
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: string) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await deletePasskey(id)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet title="Passkeys" icon="🔑" onClose={onClose}>
      <div className="col" style={{ gap: 14 }}>
        <p className="t-caption fg-secondary" style={{ margin: 0 }}>
          Passkeys let you sign in with Touch ID, Windows Hello, or a security key
          instead of your password. Your password still works as a fallback.
        </p>

        {!passkeysSupported() && (
          <div className="t-footnote fg-secondary">
            This browser does not support passkeys.
          </div>
        )}

        {passkeysSupported() && !domainOk && (
          <div
            className="t-footnote"
            style={{
              padding: '8px 10px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(255,159,10,0.12)',
              border: '1px solid rgba(255,159,10,0.32)',
              color: 'var(--orange)',
            }}
          >
            {PASSKEY_DOMAIN_HINT}
          </div>
        )}

        {error && (
          <div
            className="t-footnote"
            style={{
              padding: '8px 10px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(255,59,48,0.12)',
              border: '1px solid rgba(255,59,48,0.32)',
              color: 'var(--red)',
            }}
          >
            {error}
          </div>
        )}

        {creds === null ? (
          <div className="row" style={{ gap: 8 }}>
            <Spinner /> <span className="t-caption fg-secondary">Loading…</span>
          </div>
        ) : creds.length === 0 ? (
          <div className="t-caption fg-secondary">No passkeys registered yet.</div>
        ) : (
          <div className="col" style={{ gap: 6 }}>
            {creds.map((c) => (
              <div
                key={c.id}
                className="row"
                style={{
                  gap: 8,
                  alignItems: 'center',
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-fill)',
                }}
              >
                <span aria-hidden>🔑</span>
                <div className="col" style={{ gap: 0, minWidth: 0, lineHeight: 1.2 }}>
                  <span className="t-caption truncate" title={c.name}>
                    {c.name || 'Passkey'}
                  </span>
                  <span className="t-caption2 fg-tertiary">
                    Added {new Date(c.createdAt).toLocaleString()}
                  </span>
                </div>
                <span className="spacer" />
                <button
                  className="btn small"
                  disabled={busy}
                  onClick={() => void remove(c.id)}
                  title="Remove this passkey"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}

        {passkeysSupported() && domainOk && (
          <div className="row" style={{ gap: 8 }}>
            <input
              className="text-input"
              placeholder="Name (e.g. MacBook Touch ID)"
              value={name}
              disabled={busy}
              onChange={(e) => setName(e.target.value)}
              style={{ flex: 1 }}
            />
            <button
              className="btn prominent"
              disabled={busy}
              onClick={() => void add()}
              style={{ whiteSpace: 'nowrap' }}
            >
              {busy && <Spinner />} Add a passkey
            </button>
          </div>
        )}
      </div>
    </Sheet>
  )
}
