/** "Date & Metrics" card shared by the A-Chart, B-Chart and A/B panels —
 *  ports the controls card from ProcessMapView.swift. */

import { JourneyTimeSlider } from '../components/JourneyTimeSlider'
import { Chevron, Divider } from '../components/ui'
import { useStore } from '../store'
import { TRANSITION_METRICS, type FilterGroup, type SliderMode, type TransitionMetric } from '../types'

const METRIC_ICONS: Record<TransitionMetric, string> = {
  Count: '#',
  'Avg Time': '⏱',
  'Min Time': '⌄',
  'Max Time': '⌃',
  'Std Dev': '〰',
}

export function ChartControls({
  expanded,
  onToggleExpanded,
  sliderMode,
  rangeMin,
  rangeMax,
  fromDate,
  toDate,
  onSliderChange,
  onSliderCommit,
  metric,
  onMetricChange,
  metricsDisabled,
  selectedPresetId,
  onApplyPreset,
}: {
  expanded: boolean
  onToggleExpanded: () => void
  sliderMode: SliderMode
  rangeMin: string
  rangeMax: string
  fromDate: string
  toDate: string
  onSliderChange: (from: string, to: string) => void
  onSliderCommit: (from: string, to: string) => void
  metric: TransitionMetric
  onMetricChange: (metric: TransitionMetric) => void
  metricsDisabled: boolean
  selectedPresetId: string | null
  onApplyPreset: (group: FilterGroup) => void
}) {
  const store = useStore()

  return (
    <div className="controls-card">
      <div className="controls-head">
        <button className="expander" onClick={onToggleExpanded}>
          <Chevron open={expanded} />
          Date &amp; Metrics
        </button>
        {store.filterGroups.length > 0 && (
          <select
            className="select-input"
            style={{ width: 'auto', fontSize: 10, padding: '4px 6px', marginRight: 8 }}
            value={selectedPresetId ?? ''}
            onChange={(e) => {
              const group = store.filterGroups.find((g) => g.id === e.target.value)
              if (group) onApplyPreset(group)
            }}
            title="Filter presets"
          >
            <option value="">Presets</option>
            {store.filterGroups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {expanded && (
        <>
          <Divider />
          <JourneyTimeSlider
            rangeMin={rangeMin}
            rangeMax={rangeMax}
            mode={sliderMode}
            fromDate={fromDate}
            toDate={toDate}
            onChange={onSliderChange}
            onCommit={onSliderCommit}
          />
          <Divider />
          <div className="metric-bar">
            {TRANSITION_METRICS.map((m) => (
              <button
                key={m}
                className={`chip${metric === m ? ' active' : ''}`}
                disabled={metricsDisabled}
                onClick={() => onMetricChange(m)}
              >
                <span aria-hidden>{METRIC_ICONS[m]}</span> {m}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
