/** Left panel — port of SidebarView.swift.
 *
 * Accordion sections (Connections · Projects · Metrics · Filters · Sampling ·
 * Configuration): opening one collapses the others, exactly like the Swift
 * `collapseAllSections()` behaviour. */

import { useMemo, useState, type ReactNode } from 'react'
import { KPI_DEFAULT_ORDER, KPI_META, TRANSITION_METRICS } from '../types'
import type {
  AssignedConnection,
  FilterGroup,
  GraphStartMode,
  ManagedConnection,
  SliderMode,
  TransitionMetric,
} from '../types'
import { formatSecs } from '../graph/format'
import { useSetting } from '../settings'
import { DEFAULT_LLM_PROMPT, useStore } from '../store'
import { ConnectionEditor } from './ConnectionEditor'
import { Logo } from './Logo'
import { SamplingSection } from './SamplingSection'
import { StepEditor } from './StepEditor'
import {
  AutocompleteField,
  Chevron,
  Divider,
  PromptSheet,
  RangeSlider,
  Segmented,
  Sheet,
  Spinner,
  Switch,
  ToggleRow,
} from './ui'

type SectionId =
  | 'connections'
  | 'projects'
  | 'metrics'
  | 'filters'
  | 'sampling'
  | 'config'

export function Sidebar({ onCollapse }: { onCollapse: () => void }) {
  const store = useStore()
  const [openSection, setOpenSection] = useState<SectionId | null>('connections')
  const [showPromptEditor, setShowPromptEditor] = useState(false)
  const [showSavePreset, setShowSavePreset] = useState(false)
  const [theme, setTheme] = useSetting<string>('app.theme')
  // Power/admin only: the connection being created (null) or edited.
  const [connEditor, setConnEditor] = useState<
    { conn: ManagedConnection | null } | null
  >(null)
  const canManageConnections = store.authIsPower || store.authIsAdmin

  const toggleSection = (id: SectionId) =>
    setOpenSection((current) => (current === id ? null : id))

  return (
    <aside className="sidebar">
      <div className="sidebar-scroll">
        <BrandHeader />
        <Divider />

        <SectionHeader
          title="Connections"
          count={store.connections.length}
          open={openSection === 'connections'}
          onToggle={() => toggleSection('connections')}
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
          <ConnectionsList
            onConnected={() => setOpenSection('projects')}
            onEdit={
              canManageConnections ? (conn) => setConnEditor({ conn }) : undefined
            }
          />
        )}
        <Divider />

        <SectionHeader
          title="Projects"
          count={store.projects.length}
          open={openSection === 'projects'}
          onToggle={() => toggleSection('projects')}
          trailing={
            <button
              className="icon-btn"
              title="Reload projects"
              disabled={!store.connection.isConnected}
              onClick={() => void store.loadProjects()}
            >
              ↻
            </button>
          }
        />
        {openSection === 'projects' && (
          <ProjectsList onSelected={() => setOpenSection(null)} />
        )}
        <Divider />

        <SectionHeader
          title="Metrics"
          open={openSection === 'metrics'}
          onToggle={() => toggleSection('metrics')}
        />
        {openSection === 'metrics' && <MetricsSection />}
        <Divider />

        <SectionHeader
          title="Filters"
          open={openSection === 'filters'}
          onToggle={() => toggleSection('filters')}
        />
        {openSection === 'filters' && (
          <FiltersSection onSavePreset={() => setShowSavePreset(true)} />
        )}
        <Divider />

        <SectionHeader
          title="Sampling"
          open={openSection === 'sampling'}
          onToggle={() => toggleSection('sampling')}
        />
        {openSection === 'sampling' && <SamplingSection />}
        <Divider />

        <SectionHeader
          title="Configuration"
          open={openSection === 'config'}
          onToggle={() => toggleSection('config')}
        />
        {openSection === 'config' && (
          <ConfigSection onEditPrompt={() => setShowPromptEditor(true)} />
        )}
      </div>

      {store.authUser && (
        <>
          <Divider />
          <div className="theme-bar" style={{ gap: 8 }}>
            <span aria-hidden>👤</span>
            {store.authDisplayName ? (
              // Directory (LDAP/AD) accounts: real name on top, username below.
              <div className="col" style={{ gap: 0, minWidth: 0, lineHeight: 1.2 }}>
                <span
                  className="t-caption fg-secondary truncate"
                  title={store.authDisplayName}
                >
                  {store.authDisplayName}
                </span>
                <span className="t-caption2 fg-tertiary truncate" title={store.authUser}>
                  ({store.authUser})
                </span>
              </div>
            ) : (
              <span className="t-caption fg-secondary truncate" title={store.authUser}>
                {store.authUser}
              </span>
            )}
            <span className="spacer" />
            <button
              className="btn small"
              title="Sign out"
              onClick={() => void store.logout()}
            >
              ⏻ Sign out
            </button>
          </div>
        </>
      )}

      <Divider />
      <div className="theme-bar">
        <span aria-hidden>🎨</span>
        <span className="t-caption fg-secondary">Theme</span>
        <span className="spacer" />
        {[
          { value: 'system', icon: '◐', label: 'System' },
          { value: 'light', icon: '☀', label: 'Light' },
          { value: 'dark', icon: '☾', label: 'Dark' },
        ].map((option) => (
          <button
            key={option.value}
            className={`theme-btn${theme === option.value ? ' active' : ''}`}
            title={option.label}
            aria-label={option.label}
            onClick={() => setTheme(option.value)}
          >
            {option.icon}
          </button>
        ))}
        <button
          className="theme-btn"
          title="Hide sidebar"
          aria-label="Hide sidebar"
          onClick={onCollapse}
        >
          ⇤
        </button>
      </div>

      {connEditor && (
        <ConnectionEditor
          connection={connEditor.conn}
          onClose={() => setConnEditor(null)}
        />
      )}
      {showPromptEditor && (
        <PromptEditorSheet onClose={() => setShowPromptEditor(false)} />
      )}
      {showSavePreset && (
        <PromptSheet
          title="Save Filter Preset"
          message="Saves the current filter settings as a named preset."
          onCancel={() => setShowSavePreset(false)}
          onConfirm={(name) => {
            store.createFilterGroup(name)
            setShowSavePreset(false)
          }}
        />
      )}
    </aside>
  )
}

// ── Branding ─────────────────────────────────────────────────────────────────

function BrandHeader() {
  return (
    <div className="brand-header">
      <div className="brand-logo" aria-hidden>
        <Logo />
      </div>
      <div className="col" style={{ gap: 2 }}>
        <span className="t-title3">Process Mining</span>
        <span className="t-caption fg-secondary">Demonstrator</span>
      </div>
    </div>
  )
}

// ── Section chrome ───────────────────────────────────────────────────────────

function SectionHeader({
  title,
  count,
  open,
  onToggle,
  trailing,
}: {
  title: string
  count?: number
  open: boolean
  onToggle: () => void
  trailing?: ReactNode
}) {
  return (
    <div className="section-header">
      <button className="section-toggle" onClick={onToggle}>
        <Chevron open={open} />
        <span className="section-title">{title}</span>
        {count != null && count > 0 && <span className="section-count">({count})</span>}
      </button>
      {trailing}
    </div>
  )
}

function SubHeader({
  title,
  open,
  onToggle,
  badge,
  onClear,
}: {
  title: string
  open: boolean
  onToggle: () => void
  badge?: string
  onClear?: () => void
}) {
  return (
    <div className="sub-header">
      <button onClick={onToggle}>
        <Chevron open={open} />
        <span className="sub-title">{title}</span>
      </button>
      {badge && <span className="badge-pill">{badge}</span>}
      {onClear && (
        <button
          className="icon-btn"
          style={{ color: 'var(--secondary)', width: 20, height: 20 }}
          title={`Clear ${title}`}
          onClick={onClear}
        >
          ⊗
        </button>
      )}
    </div>
  )
}

// ── Connections ──────────────────────────────────────────────────────────────

function ConnectionsList({
  onConnected,
  onEdit,
}: {
  onConnected: () => void
  onEdit?: (conn: ManagedConnection) => void
}) {
  const store = useStore()
  const sorted = useMemo(
    () => [...store.connections].sort((a, b) => a.name.localeCompare(b.name)),
    [store.connections],
  )
  // Connections this power user owns and may edit, keyed by id.
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
    const ok = await store.connectConnection(conn)
    if (ok) onConnected()
  }

  if (sorted.length === 0) {
    return (
      <div className="card-list">
        <span className="empty-hint">
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
    <div className="card-list" style={{ maxHeight: 300 }}>
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
                  e.stopPropagation()
                  onEdit(manageableById.get(conn.id)!)
                }}
              >
                ✎
              </button>
            )}
            {isActive && (
              <div className="col" style={{ gap: 4, alignItems: 'center' }}>
                <span
                  className="status-dot"
                  style={{ background: isConnected ? 'var(--green)' : 'var(--orange)' }}
                  title={isConnected ? 'Connected' : 'Not connected'}
                />
                {conn.hasLLM && (
                  <span
                    className="status-dot"
                    style={{
                      background: store.connection.isLLMReachable
                        ? 'var(--blue)'
                        : 'var(--orange)',
                    }}
                    title={
                      store.connection.isLLMReachable
                        ? 'LLM reachable'
                        : 'LLM not reachable'
                    }
                  />
                )}
              </div>
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

// ── Projects ─────────────────────────────────────────────────────────────────

function ProjectsList({ onSelected }: { onSelected: () => void }) {
  const store = useStore()

  if (!store.connection.isConnected) {
    return (
      <div className="card-list">
        <span className="empty-hint">Connect to a database to load projects.</span>
      </div>
    )
  }
  if (store.isLoading && store.projects.length === 0) {
    return (
      <div className="card-list">
        <span className="row empty-hint">
          <Spinner /> Loading
        </span>
      </div>
    )
  }
  if (store.projects.length === 0) {
    return (
      <div className="card-list">
        <span className="empty-hint">No projects found.</span>
      </div>
    )
  }

  return (
    <div className="card-list" style={{ maxHeight: 240 }}>
      {store.projects.map((project) => {
        const selected = store.selectedProject?.projectId === project.projectId
        return (
          <button
            key={project.projectId}
            className={`card${selected ? ' selected' : ''}`}
            onClick={() => {
              void store.selectProject(project)
              onSelected()
            }}
          >
            <span aria-hidden className="fg-accent">
              📈
            </span>
            <div className="card-body">
              <span className="card-title">{project.title}</span>
              {project.description && (
                <span className="card-sub">{project.description}</span>
              )}
            </div>
            {selected && <span className="fg-accent">✓</span>}
          </button>
        )
      })}
    </div>
  )
}

// ── Metrics ──────────────────────────────────────────────────────────────────

const METRIC_ICONS: Record<TransitionMetric, string> = {
  Count: '#',
  'Avg Time': '⏱',
  'Min Time': '⌄',
  'Max Time': '⌃',
  'Std Dev': '〰',
}

function MetricsSection() {
  const store = useStore()
  return (
    <div className="col" style={{ padding: '10px 20px', gap: 8 }}>
      <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
        ƒ Transition metric
      </span>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 6,
        }}
      >
        {TRANSITION_METRICS.map((m) => (
          <button
            key={m}
            className={`chip${store.transitionMetric === m ? ' active' : ''}`}
            style={{ justifyContent: 'center', borderRadius: 7 }}
            disabled={!store.selectedProject}
            onClick={() => store.setTransitionMetric(m)}
          >
            <span aria-hidden>{METRIC_ICONS[m]}</span> {m}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Filters ──────────────────────────────────────────────────────────────────

function StepFilterList({
  steps,
  selected,
  disabledSteps,
  onToggle,
}: {
  steps: string[]
  selected: string[]
  disabledSteps: string[]
  onToggle: (step: string) => void
}) {
  const [search, setSearch] = useState('')
  const filtered = search
    ? steps.filter((s) => s.toLowerCase().includes(search.toLowerCase()))
    : steps

  return (
    <div className="step-filter">
      <div className="search-row">
        <span aria-hidden className="fg-secondary">
          🔍
        </span>
        <input
          value={search}
          placeholder="Search"
          onChange={(e) => setSearch(e.target.value)}
        />
        {search && (
          <button
            className="fg-secondary"
            onClick={() => setSearch('')}
            title="Clear search"
          >
            ⊗
          </button>
        )}
      </div>
      <div className="step-list">
        {steps.length === 0 ? (
          <span className="t-caption2 fg-tertiary" style={{ padding: '4px 8px' }}>
            No project selected
          </span>
        ) : filtered.length === 0 ? (
          <span className="t-caption2 fg-tertiary" style={{ padding: '4px 8px' }}>
            No matches
          </span>
        ) : (
          filtered.map((step) => {
            const isSelected = selected.includes(step)
            const isDisabled = disabledSteps.includes(step)
            return (
              <button
                key={step}
                className={`step-row${isSelected ? ' selected' : ''}${
                  isDisabled ? ' disabled' : ''
                }`}
                disabled={isDisabled}
                onClick={() => onToggle(step)}
              >
                <span className="mark">{isSelected ? '◉' : '○'}</span>
                <span className="truncate">{step}</span>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}

function FiltersSection({ onSavePreset }: { onSavePreset: () => void }) {
  const store = useStore()
  const [dateOpen, setDateOpen] = useSetting<boolean>('sidebar.filtersDateExpanded')
  const [includeOpen, setIncludeOpen] = useSetting<boolean>(
    'sidebar.filtersIncludeExpanded',
  )
  const [excludeOpen, setExcludeOpen] = useSetting<boolean>(
    'sidebar.filtersExcludeExpanded',
  )
  const [stepsOpen, setStepsOpen] = useSetting<boolean>('sidebar.filtersStepsExpanded')
  const [timeOpen, setTimeOpen] = useSetting<boolean>(
    'sidebar.filtersJourneyTimeExpanded',
  )
  const [scoreOpen, setScoreOpen] = useSetting<boolean>('sidebar.filtersScoreExpanded')
  const [metaOpen, setMetaOpen] = useSetting<boolean>('sidebar.filtersMetaExpanded')

  const disabled = !store.selectedProject
  const isStatistics = store.activeChartMode === 'Statistics'
  const apply = () =>
    isStatistics ? void store.loadStatistics() : void store.reloadGraph()

  // The Individual Journey and AI views use their own filter UI.
  if (store.activeChartMode === 'Individual Journey') {
    return <EventIdFilter />
  }
  if (store.activeChartMode === 'AI supported Documentation') {
    return (
      <div className="row" style={{ padding: '12px 20px', gap: 8, alignItems: 'flex-start' }}>
        <span aria-hidden className="fg-secondary">
          ⓘ
        </span>
        <span className="t-caption fg-secondary">
          AI supported Documentation uses the filter conditions from the A-Chart.
        </span>
      </div>
    )
  }

  const stepsActive =
    store.minStepsFilter > store.stepCountMin || store.maxStepsFilter < store.stepCountMax
  const timeActive =
    store.minJourneyTimeFilter > store.journeyTimeBoundsMin ||
    store.maxJourneyTimeFilter < store.journeyTimeBoundsMax
  const scoreActive =
    store.minScoreFilter > store.scoreBoundsMin || store.maxScoreFilter < store.scoreBoundsMax
  const metaCount =
    (store.meta1Title && store.meta1Filter ? 1 : 0) +
    (store.meta2Title && store.meta2Filter ? 1 : 0) +
    (store.meta3Title && store.meta3Filter ? 1 : 0)
  const hasMeta = !!(store.meta1Title || store.meta2Title || store.meta3Title)

  const maxSteps = Math.max(store.stepCountMin, store.stepCountMax)
  const maxTime = Math.max(store.journeyTimeBoundsMin + 1, store.journeyTimeBoundsMax)
  const maxScore = Math.max(store.scoreBoundsMin + 1, store.scoreBoundsMax)

  return (
    <div className="col" style={{ gap: 0 }}>
      {store.activeChartMode === 'A/B Comparison' && (
        <>
          <div className="row" style={{ padding: '8px 20px', gap: 10 }}>
            <span className="t-caption fg-secondary">Editing:</span>
            <Segmented
              options={[
                { value: 'a', label: 'A-Chart' },
                { value: 'b', label: 'B-Chart' },
              ]}
              value={store.abActiveSide}
              onChange={(side) => store.switchABSide(side)}
            />
          </div>
          <Divider />
        </>
      )}

      <SubHeader title="Date" open={dateOpen} onToggle={() => setDateOpen(!dateOpen)} />
      {dateOpen && (
        <div className="col" style={{ padding: '0 20px 10px', gap: 8 }}>
          <div className="row">
            <span className="t-footnote fg-secondary" style={{ width: 34 }}>
              From
            </span>
            <input
              className="text-input"
              type="date"
              value={store.fromDate}
              onChange={(e) => store.patch({ fromDate: e.target.value })}
            />
          </div>
          <div className="row">
            <span className="t-footnote fg-secondary" style={{ width: 34 }}>
              To
            </span>
            <input
              className="text-input"
              type="date"
              value={store.toDate}
              onChange={(e) => store.patch({ toDate: e.target.value })}
            />
          </div>
        </div>
      )}
      <Divider />

      <SubHeader
        title="Include Steps"
        open={includeOpen}
        onToggle={() => setIncludeOpen(!includeOpen)}
        badge={store.includedSteps.length ? String(store.includedSteps.length) : undefined}
        onClear={
          store.includedSteps.length ? () => store.patch({ includedSteps: [] }) : undefined
        }
      />
      {includeOpen && (
        <div style={{ padding: '0 20px 10px' }}>
          <StepFilterList
            steps={store.allSteps}
            selected={store.includedSteps}
            disabledSteps={store.excludedSteps}
            onToggle={(step) =>
              store.patch({
                includedSteps: store.includedSteps.includes(step)
                  ? store.includedSteps.filter((s) => s !== step)
                  : [...store.includedSteps, step],
              })
            }
          />
        </div>
      )}
      <Divider />

      <SubHeader
        title="Exclude Steps"
        open={excludeOpen}
        onToggle={() => setExcludeOpen(!excludeOpen)}
        badge={store.excludedSteps.length ? String(store.excludedSteps.length) : undefined}
        onClear={
          store.excludedSteps.length ? () => store.patch({ excludedSteps: [] }) : undefined
        }
      />
      {excludeOpen && (
        <div style={{ padding: '0 20px 10px' }}>
          <StepFilterList
            steps={store.allSteps}
            selected={store.excludedSteps}
            disabledSteps={store.includedSteps}
            onToggle={(step) =>
              store.patch({
                excludedSteps: store.excludedSteps.includes(step)
                  ? store.excludedSteps.filter((s) => s !== step)
                  : [...store.excludedSteps, step],
              })
            }
          />
        </div>
      )}
      <Divider />

      <SubHeader
        title="Num Steps"
        open={stepsOpen}
        onToggle={() => setStepsOpen(!stepsOpen)}
        badge={
          stepsActive ? `${store.minStepsFilter}–${store.maxStepsFilter}` : undefined
        }
        onClear={
          stepsActive
            ? () =>
                store.patch({
                  minStepsFilter: store.stepCountMin,
                  maxStepsFilter: store.stepCountMax,
                })
            : undefined
        }
      />
      {stepsOpen && (
        <div style={{ padding: '10px 20px' }}>
          <RangeSlider
            min={store.stepCountMin}
            max={maxSteps}
            low={store.minStepsFilter}
            high={Math.min(store.maxStepsFilter, maxSteps)}
            disabled={disabled || store.stepCountMin === store.stepCountMax}
            onChange={(low, high) =>
              store.patch({ minStepsFilter: low, maxStepsFilter: high })
            }
          />
        </div>
      )}
      <Divider />

      <SubHeader
        title="Journey Time"
        open={timeOpen}
        onToggle={() => setTimeOpen(!timeOpen)}
        badge={
          timeActive
            ? `${formatSecs(store.minJourneyTimeFilter)}–${formatSecs(
                Math.min(store.maxJourneyTimeFilter, maxTime),
              )}`
            : undefined
        }
        onClear={
          timeActive
            ? () =>
                store.patch({
                  minJourneyTimeFilter: store.journeyTimeBoundsMin,
                  maxJourneyTimeFilter: store.journeyTimeBoundsMax,
                })
            : undefined
        }
      />
      {timeOpen && (
        <div style={{ padding: '10px 20px' }}>
          <RangeSlider
            min={store.journeyTimeBoundsMin}
            max={maxTime}
            low={store.minJourneyTimeFilter}
            high={Math.min(store.maxJourneyTimeFilter, maxTime)}
            format={formatSecs}
            disabled={
              disabled || store.journeyTimeBoundsMax <= store.journeyTimeBoundsMin
            }
            onChange={(low, high) =>
              store.patch({ minJourneyTimeFilter: low, maxJourneyTimeFilter: high })
            }
          />
        </div>
      )}
      <Divider />

      <SubHeader
        title="Journey Score"
        open={scoreOpen}
        onToggle={() => setScoreOpen(!scoreOpen)}
        badge={
          scoreActive ? `${store.minScoreFilter}–${store.maxScoreFilter}` : undefined
        }
        onClear={
          scoreActive
            ? () =>
                store.patch({
                  minScoreFilter: store.scoreBoundsMin,
                  maxScoreFilter: store.scoreBoundsMax,
                })
            : undefined
        }
      />
      {scoreOpen && (
        <div style={{ padding: '10px 20px' }}>
          <RangeSlider
            min={store.scoreBoundsMin}
            max={maxScore}
            low={Math.max(store.minScoreFilter, store.scoreBoundsMin)}
            high={Math.min(store.maxScoreFilter, maxScore)}
            disabled={disabled || store.scoreBoundsMax <= store.scoreBoundsMin}
            onChange={(low, high) =>
              store.patch({ minScoreFilter: low, maxScoreFilter: high })
            }
          />
        </div>
      )}

      {hasMeta && (
        <>
          <Divider />
          <SubHeader
            title="Meta"
            open={metaOpen}
            onToggle={() => setMetaOpen(!metaOpen)}
            badge={metaCount > 0 ? String(metaCount) : undefined}
            onClear={
              metaCount > 0
                ? () =>
                    store.patch({ meta1Filter: '', meta2Filter: '', meta3Filter: '' })
                : undefined
            }
          />
          {metaOpen && (
            <div className="col" style={{ padding: '0 20px 10px', gap: 6 }}>
              <MetaField
                title={store.meta1Title}
                value={store.meta1Filter}
                suggestions={store.meta1Values}
                onChange={(v) => store.patch({ meta1Filter: v })}
              />
              <MetaField
                title={store.meta2Title}
                value={store.meta2Filter}
                suggestions={store.meta2Values}
                onChange={(v) => store.patch({ meta2Filter: v })}
              />
              <MetaField
                title={store.meta3Title}
                value={store.meta3Filter}
                suggestions={store.meta3Values}
                onChange={(v) => store.patch({ meta3Filter: v })}
              />
            </div>
          )}
        </>
      )}

      <div className="row" style={{ padding: '10px 20px', gap: 8 }}>
        <button
          className="btn small"
          disabled={disabled}
          onClick={() => {
            store.resetFilters()
            apply()
          }}
        >
          ↺ Reset
        </button>
        <span className="spacer" />
        <button className="btn small" disabled={disabled} onClick={onSavePreset}>
          🔖 Save Preset…
        </button>
        <button className="btn prominent small" disabled={disabled} onClick={apply}>
          Apply
        </button>
      </div>

      <PresetList />
    </div>
  )
}

function MetaField({
  title,
  value,
  suggestions,
  onChange,
}: {
  title: string | null
  value: string
  suggestions: string[]
  onChange: (value: string) => void
}) {
  if (!title) return null
  return (
    <AutocompleteField
      label={title}
      value={value}
      suggestions={suggestions}
      onChange={onChange}
    />
  )
}

function PresetList() {
  const store = useStore()
  const [renaming, setRenaming] = useState<FilterGroup | null>(null)

  if (store.filterGroups.length === 0) return null

  return (
    <>
      <Divider />
      <div className="col" style={{ padding: '8px 20px 12px', gap: 4 }}>
        <span className="sub-title">Presets</span>
        {store.filterGroups.map((group) => (
          <div
            key={group.id}
            className={`card${store.selectedFilterGroupId === group.id ? ' selected' : ''}`}
            style={{ minHeight: 32, padding: '5px 10px' }}
          >
            <button
              className="card-body"
              style={{ textAlign: 'left' }}
              onClick={() => {
                store.applyFilterGroup(group)
                void store.reloadGraph()
              }}
            >
              <span className="card-title t-caption">{group.name}</span>
            </button>
            <button
              className="icon-btn"
              style={{ width: 20, height: 20, fontSize: 11, color: 'var(--secondary)' }}
              title="Rename preset"
              onClick={() => setRenaming(group)}
            >
              ✎
            </button>
            <button
              className="icon-btn"
              style={{ width: 20, height: 20, fontSize: 11, color: 'var(--red)' }}
              title="Delete preset"
              onClick={() => store.deleteFilterGroup(group.id)}
            >
              🗑
            </button>
          </div>
        ))}
      </div>
      {renaming && (
        <PromptSheet
          title="Rename Filter Preset"
          initialValue={renaming.name}
          confirmLabel="Rename"
          onCancel={() => setRenaming(null)}
          onConfirm={(name) => {
            store.renameFilterGroup(renaming.id, name)
            setRenaming(null)
          }}
        />
      )}
    </>
  )
}

function EventIdFilter() {
  const store = useStore()
  const [focused, setFocused] = useState(false)

  return (
    <div className="col" style={{ padding: '8px 20px 10px', gap: 10 }}>
      <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
        Event ID
      </span>
      <div style={{ position: 'relative' }}>
        <div className="row" style={{ gap: 6 }}>
          <input
            className="text-input"
            value={store.eventIdFilter}
            placeholder="Enter EVENT_ID"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            onChange={(e) => {
              store.patch({ eventIdFilter: e.target.value })
              void store.fetchEventIdSuggestions()
              setFocused(true)
            }}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 180)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setFocused(false)
                void store.loadIndividualJourney()
              }
            }}
          />
          {store.eventIdFilter && (
            <button
              className="icon-btn"
              style={{ width: 22, height: 22, color: 'var(--secondary)' }}
              onClick={() => store.patch({ eventIdFilter: '', eventIdSuggestions: [] })}
              title="Clear"
            >
              ⊗
            </button>
          )}
        </div>
        {focused && store.eventIdSuggestions.length > 0 && (
          <div
            className="suggestions"
            style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10 }}
          >
            {store.eventIdSuggestions.map((id) => (
              <button
                key={id}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  store.patch({ eventIdFilter: id, eventIdSuggestions: [] })
                  setFocused(false)
                  void store.loadIndividualJourney()
                }}
              >
                {id}
              </button>
            ))}
          </div>
        )}
      </div>
      <button
        className="btn prominent small"
        style={{ alignSelf: 'flex-end' }}
        disabled={!store.eventIdFilter.trim() || !store.selectedProject}
        onClick={() => void store.loadIndividualJourney()}
      >
        Load Journey
      </button>
    </div>
  )
}

// ── Configuration ────────────────────────────────────────────────────────────

function ConfigSection({ onEditPrompt }: { onEditPrompt: () => void }) {
  const store = useStore()
  const [showGrouping, setShowGrouping] = useSetting<boolean>('processmap.showGrouping')
  const [startMode, setStartMode] = useSetting<GraphStartMode>('graph.startMode')
  const [showDescriptions, setShowDescriptions] = useSetting<boolean>(
    'processmap.showNodeDescriptions',
  )
  const [optimised, setOptimised] = useSetting<boolean>('graph.optimisedLayout')
  const [colorize, setColorize] = useSetting<boolean>('graph.edge.colorizeByWeight')
  const [sliderMode, setSliderMode] = useSetting<SliderMode>('slider.mode')
  const [kpisOpen, setKpisOpen] = useSetting<boolean>('sidebar.configKpisExpanded')
  const [stepsOpen, setStepsOpen] = useSetting<boolean>('sidebar.configStepsExpanded')
  const [kpiOrder, setKpiOrder] = useSetting<string>('kpi.order')
  const [dragging, setDragging] = useState<string | null>(null)

  const orderedIds = useMemo(() => {
    const stored = kpiOrder.split(',').filter(Boolean)
    const all = KPI_DEFAULT_ORDER.split(',')
    return [...stored, ...all.filter((id) => !stored.includes(id))]
  }, [kpiOrder])

  const reorder = (dragId: string, targetId: string) => {
    if (dragId === targetId) return
    const arr = orderedIds.filter((id) => id !== dragId)
    const index = arr.indexOf(targetId)
    arr.splice(index < 0 ? arr.length : index, 0, dragId)
    setKpiOrder(arr.join(','))
  }

  return (
    <div className="col" style={{ gap: 0 }}>
      <ToggleRow
        icon="⬚"
        label="Show step groups"
        checked={showGrouping}
        onChange={setShowGrouping}
      />
      {showGrouping && (
        <div className="col" style={{ padding: '6px 20px', gap: 5 }}>
          <span className="t-caption fg-secondary">▦ Groups start</span>
          <Segmented
            options={[
              { value: 'expanded', label: 'Expanded' },
              { value: 'collapsed', label: 'Collapsed' },
              { value: 'persisted', label: 'Persisted' },
            ]}
            value={startMode}
            onChange={setStartMode}
          />
        </div>
      )}
      <ToggleRow
        icon="🗒"
        label="Show node notes"
        checked={showDescriptions}
        onChange={setShowDescriptions}
      />
      <ToggleRow
        icon="✨"
        label="Optimise layout"
        checked={optimised}
        onChange={setOptimised}
      />
      <ToggleRow
        icon="🎨"
        label="Colorise edges by weight"
        checked={colorize}
        onChange={setColorize}
      />

      <Divider />
      <div className="row" style={{ padding: '8px 20px', gap: 10 }}>
        <span aria-hidden className="fg-secondary">
          ⇥
        </span>
        <span className="t-caption fg-secondary spacer">Date slider</span>
        <Segmented
          options={[
            { value: 'Range', label: 'Range' },
            { value: 'Day', label: 'Day' },
          ]}
          value={sliderMode}
          onChange={setSliderMode}
        />
      </div>

      <Divider />
      <div className="row" style={{ padding: '8px 20px', gap: 10 }}>
        <span aria-hidden className="fg-secondary">
          💬
        </span>
        <span className="t-caption fg-secondary spacer">LLM Prompt</span>
        <button
          className="btn small"
          disabled={!store.selectedProject}
          onClick={onEditPrompt}
        >
          Edit
        </button>
      </div>

      <Divider />
      <SubHeader title="KPIs" open={kpisOpen} onToggle={() => setKpisOpen(!kpisOpen)} />
      {kpisOpen && (
        <div className="col" style={{ padding: '0 14px 8px', gap: 0 }}>
          {orderedIds.map((id) => (
            <KpiToggleRow
              key={id}
              id={id}
              dragging={dragging === id}
              onDragStart={() => setDragging(id)}
              onDragEnd={() => setDragging(null)}
              onDropOn={() => {
                if (dragging) reorder(dragging, id)
              }}
            />
          ))}
        </div>
      )}

      <Divider />
      <SubHeader title="Steps" open={stepsOpen} onToggle={() => setStepsOpen(!stepsOpen)} />
      {stepsOpen && (
        <div style={{ padding: '0 20px 14px' }}>
          <StepEditor />
        </div>
      )}
    </div>
  )
}

function KpiToggleRow({
  id,
  dragging,
  onDragStart,
  onDragEnd,
  onDropOn,
}: {
  id: string
  dragging: boolean
  onDragStart: () => void
  onDragEnd: () => void
  onDropOn: () => void
}) {
  const meta = KPI_META[id]
  const [visible, setVisible] = useSetting<boolean>(`kpi.show.${id}`, true)
  if (!meta) return null

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDropOn}
      className="row"
      style={{ gap: 6, opacity: dragging ? 0.4 : 1, cursor: 'grab' }}
    >
      <span className="fg-tertiary" style={{ width: 14, fontSize: 11 }} aria-hidden>
        ≡
      </span>
      <div className="toggle-row" style={{ flex: 1, padding: '6px 0' }}>
        <span aria-hidden style={{ width: 16 }}>
          {meta.icon}
        </span>
        <span className="toggle-label">{meta.label}</span>
        <Switch checked={visible} onChange={setVisible} />
      </div>
    </div>
  )
}

function PromptEditorSheet({ onClose }: { onClose: () => void }) {
  const store = useStore()
  const [text, setText] = useState(store.llmPromptTemplate)

  return (
    <Sheet
      title="LLM Prompt Template"
      onClose={onClose}
      footer={
        <>
          <button
            className="btn"
            onClick={() => setText(DEFAULT_LLM_PROMPT)}
          >
            Reset to Default
          </button>
          <span className="spacer" />
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn prominent"
            onClick={() => {
              store.setLLMPromptTemplate(text)
              onClose()
            }}
          >
            Save
          </button>
        </>
      }
    >
      <div className="t-caption fg-secondary">
        This prompt is sent to the LLM together with the current transition table. Use it
        to guide the analysis style and output format.
      </div>
      <textarea
        className="text-input"
        style={{ minHeight: 220 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </Sheet>
  )
}
