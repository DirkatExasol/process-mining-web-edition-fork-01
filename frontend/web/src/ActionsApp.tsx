/** Root shell for the Actions authoring surface — a separate surface (admin port + 20)
 *  that reuses the main app's sign-in flow but is reachable only by developers and
 *  admins. It reuses the app store to connect to a database and load a project graph,
 *  then edits the saved actions for that (connection, project). */

import { useEffect, useState } from 'react'
import { ActionsBuilder } from './components/ActionsBuilder'
import { HelpPanel } from './components/HelpPanel'
import { IdleLogout } from './components/IdleLogout'
import { LoginView } from './components/LoginView'
import { Logo } from './components/Logo'
import { Spinner } from './components/ui'
import { hydrateSettings, useSetting } from './settings'
import { useStore } from './store'
import './styles.css'

/** Applies the shared `app.theme` preference, following the OS when set to "system". */
function ThemeSync() {
  const [theme] = useSetting<string>('app.theme')
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const resolved = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme
      document.documentElement.dataset.theme = resolved
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])
  return null
}

export function ActionsApp() {
  const store = useStore()
  const [ready, setReady] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

  const initAfterAuth = () => {
    void hydrateSettings()
    void store.refreshConnections()
  }

  useEffect(() => {
    void (async () => {
      await store.checkSession()
      const s = useStore.getState()
      if (s.authUser && (s.authIsDeveloper || s.authIsAdmin)) initAfterAuth()
      setReady(true)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!ready) {
    return (
      <>
        <ThemeSync />
        <div className="center-fill" style={{ height: '100%' }}>
          <Spinner large />
          <span>Starting…</span>
        </div>
      </>
    )
  }

  // Always role-gated, so it requires sign-in regardless of the global setting.
  if (!store.authUser || store.mfaSetupPending) {
    return (
      <>
        <ThemeSync />
        <LoginView subtitle="Action Designer" onSignedIn={initAfterAuth} />
      </>
    )
  }

  // Defence in depth: the server refuses a login for anyone without the role, so this
  // is only reached if the role is revoked mid-session.
  const authorized = store.authIsDeveloper || store.authIsAdmin
  if (!authorized) {
    return (
      <>
        <ThemeSync />
        <div className="center-fill" style={{ height: '100%', gap: 12 }}>
          <span className="brand-logo">
            <Logo />
          </span>
          <h2 style={{ margin: 0 }}>Access denied</h2>
          <p className="fg-secondary" style={{ maxWidth: 420, textAlign: 'center' }}>
            Actions are authored by developers and administrators only. Ask an administrator to
            grant you the Developer role.
          </p>
          <button className="btn" onClick={() => void store.logout()}>
            ⏻ Sign out
          </button>
        </div>
      </>
    )
  }

  return (
    <>
      <ThemeSync />
      <ActionsBuilder onShowHelp={() => setShowHelp(true)} />
      {showHelp && <HelpPanel onClose={() => setShowHelp(false)} />}
      <IdleLogout alwaysRequireAuth />
    </>
  )
}
