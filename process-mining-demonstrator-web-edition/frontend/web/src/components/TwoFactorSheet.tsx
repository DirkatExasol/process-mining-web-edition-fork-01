/** Two-factor (TOTP) self-management for the signed-in user: set up an
 *  authenticator app, view/regenerate recovery codes, or turn it off. Only
 *  reachable when the admin has enabled two-factor for the account. */

import { useEffect, useState } from 'react'
import {
  mfaDisable,
  mfaRegenerateRecovery,
  mfaSetupBegin,
  mfaSetupFinish,
  mfaStatus,
  type MfaSetup,
  type MfaStatus,
} from '../mfa'
import { Sheet, Spinner } from './ui'

export function TwoFactorSheet({ onClose }: { onClose: () => void }) {
  const [status, setStatus] = useState<MfaStatus | null>(null)
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [code, setCode] = useState('')
  const [recovery, setRecovery] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Turning off 2FA requires the current code — this holds the "confirm off" form.
  const [disabling, setDisabling] = useState(false)
  const [disableCode, setDisableCode] = useState('')

  const reload = async () => {
    try {
      setStatus(await mfaStatus())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  const begin = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      setSetup(await mfaSetupBegin())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const finish = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy || !code.trim()) return
    setBusy(true)
    setError(null)
    try {
      const codes = await mfaSetupFinish(code.trim())
      setSetup(null)
      setCode('')
      setRecovery(codes)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const regenerate = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      setRecovery(await mfaRegenerateRecovery())
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const turnOff = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy || !disableCode.trim()) return
    setBusy(true)
    setError(null)
    try {
      await mfaDisable(disableCode.trim())
      setSetup(null)
      setRecovery(null)
      setDisabling(false)
      setDisableCode('')
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const copyRecovery = () => {
    if (recovery) void navigator.clipboard?.writeText(recovery.join('\n'))
  }

  return (
    <Sheet title="Two-factor authentication" icon="🔒" onClose={onClose}>
      <div className="col" style={{ gap: 14 }}>
        <p className="t-caption fg-secondary" style={{ margin: 0 }}>
          Add a one-time code from an authenticator app (Google Authenticator, 1Password,
          Authy…) on top of your password. Your password still signs you in — the code is
          an extra step.
        </p>

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

        {/* Newly generated recovery codes — shown once, right after setup/regenerate. */}
        {recovery && (
          <div className="col" style={{ gap: 8 }}>
            <span className="t-caption" style={{ fontWeight: 600 }}>
              Save your recovery codes
            </span>
            <span className="t-caption2 fg-secondary">
              Each works once if you lose your authenticator. Store them somewhere safe —
              they won’t be shown again.
            </span>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 6,
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg-fill)',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: 13,
              }}
            >
              {recovery.map((c) => (
                <span key={c}>{c}</span>
              ))}
            </div>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn small" onClick={copyRecovery}>
                Copy codes
              </button>
              <button className="btn small" onClick={() => setRecovery(null)}>
                Done
              </button>
            </div>
          </div>
        )}

        {status === null ? (
          <div className="row" style={{ gap: 8 }}>
            <Spinner /> <span className="t-caption fg-secondary">Loading…</span>
          </div>
        ) : setup ? (
          // ── Enrolment in progress ─────────────────────────────────────────
          <form className="col" style={{ gap: 12 }} onSubmit={finish}>
            <span className="t-caption fg-secondary">
              Scan this with your authenticator app, then enter the 6-digit code it shows.
            </span>
            <div
              style={{ alignSelf: 'center', width: 180, height: 180, background: '#fff', padding: 8, borderRadius: 8 }}
              // The QR SVG is generated by our own server from the enrolment URI.
              dangerouslySetInnerHTML={{ __html: setup.qrSvg }}
            />
            <span className="t-caption2 fg-tertiary" style={{ textAlign: 'center', wordBreak: 'break-all' }}>
              Can’t scan? Enter this key manually: <strong>{setup.secret}</strong>
            </span>
            <input
              className="text-input"
              value={code}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6-digit code"
              onChange={(e) => setCode(e.target.value)}
            />
            <div className="row" style={{ gap: 8 }}>
              <button className="btn prominent" type="submit" disabled={busy || !code.trim()} style={{ flex: 1 }}>
                {busy && <Spinner />} Confirm
              </button>
              <button className="btn" type="button" disabled={busy} onClick={() => { setSetup(null); setCode('') }}>
                Cancel
              </button>
            </div>
          </form>
        ) : status.enabled ? (
          // ── Already enrolled ──────────────────────────────────────────────
          !recovery && (
            <div className="col" style={{ gap: 10 }}>
              <div
                className="row"
                style={{
                  gap: 8,
                  alignItems: 'center',
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-fill)',
                }}
              >
                <span aria-hidden>✅</span>
                <span className="t-caption">
                  Two-factor is on. {status.recoveryRemaining} recovery code
                  {status.recoveryRemaining === 1 ? '' : 's'} left.
                </span>
              </div>
              {disabling ? (
                <form className="col" style={{ gap: 8 }} onSubmit={turnOff}>
                  <span className="t-caption2 fg-secondary">
                    Enter your current code (or a recovery code) to turn two-factor off.
                  </span>
                  <div className="row" style={{ gap: 8 }}>
                    <input
                      className="text-input"
                      value={disableCode}
                      autoFocus
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="Current code"
                      onChange={(e) => setDisableCode(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <button className="btn small" type="submit" disabled={busy || !disableCode.trim()}>
                      {busy && <Spinner />} Confirm off
                    </button>
                    <button
                      className="btn small"
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setDisabling(false)
                        setDisableCode('')
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <div className="row" style={{ gap: 8 }}>
                  <button className="btn small" disabled={busy} onClick={() => void regenerate()}>
                    Regenerate recovery codes
                  </button>
                  <button className="btn small" disabled={busy} onClick={() => setDisabling(true)}>
                    Turn off
                  </button>
                </div>
              )}
            </div>
          )
        ) : (
          // ── Not yet enrolled ──────────────────────────────────────────────
          !recovery && (
            <button className="btn prominent" disabled={busy} onClick={() => void begin()}>
              {busy && <Spinner />} Set up authenticator
            </button>
          )
        )}
      </div>
    </Sheet>
  )
}
