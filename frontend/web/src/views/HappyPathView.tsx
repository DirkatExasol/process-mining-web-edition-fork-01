/** Happy Path — port of HappyPathView.swift.
 *
 * Left: the actual process map. Right: the ideal sequence. In view mode the
 * ideal path is drawn as a trunk of step cards → a Y-fork → named branch
 * columns, each card showing its coverage (max(incoming, outgoing) / journeys)
 * as a green percentage. Edit mode swaps in the step editor. */

import { useEffect, useMemo, useState } from 'react'
import { Divider, PromptSheet, Unavailable } from '../components/ui'
import { FlowChart } from '../flow/FlowChart'
import { useStore } from '../store'
import type { HappyPath, HappyPathBranch } from '../types'
import { useNoteHandlers } from './useNoteHandlers'

export function HappyPathView() {
  const store = useStore()
  const notes = useNoteHandlers()
  const [editMode, setEditMode] = useState(false)
  const [newPathName, setNewPathName] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<HappyPath | null>(null)
  const [renamingBranch, setRenamingBranch] = useState<{
    pathId: string
    branchId: string
    label: string
  } | null>(null)

  const path = store.happyPaths.find((p) => p.id === store.selectedHappyPathId) ?? null
  const score = path ? store.happyPathScores[path.id] : null

  useEffect(() => {
    if (store.selectedProject && store.happyPaths.length > 0) {
      void store.refreshHappyPathConformance()
    }
    setEditMode(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.selectedProject?.projectId, store.happyPaths.length, store.selectedHappyPathId])

  // Coverage per step: max(incoming, outgoing) occurrences / total journeys.
  const coverage = useMemo<Record<string, number>>(() => {
    const total = store.journeyCount
    if (!total || total <= 0) return {}
    const incoming: Record<string, number> = {}
    const outgoing: Record<string, number> = {}
    for (const t of store.processGraph.transitions) {
      outgoing[t.fromStep] = (outgoing[t.fromStep] ?? 0) + t.occurrences
      incoming[t.toStep] = (incoming[t.toStep] ?? 0) + t.occurrences
    }
    const result: Record<string, number> = {}
    for (const step of Object.keys(store.processGraph.steps)) {
      const count = Math.max(incoming[step] ?? 0, outgoing[step] ?? 0)
      result[step] = Math.min(1, count / total)
    }
    return result
  }, [store.processGraph, store.journeyCount])

  const inGraph = useMemo(
    () => new Set(Object.keys(store.processGraph.steps)),
    [store.processGraph.steps],
  )

  if (!store.selectedProject) {
    return (
      <Unavailable
        glyph="🗺"
        title="No Project Selected"
        description="Select a project from the sidebar."
      />
    )
  }

  const scoreColor =
    score == null
      ? 'var(--secondary)'
      : score >= 0.7
        ? 'var(--green)'
        : score <= 0.3
          ? 'var(--red)'
          : 'var(--orange)'

  const available = path
    ? store.allSteps.filter(
        (s) => !path.steps.includes(s) && !path.branches.some((b) => b.steps.includes(s)),
      )
    : []

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div
        className="row"
        style={{
          padding: '8px 16px',
          gap: 10,
          background: 'var(--bg-tertiary-grouped)',
          borderBottom: '1px solid var(--separator-soft)',
        }}
      >
        <span aria-hidden>🪧</span>
        <select
          className="select-input"
          style={{ width: 'auto', minWidth: 160 }}
          value={store.selectedHappyPathId ?? ''}
          onChange={(e) => store.selectHappyPath(e.target.value)}
        >
          {store.happyPaths.length === 0 && <option value="">No happy paths yet</option>}
          {store.happyPaths.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button className="btn small" onClick={() => setNewPathName('')}>
          ＋ New
        </button>
        {path && (
          <>
            <button className="btn small" onClick={() => setRenaming(path)}>
              ✎ Rename
            </button>
            <button
              className="btn small destructive"
              onClick={() => store.deleteHappyPath(path.id)}
            >
              🗑 Delete
            </button>
          </>
        )}

        {score != null && (
          <div
            className="row"
            style={{
              gap: 6,
              padding: '5px 10px',
              borderRadius: 10,
              background: 'var(--material)',
              border: `1.5px solid ${
                score >= 0.7
                  ? 'rgba(52,199,89,0.45)'
                  : score <= 0.3
                    ? 'rgba(255,59,48,0.45)'
                    : 'rgba(255,149,0,0.45)'
              }`,
            }}
            title="Journey-count-weighted edge coverage"
          >
            <span aria-hidden style={{ color: scoreColor }}>
              🪧
            </span>
            <span className="t-caption fg-secondary">Conformance</span>
            <span className="t-headline tnum" style={{ color: scoreColor }}>
              {score.toFixed(2)}
            </span>
          </div>
        )}

        <span className="spacer" />
        {path && (
          <button
            className={`btn small${editMode ? ' prominent' : ''}`}
            onClick={() => setEditMode(!editMode)}
          >
            {editMode ? '✓ Done' : '✎ Edit Path'}
          </button>
        )}
      </div>

      {/* ── Body: actual map (left) + happy path (right) ────────────────── */}
      <div className="row" style={{ flex: 1, minHeight: 0, alignItems: 'stretch', gap: 0 }}>
        <div className="col" style={{ flex: 1, minWidth: 0, gap: 0 }}>
          <div
            className="row"
            style={{
              padding: '6px 14px',
              gap: 6,
              background: 'var(--bg-secondary-grouped)',
              borderBottom: '1px solid var(--separator-soft)',
            }}
          >
            <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
              Actual Process
            </span>
            <span className="spacer" />
            {store.journeyCount != null && (
              <span className="t-caption2 fg-secondary tnum">
                {store.journeyCount.toLocaleString()} journeys
              </span>
            )}
          </div>
          {store.processGraph.transitions.length === 0 ? (
            <Unavailable
              glyph="📊"
              title="No Process Data"
              description="Apply filters in the sidebar to load the process map."
              action={
                <button className="btn prominent" onClick={() => void store.reloadGraph()}>
                  Load
                </button>
              }
            />
          ) : (
            <FlowChart
              graph={store.processGraph}
              projectId={store.selectedProject.projectId}
              chartMode="HappyPath"
              metric={store.transitionMetric}
              isLoading={store.isLoading}
              onNodeAction={(node, action) => store.handleNodeAction(node, action)}
              notes={store.projectNotes}
              onNodeNote={notes.openNodeNotes}
              onEdgeNote={notes.openEdgeNotes}
            />
          )}
        </div>

        <div
          className="col"
          style={{
            width: 460,
            flexShrink: 0,
            borderLeft: '1px solid var(--separator)',
            background: 'var(--bg-secondary-grouped)',
            gap: 0,
            minHeight: 0,
          }}
        >
          <div
            className="row"
            style={{
              padding: '6px 14px',
              gap: 6,
              borderBottom: '1px solid var(--separator-soft)',
            }}
          >
            <span className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
              {path?.name ?? 'Happy Path'}
            </span>
            <span className="spacer" />
            {editMode && path && available.length > 0 && (
              <AddStepMenu
                label="＋"
                steps={available}
                onPick={(step) =>
                  store.updateHappyPath(path.id, (p) =>
                    p.steps.includes(step) ? p : { ...p, steps: [...p.steps, step] },
                  )
                }
              />
            )}
          </div>

          {!path ? (
            <div style={{ padding: 20 }}>
              <span className="t-footnote fg-secondary">
                Define an ideal step sequence to measure how closely real journeys follow
                your intended design. Create one with “＋ New”.
              </span>
            </div>
          ) : path.steps.length === 0 ? (
            <Unavailable
              glyph="🪧"
              title="No Steps Defined"
              description={
                editMode
                  ? 'Use ＋ to add the first step.'
                  : 'Enable Edit Path to define the happy path.'
              }
            />
          ) : editMode ? (
            <HappyPathEditor
              path={path}
              available={available}
              coverage={coverage}
              inGraph={inGraph}
              onRenameBranch={(branchId, label) =>
                setRenamingBranch({ pathId: path.id, branchId, label })
              }
            />
          ) : (
            <HappyPathVisualisation path={path} coverage={coverage} inGraph={inGraph} />
          )}
        </div>
      </div>

      {newPathName !== null && (
        <PromptSheet
          title="New Happy Path"
          message="Give the ideal step sequence a name."
          onCancel={() => setNewPathName(null)}
          onConfirm={(name) => {
            store.createHappyPath(name)
            setNewPathName(null)
            setEditMode(true)
          }}
        />
      )}
      {renaming && (
        <PromptSheet
          title="Rename Happy Path"
          initialValue={renaming.name}
          confirmLabel="Rename"
          onCancel={() => setRenaming(null)}
          onConfirm={(name) => {
            store.renameHappyPath(renaming.id, name)
            setRenaming(null)
          }}
        />
      )}
      {renamingBranch && (
        <PromptSheet
          title="Rename Branch"
          initialValue={renamingBranch.label}
          confirmLabel="Rename"
          onCancel={() => setRenamingBranch(null)}
          onConfirm={(label) => {
            store.updateHappyPath(renamingBranch.pathId, (p) => ({
              ...p,
              branches: p.branches.map((b) =>
                b.id === renamingBranch.branchId ? { ...b, label } : b,
              ),
            }))
            setRenamingBranch(null)
          }}
        />
      )}

      {notes.element}
    </div>
  )
}

// ── View mode: the trunk → fork → branches visualisation ──────────────────────

function StepVizCard({
  name,
  inGraph,
  coverage,
}: {
  name: string
  inGraph: boolean
  coverage?: number
}) {
  return (
    <div
      style={{
        display: 'grid',
        justifyItems: 'center',
        gap: 2,
        padding: '10px 12px',
        borderRadius: 8,
        background: inGraph ? 'rgba(52,199,89,0.12)' : 'rgba(120,120,128,0.08)',
        border: `1px solid ${inGraph ? 'rgba(52,199,89,0.5)' : 'var(--separator-soft)'}`,
        textAlign: 'center',
      }}
      title={inGraph ? name : `${name} — not present in the filtered process`}
    >
      <span
        className="t-caption"
        style={{ fontWeight: 500, color: inGraph ? 'var(--primary)' : 'var(--secondary)' }}
      >
        {name}
      </span>
      {inGraph && coverage != null && (
        <span
          className="t-caption2 tnum"
          style={{ color: 'rgba(52,199,89,0.85)', fontWeight: 600 }}
        >
          {Math.round(coverage * 100)}%
        </span>
      )}
    </div>
  )
}

function Chevron() {
  return (
    <div
      className="fg-secondary"
      style={{ textAlign: 'center', fontSize: 11, padding: '3px 0', lineHeight: 1 }}
      aria-hidden
    >
      ⌄
    </div>
  )
}

function HappyPathVisualisation({
  path,
  coverage,
  inGraph,
}: {
  path: HappyPath
  coverage: Record<string, number>
  inGraph: Set<string>
}) {
  const hasBranches = path.branches.length > 0

  return (
    <div className="scroll-view" style={{ gap: 0, padding: '16px 0 24px' }}>
      {/* Trunk */}
      <div style={{ padding: '0 24px' }}>
        {path.steps.map((step, i) => (
          <div key={`${step}-${i}`}>
            <div style={{ position: 'relative' }}>
              <StepVizCard
                name={step}
                inGraph={inGraph.has(step)}
                coverage={coverage[step]}
              />
              {hasBranches && i === path.steps.length - 1 && (
                <span
                  style={{
                    position: 'absolute',
                    top: 8,
                    right: -10,
                    width: 20,
                    height: 20,
                    borderRadius: '50%',
                    background: 'var(--accent)',
                    color: '#fff',
                    display: 'grid',
                    placeItems: 'center',
                    fontSize: 12,
                    fontWeight: 700,
                    boxShadow: 'var(--shadow-sm)',
                  }}
                  title="Branches fork from here"
                  aria-hidden
                >
                  +
                </span>
              )}
            </div>
            {i < path.steps.length - 1 && <Chevron />}
          </div>
        ))}
      </div>

      {/* Fork divider + branch columns */}
      {hasBranches && (
        <>
          <div className="row" style={{ gap: 6, padding: '8px 24px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'rgba(120,120,128,0.25)' }} />
            <span className="fg-secondary" style={{ fontSize: 12 }} aria-hidden>
              ⑂
            </span>
            <div style={{ flex: 1, height: 1, background: 'rgba(120,120,128,0.25)' }} />
          </div>

          <div className="row" style={{ alignItems: 'flex-start', gap: 0 }}>
            {path.branches.map((branch, bi) => (
              <div key={branch.id} className="row" style={{ flex: 1, minWidth: 0, gap: 0 }}>
                {bi > 0 && (
                  <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--separator)' }} />
                )}
                <BranchColumn
                  branch={branch}
                  number={bi + 1}
                  coverage={coverage}
                  inGraph={inGraph}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function BranchColumn({
  branch,
  number,
  coverage,
  inGraph,
}: {
  branch: HappyPathBranch
  number: number
  coverage: Record<string, number>
  inGraph: Set<string>
}) {
  const label = branch.label || `Branch ${number}`
  return (
    <div className="col" style={{ flex: 1, minWidth: 0, gap: 0, padding: '10px 12px 12px' }}>
      <span
        className="t-caption2 fg-secondary"
        style={{ fontWeight: 600, textAlign: 'center', paddingBottom: 6 }}
      >
        {label}
      </span>
      {branch.steps.length === 0 ? (
        <span
          className="t-caption2 fg-tertiary"
          style={{ textAlign: 'center', padding: 12 }}
        >
          No steps
        </span>
      ) : (
        branch.steps.map((step, i) => (
          <div key={`${step}-${i}`}>
            <StepVizCard
              name={step}
              inGraph={inGraph.has(step)}
              coverage={coverage[step]}
            />
            {i < branch.steps.length - 1 && <Chevron />}
          </div>
        ))
      )}
    </div>
  )
}

// ── Edit mode ─────────────────────────────────────────────────────────────────

function AddStepMenu({
  label,
  steps,
  onPick,
}: {
  label: string
  steps: string[]
  onPick: (step: string) => void
}) {
  return (
    <select
      className="select-input"
      style={{ width: 'auto', maxWidth: 180 }}
      value=""
      onChange={(e) => {
        if (e.target.value) onPick(e.target.value)
      }}
      title="Add a step"
    >
      <option value="">{label} Add step…</option>
      {steps.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  )
}

function EditStepRow({
  name,
  inGraph,
  canMoveUp,
  canMoveDown,
  onMove,
  onRemove,
}: {
  name: string
  inGraph: boolean
  canMoveUp: boolean
  canMoveDown: boolean
  onMove: (delta: number) => void
  onRemove: () => void
}) {
  return (
    <div className="row" style={{ gap: 6 }}>
      <div
        className="row spacer"
        style={{
          padding: '7px 12px',
          borderRadius: 8,
          background: inGraph ? 'rgba(52,199,89,0.12)' : 'rgba(120,120,128,0.08)',
          border: `1px solid ${inGraph ? 'rgba(52,199,89,0.5)' : 'var(--separator-soft)'}`,
          fontSize: 12,
          fontWeight: 500,
          minWidth: 0,
          color: inGraph ? 'var(--primary)' : 'var(--secondary)',
        }}
        title={inGraph ? name : `${name} — not present in the filtered process`}
      >
        <span className="truncate">{name}</span>
      </div>
      <button
        className="icon-btn"
        style={{ width: 20, height: 20, fontSize: 10 }}
        disabled={!canMoveUp}
        title="Move up"
        onClick={() => onMove(-1)}
      >
        ▲
      </button>
      <button
        className="icon-btn"
        style={{ width: 20, height: 20, fontSize: 10 }}
        disabled={!canMoveDown}
        title="Move down"
        onClick={() => onMove(1)}
      >
        ▼
      </button>
      <button
        className="icon-btn"
        style={{ width: 20, height: 20, fontSize: 12, color: 'var(--red)' }}
        title="Remove step"
        onClick={onRemove}
      >
        ⊖
      </button>
    </div>
  )
}

function HappyPathEditor({
  path,
  available,
  inGraph,
  onRenameBranch,
}: {
  path: HappyPath
  available: string[]
  coverage: Record<string, number>
  inGraph: Set<string>
  onRenameBranch: (branchId: string, label: string) => void
}) {
  const store = useStore()

  return (
    <div className="scroll-view" style={{ gap: 14 }}>
      <div className="col" style={{ gap: 8 }}>
        <span className="sub-title">Trunk</span>
        {path.steps.map((step, i) => (
          <EditStepRow
            key={`${step}-${i}`}
            name={step}
            inGraph={inGraph.has(step)}
            canMoveUp={i > 0}
            canMoveDown={i < path.steps.length - 1}
            onMove={(delta) =>
              store.updateHappyPath(path.id, (p) => {
                const steps = [...p.steps]
                const target = i + delta
                if (target < 0 || target >= steps.length) return p
                ;[steps[i], steps[target]] = [steps[target], steps[i]]
                return { ...p, steps }
              })
            }
            onRemove={() =>
              store.updateHappyPath(path.id, (p) => ({
                ...p,
                steps: p.steps.filter((_, idx) => idx !== i),
              }))
            }
          />
        ))}
        {available.length > 0 && (
          <AddStepMenu
            label="＋"
            steps={available}
            onPick={(step) =>
              store.updateHappyPath(path.id, (p) =>
                p.steps.includes(step) ? p : { ...p, steps: [...p.steps, step] },
              )
            }
          />
        )}
      </div>

      <Divider />

      <div className="col" style={{ gap: 10 }}>
        <div className="row">
          <span className="sub-title spacer">Branches</span>
          <button
            className="btn small"
            onClick={() =>
              store.updateHappyPath(path.id, (p) => ({
                ...p,
                branches: [
                  ...p.branches,
                  {
                    id: crypto.randomUUID().toUpperCase(),
                    label: `Branch ${p.branches.length + 1}`,
                    steps: [],
                  },
                ],
              }))
            }
          >
            ＋ Branch
          </button>
        </div>

        {path.branches.length === 0 && (
          <span className="t-caption2 fg-tertiary">
            Optional. Each branch continues the trunk; every journey is scored against
            the branch it matches best.
          </span>
        )}

        {path.branches.map((branch, bIndex) => (
          <div
            key={branch.id}
            className="col"
            style={{ gap: 6, padding: 10, borderRadius: 8, background: 'var(--bg-fill)' }}
          >
            <div className="row">
              <span className="t-caption spacer" style={{ fontWeight: 600 }}>
                {branch.label || `Branch ${bIndex + 1}`}
              </span>
              <button
                className="icon-btn"
                style={{ width: 20, height: 20, fontSize: 11 }}
                title="Rename branch"
                onClick={() => onRenameBranch(branch.id, branch.label)}
              >
                ✎
              </button>
              <button
                className="icon-btn"
                style={{ width: 20, height: 20, fontSize: 11, color: 'var(--red)' }}
                title="Delete branch"
                onClick={() =>
                  store.updateHappyPath(path.id, (p) => ({
                    ...p,
                    branches: p.branches.filter((b) => b.id !== branch.id),
                  }))
                }
              >
                🗑
              </button>
            </div>

            {branch.steps.map((step, i) => (
              <EditStepRow
                key={`${step}-${i}`}
                name={step}
                inGraph={inGraph.has(step)}
                canMoveUp={i > 0}
                canMoveDown={i < branch.steps.length - 1}
                onMove={(delta) =>
                  store.updateHappyPath(path.id, (p) => ({
                    ...p,
                    branches: p.branches.map((b) => {
                      if (b.id !== branch.id) return b
                      const steps = [...b.steps]
                      const target = i + delta
                      if (target < 0 || target >= steps.length) return b
                      ;[steps[i], steps[target]] = [steps[target], steps[i]]
                      return { ...b, steps }
                    }),
                  }))
                }
                onRemove={() =>
                  store.updateHappyPath(path.id, (p) => ({
                    ...p,
                    branches: p.branches.map((b) =>
                      b.id === branch.id
                        ? { ...b, steps: b.steps.filter((_, idx) => idx !== i) }
                        : b,
                    ),
                  }))
                }
              />
            ))}

            {available.length > 0 && (
              <AddStepMenu
                label="＋"
                steps={available}
                onPick={(step) =>
                  store.updateHappyPath(path.id, (p) => ({
                    ...p,
                    branches: p.branches.map((b) =>
                      b.id === branch.id ? { ...b, steps: [...b.steps, step] } : b,
                    ),
                  }))
                }
              />
            )}
          </div>
        ))}
      </div>

      <Divider />
      <button
        className="btn small"
        style={{ alignSelf: 'flex-start' }}
        onClick={() => void store.refreshHappyPathConformance()}
      >
        ↻ Recompute conformance
      </button>
    </div>
  )
}
