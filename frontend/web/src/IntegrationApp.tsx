/** Root shell for the integration / data-source console — a separate surface
 *  (admin port + 10) that reuses the main app's sign-in flow but is reachable only
 *  by power users, developers and admins. The data-source configuration UI is built
 *  on top of this scaffold in later stages. */

import { useEffect, useState } from 'react'
import { IntegrationSidebar } from './components/IntegrationSidebar'
import { IntegrationStatusPanel } from './components/IntegrationStatusPanel'
import { LoginView } from './components/LoginView'
import { Logo } from './components/Logo'
import { Spinner } from './components/ui'
import { hydrateSettings, useSetting } from './settings'
import { useStore } from './store'
import './styles.css'

/** Applies the `app.theme` preference (shared with the main app), following the OS
 *  when set to "system". The saved value is hydrated after sign-in; until then this
 *  falls back to the OS scheme. */
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

export function IntegrationApp() {
  const store = useStore()
  const [ready, setReady] = useState(false)

  // After sign-in (gated APIs): load the per-user settings (theme, etc.) and the
  // user's assigned data-source connections.
  const initAfterAuth = () => {
    void hydrateSettings()
    void store.refreshConnections()
  }

  useEffect(() => {
    void (async () => {
      await store.checkSession()
      const s = useStore.getState()
      if (s.authUser && (s.authIsPower || s.authIsDeveloper || s.authIsAdmin)) {
        initAfterAuth()
      }
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

  // The integration console always requires sign-in (it is role-gated), regardless
  // of the global "require login" setting. The forced-2FA-enrolment step keeps the
  // login screen up until it completes, matching the main app.
  if (!store.authUser || store.mfaSetupPending) {
    return (
      <>
        <ThemeSync />
        <LoginView onSignedIn={initAfterAuth} />
      </>
    )
  }

  // Defence in depth: the server refuses a login (and drops the session) for anyone
  // without the role, so this is only reached if the role is revoked mid-session.
  const authorized = store.authIsPower || store.authIsDeveloper || store.authIsAdmin
  if (!authorized) {
    return (
      <>
        <ThemeSync />
        <div className="center-fill" style={{ height: '100%', gap: 12 }}>
          <Logo />
          <h2 style={{ margin: 0 }}>Access denied</h2>
          <p className="fg-secondary" style={{ maxWidth: 420, textAlign: 'center' }}>
            The integration console is available to power users and developers only. Ask
            an administrator to grant you the Developer role.
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
      <div className="app">
        <IntegrationSidebar />
        <main className="integration-body">
          <IntegrationStatusPanel />
        </main>
      </div>
    </>
  )
}
