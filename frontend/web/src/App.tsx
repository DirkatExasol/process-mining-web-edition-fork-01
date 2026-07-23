/** Root shell — port of ContentView.swift: split view, theme, alert host,
 *  launch splash, legal gate and the floating help panel. */

import { useCallback, useEffect, useState } from 'react'
import { HelpPanel } from './components/HelpPanel'
import { LegalGate, SplashScreen } from './components/Gates'
import { LoginView } from './components/LoginView'
import { Sidebar } from './components/Sidebar'
import { Spinner } from './components/ui'
import { hydrateSettings, useSetting } from './settings'
import { useStore } from './store'
import { DetailPane } from './views/DetailPane'

export function App() {
  const store = useStore()
  const [ready, setReady] = useState(false)
  const [sidebarHidden, setSidebarHidden] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [showSplash, setShowSplash] = useState(true)

  // Loads everything that needs an authenticated session (settings live in the
  // backend and its API is gated when sign-in is required).
  const initAfterAuth = useCallback(async () => {
    await hydrateSettings()
    await store.refreshConnections()
    if (useStore.getState().connection.isConnected) {
      await useStore.getState().loadProjects()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void (async () => {
      await store.checkSession()
      const { requireLogin, authUser } = useStore.getState()
      if (!requireLogin || authUser) {
        await initAfterAuth()
      }
      setReady(true)
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ⌘/Ctrl + ? opens help, matching the Swift keyboard shortcut.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === '/' || e.key === '?')) {
        e.preventDefault()
        setShowHelp((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!ready) {
    return (
      <div className="center-fill" style={{ height: '100%' }}>
        <Spinner large />
        <span>Starting…</span>
      </div>
    )
  }

  // Sign-in gate: shown when the admin requires login and there is no session.
  if (store.requireLogin && !store.authUser) {
    return (
      <>
        <ThemeSync />
        <LoginView
          onSignedIn={() => {
            void initAfterAuth()
          }}
        />
        <AlertHost />
      </>
    )
  }

  return (
    <>
      <ThemeSync />
      <LegalGateHost>
        <div className="app">
          {!sidebarHidden && <Sidebar onCollapse={() => setSidebarHidden(true)} />}
          <DetailPane
            sidebarHidden={sidebarHidden}
            onShowSidebar={() => setSidebarHidden(false)}
            onShowHelp={() => setShowHelp(true)}
          />
        </div>
      </LegalGateHost>

      {showHelp && <HelpPanel onClose={() => setShowHelp(false)} />}
      {showSplash && <SplashScreen onClose={() => setShowSplash(false)} />}
      <AlertHost />
    </>
  )
}

/** Applies the `app.theme` preference, following the OS when set to "system". */
function ThemeSync() {
  const [theme] = useSetting<string>('app.theme')

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const resolved =
        theme === 'system' ? (media.matches ? 'dark' : 'light') : theme
      document.documentElement.dataset.theme = resolved
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  return null
}

function LegalGateHost({ children }: { children: React.ReactNode }) {
  const [accepted, setAccepted] = useSetting<boolean>('legal.accepted')
  if (!accepted) return <LegalGate onAccept={() => setAccepted(true)} />
  return <>{children}</>
}

function AlertHost() {
  const store = useStore()
  const alert = store.pendingAlert
  if (!alert) return null

  return (
    <div className="scrim" onClick={store.dismissAlert}>
      <div className="alert-box" onClick={(e) => e.stopPropagation()} role="alertdialog">
        <div className="a-body">
          <div className="a-title">{alert.title}</div>
          <div className="a-message">{alert.message}</div>
        </div>
        <div className="a-actions">
          {alert.secondaryLabel && (
            <button onClick={store.dismissAlert}>{alert.secondaryLabel}</button>
          )}
          <button
            className="emphasis"
            onClick={() => {
              store.dismissAlert()
              alert.onPrimary?.()
            }}
          >
            {alert.primaryLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
