/** A-Chart / B-Chart panel — ports `aChartContent` / `bChartContent`. */

import { useEffect, useState } from 'react'
import { FlowChart, type SyncState } from '../flow/FlowChart'
import { SankeyChart } from '../flow/SankeyChart'
import { Unavailable } from '../components/ui'
import { useSetting } from '../settings'
import { useStore } from '../store'
import { simulationFilterNotice, type SliderMode } from '../types'
import { ChartControls } from './ChartControls'
import { useNoteHandlers } from './useNoteHandlers'
import { api } from '../api'
import { resolveScope } from '../actions/resolveScope'
import type { ActionRunResult, SavedAction } from '../actions/types'
import { ActionResultModal } from './ActionResultModal'
import { AggregateSetDialog } from './AggregateSetDialog'

export function ChartView({
  side,
  syncState,
}: {
  side: 'a' | 'b'
  syncState?: SyncState | null
}) {
  const store = useStore()
  const [sliderMode] = useSetting<SliderMode>('slider.mode')
  const [sankey, setSankey] = useSetting<boolean>('graph.sankeyView')
  const [expanded, setExpanded] = useSetting<boolean>(
    side === 'a' ? 'achart.controlsExpanded' : 'bchart.controlsExpanded',
  )
  const [sliderFrom, setSliderFrom] = useState(store.fromDate)
  const [sliderTo, setSliderTo] = useState(store.toDate)
  const notes = useNoteHandlers()

  // Node-menu actions: available to run for power/dev/admin when the feature is enabled.
  const runRole = store.authIsPower || store.authIsDeveloper || store.authIsAdmin
  const actionItems = store.actionsEnabled && runRole ? store.projectActions : []
  const [actionModal, setActionModal] = useState<{
    title: string
    result: ActionRunResult | null
    busy: boolean
    error: string | null
  } | null>(null)

  // Aggregate designer: developers can collapse a connected step selection into a Σ step.
  const canAggregate = store.authIsDeveloper || store.authIsAdmin
  const [aggregateGroups, setAggregateGroups] = useState<string[][] | null>(null)

  // A drill-down detail project (id "aggd_…") is a black-box sub-process: no Sankey, and a
  // Return button back to the high-level map it was reached from.
  const isDetailProject = !!store.selectedProject?.projectId.startsWith('aggd_')

  const runNodeAction = async (action: SavedAction, node: string) => {
    const connId = store.connection.activeProfileId ?? ''
    const projectId = store.selectedProject?.projectId ?? ''
    const resolvedSteps = resolveScope(action.spec.from.selectors, node, store.processGraph.transitions)
    setActionModal({ title: `${action.name} · ${node}`, result: null, busy: true, error: null })
    try {
      const result = await api.runAction(projectId, action.id, {
        connectionId: connId,
        filter: store.currentFilterSpec(),
        contextNode: node,
        resolvedSteps,
      })
      setActionModal({ title: `${action.name} · ${node}`, result, busy: false, error: null })
    } catch (e) {
      setActionModal({
        title: `${action.name} · ${node}`,
        result: null,
        busy: false,
        error: String((e as Error).message ?? e),
      })
    }
  }

  // Keep the slider in sync with the store's applied window. This covers project
  // load (the "last N days" default), a Day snap to the nearest date, and — the
  // reason this keys on fromDate/toDate rather than only the load-time values —
  // applying a preset from the left sidebar, which sets the window in the store
  // without going through the chart's own slider. A drag only moves local state
  // (the store commits on release), so this never clobbers a drag in progress.
  useEffect(() => {
    setSliderFrom(store.fromDate)
    setSliderTo(store.toDate)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.selectedProject, store.fromDate, store.toDate])

  const hasData = store.processGraph.transitions.length > 0
  const rangeMin =
    store.projectMinDate < store.initialToDate ? store.projectMinDate : store.initialFromDate

  if (!store.selectedProject) {
    return (
      <Unavailable
        glyph="🗺"
        title="No Project Selected"
        description="Select a project from the sidebar."
      />
    )
  }

  if (store.errorMessage && !store.isLoading) {
    return (
      <Unavailable glyph="⚠️" title="Failed to Load" description={store.errorMessage} />
    )
  }

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      {hasData && (
        <ChartControls
          expanded={expanded}
          onToggleExpanded={() => setExpanded(!expanded)}
          sliderMode={sliderMode}
          rangeMin={rangeMin}
          rangeMax={store.initialToDate}
          fromDate={sliderFrom}
          toDate={sliderTo}
          onSliderChange={(from, to) => {
            setSliderFrom(from)
            setSliderTo(to)
          }}
          onSliderCommit={(from, to) => {
            if (sliderMode === 'Day') {
              void store.reloadGraphForDay(from).then((actual) => {
                if (actual && actual !== from) {
                  setSliderFrom(actual)
                  setSliderTo(actual)
                }
              })
            } else {
              store.patch({ fromDate: from, toDate: to })
              void store.reloadGraph()
            }
          }}
          metric={store.transitionMetric}
          onMetricChange={(m) => store.setTransitionMetric(m)}
          metricsDisabled={!hasData}
          selectedPresetId={store.selectedFilterGroupId}
          onApplyPreset={(group) => {
            store.applyFilterGroup(group)
            setSliderFrom(group.fromDate.slice(0, 10))
            setSliderTo(group.toDate.slice(0, 10))
            void store.reloadGraph()
          }}
        />
      )}

      {!hasData ? (
        store.isLoading ? (
          <div className="center-fill">
            <span className="spinner large" />
            <span>
              {side === 'a' ? 'Loading process map' : 'Loading B-Chart'}
            </span>
          </div>
        ) : (
          <Unavailable
            glyph="📊"
            title="No Process Data"
            description={
              side === 'a'
                ? 'No event transitions found for this project.'
                : 'Use the sidebar filters and tap Apply to load the B-Chart.'
            }
            action={
              <button
                className="btn prominent"
                onClick={() => void store.reloadGraph()}
              >
                Load
              </button>
            }
          />
        )
      ) : (
        <div className="col" style={{ flex: 1, minHeight: 0, position: 'relative' }}>
          {/* A drilled-into detail project offers a Return button (back to the high-level
              map) instead of the flowchart/Sankey switch — and never shows the Sankey. */}
          {isDetailProject ? (
            store.drillReturn && (
              <div className="swim-toggle seg-toggle" role="toolbar">
                <button
                  className="seg sel"
                  onClick={() => void store.returnFromDrill()}
                  title={`Back to “${store.drillReturn.title}”`}
                >
                  ← Return to high-level map
                </button>
              </div>
            )
          ) : (
            /* In-canvas view switch (flowchart ↔ Sankey), like the Individual Journey's. */
            <div className="swim-toggle seg-toggle" role="tablist" aria-label="Chart view">
              <button
                className={`seg${sankey ? '' : ' sel'}`}
                role="tab"
                aria-selected={!sankey}
                onClick={() => setSankey(false)}
                title="Directed-follows flowchart (loops shown)"
              >
                🕸 Flowchart
              </button>
              <button
                className={`seg${sankey ? ' sel' : ''}`}
                role="tab"
                aria-selected={sankey}
                onClick={() => setSankey(true)}
                title="Sankey flow (looping clusters collapsed for readability)"
              >
                🌊 Sankey
              </button>
            </div>
          )}

          {sankey && !isDetailProject ? (
            <SankeyChart
              graph={store.processGraph}
              metric={store.transitionMetric}
              journeyTotal={store.journeyCount ?? 0}
            />
          ) : (
            <FlowChart
              graph={store.processGraph}
              projectId={store.selectedProject.projectId}
              chartMode={side === 'a' ? 'A-Chart' : 'B-Chart'}
              metric={store.transitionMetric}
              journeyTotal={store.journeyCount ?? 0}
              allowTransitionTable
              isLoading={store.isLoading}
              syncState={syncState}
              notice={simulationFilterNotice(
                side === 'a' ? store.abDataSourceA : store.abDataSourceB,
              )}
              readOnly={
                (side === 'a' ? store.abDataSourceA : store.abDataSourceB).kind ===
                'simulation'
              }
              onNodeAction={(node, action) => store.handleNodeAction(node, action)}
              notes={store.projectNotes}
              onNodeNote={notes.openNodeNotes}
              onEdgeNote={notes.openEdgeNotes}
              actionItems={actionItems}
              onRunAction={(action, node) => void runNodeAction(action, node)}
              onCreateAggregate={canAggregate ? (groups) => setAggregateGroups(groups) : undefined}
              isHighLevelMap={store.projectAggregates.length > 0}
              aggregateLinks={store.projectAggregates}
              onDrillDown={(link) => void store.drillDownTo(link)}
            />
          )}
        </div>
      )}

      {hasData && store.queryMs != null && (
        <div className="chart-footer" title="Server-side execution time of the queries behind this view">
          <span className="spacer" />
          <span>
            Query time:{' '}
            {store.queryMs < 1000
              ? `${store.queryMs} ms`
              : `${(store.queryMs / 1000).toFixed(2)} s`}
          </span>
        </div>
      )}

      {notes.element}

      {actionModal && (
        <ActionResultModal
          title={actionModal.title}
          result={actionModal.result}
          busy={actionModal.busy}
          error={actionModal.error}
          onClose={() => setActionModal(null)}
        />
      )}

      {aggregateGroups && store.selectedProject && (
        <AggregateSetDialog
          groups={aggregateGroups}
          transitions={store.processGraph.transitions}
          projectId={store.selectedProject.projectId}
          connectionId={store.connection.activeProfileId ?? ''}
          projectTitle={store.selectedProject.title}
          addMode={store.projectAggregates.length > 0}
          onClose={() => setAggregateGroups(null)}
          onDone={(result) => {
            setAggregateGroups(null)
            void store.loadProjects()
            void store.loadProjectAggregates()
            const here = result.highLevelConnectionId === store.connection.activeProfileId
            const n = result.aggregates.length
            store.showAlert({
              title: 'Aggregates created',
              message: here
                ? `Built the high-level map with ${n} new Σ step${n === 1 ? '' : 's'} and ${n === 1 ? 'its detail project' : 'their detail projects'} in this connection's schema. If you don't see them in the Projects list, refresh — they only appear here when the schema was left blank (same schema); a new schema/connection must be opened separately.`
                : `Wrote the high-level map and ${n} detail project${n === 1 ? '' : 's'} to another connection/schema. Connect to that schema to open them — they won't appear in this Projects list.`,
              primaryLabel: 'OK',
            })
          }}
        />
      )}
    </div>
  )
}
