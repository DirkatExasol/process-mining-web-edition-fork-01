/** The signed-in identity + authentication footer shared by the main app sidebar
 *  and the integration console sidebar: a name/role row and a row of
 *  authentication controls (two-factor, passkeys) with sign-out. */

import { useState } from 'react'
import { useStore } from '../store'
import { PasskeysSheet } from './PasskeysSheet'
import { TwoFactorSheet } from './TwoFactorSheet'
import { Divider } from './ui'

export function AuthFooter() {
  const store = useStore()
  const [showPasskeys, setShowPasskeys] = useState(false)
  const [showTwoFactor, setShowTwoFactor] = useState(false)

  if (!store.authUser) return null

  const role = store.authIsAdmin
    ? 'Admin'
    : store.authIsPower
      ? 'Power user'
      : store.authIsDeveloper
        ? 'Developer'
        : 'User'

  return (
    <>
      <Divider />
      <div className="col" style={{ gap: 8 }}>
        {/* First row: who is signed in, with the role in parentheses. */}
        <div className="theme-bar" style={{ gap: 8 }}>
          <span aria-hidden>👤</span>
          <span
            className="t-caption fg-secondary truncate"
            title={
              store.authDisplayName
                ? `${store.authDisplayName} (${store.authUser})`
                : store.authUser
            }
          >
            {store.authDisplayName || store.authUser}
          </span>
          <span className="t-caption2 fg-tertiary truncate">({role})</span>
        </div>
        {/* Second row: authentication management + sign out. */}
        <div className="theme-bar" style={{ gap: 8 }}>
          {store.authMfaAllowed && (
            <button
              className="btn small"
              title="Manage two-factor authentication"
              onClick={() => setShowTwoFactor(true)}
            >
              🔒 Two-factor
            </button>
          )}
          {store.authPasskeyAllowed && (
            <button
              className="btn small"
              title="Manage passkeys for this account"
              onClick={() => setShowPasskeys(true)}
            >
              🔑 Passkeys
            </button>
          )}
          <span className="spacer" />
          <button className="btn small" title="Sign out" onClick={() => void store.logout()}>
            ⏻ Sign out
          </button>
        </div>
      </div>

      {showPasskeys && <PasskeysSheet onClose={() => setShowPasskeys(false)} />}
      {showTwoFactor && <TwoFactorSheet onClose={() => setShowTwoFactor(false)} />}
    </>
  )
}
