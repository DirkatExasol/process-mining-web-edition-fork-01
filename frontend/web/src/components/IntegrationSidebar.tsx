/** Left panel for the integration console — mirrors the app sidebar: a brand
 *  header, the user's data-source connection badges, and the shared identity /
 *  authentication footer pinned at the bottom. */

import { useMemo, useState } from 'react'
import { useStore } from '../store'
import type { AssignedConnection } from '../types'
import { AuthFooter } from './AuthFooter'
import { Logo } from './Logo'
import { SectionHeader } from './SectionHeader'
import { SourcesSection } from './SourcesSection'
import { SourceTypesSection } from './SourceTypesSection'
import { ThemeBar } from './ThemeBar'
import { Divider } from './ui'

type SectionId = 'connections' | 'sources' | 'sourceTypes'

function IntegrationBrand() {
  return (
    <div className="brand-header">
      <div className="brand-logo" aria-hidden>
        <Logo />
      </div>
      <div className="col" style={{ gap: 2 }}>
        <span className="t-title3">Integration</span>
        <span className="t-caption fg-secondary">Data-source configuration</span>
      </div>
    </div>
  )
}

/** The user's assigned connections as clickable badges — click to connect /
 *  disconnect, with a live status dot on the active one (same behaviour as the
 *  main app's Connections list). */
function ConnectionBadges() {
  const store = useStore()
  const sorted = useMemo(
    () => [...store.connections].sort((a, b) => a.name.localeCompare(b.name)),
    [store.connections],
  )

  const connectOrDisconnect = async (conn: AssignedConnection) => {
    const isActive = store.connection.activeProfileId === conn.id
    if (store.connection.isConnected && isActive) {
      await store.disconnect()
      return
    }
    if (store.connection.isConnected) await store.disconnect()
    await store.connectConnection(conn)
  }

  if (!sorted.length) {
    return (
      <div className="col" style={{ gap: 6, padding: '0 4px' }}>
        <span className="t-caption fg-tertiary">
          No connections assigned to you. Ask an administrator to grant access.
        </span>
        {store.connection.lastError && (
          <span className="t-caption fg-red">{store.connection.lastError}</span>
        )}
      </div>
    )
  }

  return (
    // Show at most ~3 connection badges (each min 64px + 6px gap); scroll past that.
    <div className="card-list" style={{ maxHeight: 216 }}>
      {sorted.map((conn) => {
        const isActive = store.connection.activeProfileId === conn.id
        const isConnected = store.connection.isConnected && isActive
        return (
          <div
            key={conn.id}
            className={`card${isActive ? ' selected' : ''}`}
            style={{ minHeight: 64 }}
            onClick={() => void connectOrDisconnect(conn)}
          >
            <span
              aria-hidden
              style={{ fontSize: 17, color: isConnected ? 'var(--green)' : 'var(--accent)' }}
            >
              ⛁
            </span>
            <div className="card-body">
              <span className="card-title">{conn.name || '(unnamed)'}</span>
              {conn.comment && <span className="card-sub">{conn.comment}</span>}
              <span className="card-sub">
                Database: {conn.host || '(no host)'}:{conn.port}
              </span>
              {conn.hasLLM && (
                <span className="card-sub">LLM: {conn.llmURL || '(configured)'}</span>
              )}
            </div>
            {isActive && (
              <span
                className="status-dot"
                style={{ background: isConnected ? 'var(--green)' : 'var(--orange)' }}
                title={isConnected ? 'Connected' : 'Not connected'}
              />
            )}
          </div>
        )
      })}
      {store.connection.lastError && !store.connection.isConnected && (
        <span className="t-caption fg-red">{store.connection.lastError}</span>
      )}
    </div>
  )
}

export function IntegrationSidebar() {
  const store = useStore()
  // Accordion: at most one of the three sections is expanded at a time.
  const [openSection, setOpenSection] = useState<SectionId | null>('connections')
  const toggle = (id: SectionId) => setOpenSection((cur) => (cur === id ? null : id))

  return (
    <aside className="sidebar">
      <div className="sidebar-scroll">
        <IntegrationBrand />
        <Divider />
        <SectionHeader
          title="Connections"
          count={store.connections.length}
          open={openSection === 'connections'}
          onToggle={() => toggle('connections')}
        />
        {openSection === 'connections' && <ConnectionBadges />}
        <Divider />
        <SourcesSection open={openSection === 'sources'} onToggle={() => toggle('sources')} />
        <Divider />
        <SourceTypesSection
          open={openSection === 'sourceTypes'}
          onToggle={() => toggle('sourceTypes')}
        />
      </div>
      <AuthFooter />
      <Divider />
      <ThemeBar />
    </aside>
  )
}
