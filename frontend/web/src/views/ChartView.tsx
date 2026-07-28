/** A-Chart / B-Chart panel — ports `aChartContent` / `bChartContent`. */

import { useEffect, useState } from 'react'
import { FlowChart, type SyncState } from '../flow/FlowChart'
import { Unavailable } from '../components/ui'
import { useSetting } from '../settings'
import { useStore } from '../store'
import { simulationFilterNotice, type SliderMode } from '../types'
import { ChartControls } from './ChartControls'
import { useNoteHandlers } from './useNoteHandlers'

export function ChartView({
  side,
  syncState,
}: {
  side: 'a' | 'b'
  syncState?: SyncState | null
}) {
  const store = useStore()
  const [sliderMode] = useSetting<SliderMode>('slider.mode')
  const [expanded, setExpanded] = useSetting<boolean>(
    side === 'a' ? 'achart.controlsExpanded' : 'bchart.controlsExpanded',
  )
  const [sliderFrom, setSliderFrom] = useState(store.fromDate)
  const [sliderTo, setSliderTo] = useState(store.toDate)
  const notes = useNoteHandlers()

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
        <FlowChart
          graph={store.processGraph}
          projectId={store.selectedProject.projectId}
          chartMode={side === 'a' ? 'A-Chart' : 'B-Chart'}
          metric={store.transitionMetric}
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
        />
      )}

      {notes.element}
    </div>
  )
}
