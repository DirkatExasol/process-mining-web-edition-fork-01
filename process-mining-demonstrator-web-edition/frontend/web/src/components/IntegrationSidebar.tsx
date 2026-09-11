/** Left panel for the integration console — mirrors the app sidebar: a brand
 *  header, the user's data-source connection badges, and the shared identity /
 *  authentication footer pinned at the bottom. */

import { useMemo, useState } from 'react'
import { useStore } from '../store'
import type { AssignedConnection, ManagedConnection } from '../types'
import { AuthFooter } from './AuthFooter'
import { ConnectionEditor } from './ConnectionEditor'
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
function ConnectionBadges({ onEdit }: { onEdit?: (conn: ManagedConnection) => void }) {
  const store = useStore()
  const sorted = useMemo(
    () => [...store.connections].sort((a, b) => a.name.localeCompare(b.name)),
    [store.connections],
  )
  // Connections this developer owns and may edit, keyed by id. Being *assigned* a
  // connection is not the same as owning it — an admin's connection stays read-only.
  const manageableById = useMemo(
    () => new Map(store.manageableConnections.map((c) => [c.id, c])),
    [store.manageableConnections],
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
          {onEdit
            ? 'No connections yet. Use ＋ above to create one and assign users.'
            : 'No connections assigned to you. Ask an administrator to grant access.'}
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
            {onEdit && manageableById.has(conn.id) && (
              <button
                className="icon-btn"
                style={{ width: 22, height: 22, color: 'var(--secondary)' }}
                title="Edit connection"
                onClick={(e) => {
                  e.stopPropagation() // the card itself connects/disconnects
                  onEdit(manageableById.get(conn.id)!)
                }}
              >
                ✎
              </button>
            )}
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

  // Same capability as the main app's sidebar — the console is developer/admin only, but
  // keep the predicate identical so the two surfaces can never drift apart.
  const [connEditor, setConnEditor] = useState<{ conn: ManagedConnection | null } | null>(null)
  const canManageConnections =
    store.authIsPower || store.authIsAdmin || store.authIsDeveloper

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
          trailing={
            <>
              {canManageConnections && (
                <button
                  className="icon-btn"
                  title="New connection"
                  onClick={() => {
                    void store.refreshManageable()
                    setConnEditor({ conn: null })
                  }}
                >
                  ＋
                </button>
              )}
              <button
                className="icon-btn"
                title="Refresh connections"
                onClick={() => void store.refreshConnections()}
              >
                ↻
              </button>
            </>
          }
        />
        {openSection === 'connections' && (
          <ConnectionBadges
            onEdit={canManageConnections ? (conn) => setConnEditor({ conn }) : undefined}
          />
        )}
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

      {connEditor && (
        <ConnectionEditor
          connection={connEditor.conn}
          onClose={() => setConnEditor(null)}
        />
      )}
    </aside>
  )
}
