import { memo } from 'react'
import { EdgeLabelRenderer, type EdgeProps } from '@xyflow/react'
import {
  EDGE_SCHEMA_GRADIENTS,
  NOTE_YELLOW,
  interpolate,
  rgba,
  type EdgeColorSchema,
} from '../graph/colors'
import { formatCount, formatDuration } from '../graph/format'
import {
  isTimeBased,
  metricValue,
  type ProcessTransition,
  type TransitionMetric,
} from '../types'

export interface MetricEdgeData extends Record<string, unknown> {
  transition: ProcessTransition
  metric: TransitionMetric
  maxValue: number
  colorize: boolean
  schema: EdgeColorSchema
  /** Target-process / conformance overlay. */
  normValue: number | null
  normMetric: TransitionMetric
  showNorms: boolean
  showCompliance: boolean
  normIsMinimum: boolean
  /** Total occurrences leaving the source node — count norms are percentages. */
  outgoingTotal: number
  hasNote: boolean
  nodeH: number
  edgeScale: number
  onEdgeClick?: (transition: ProcessTransition, screen: { x: number; y: number }) => void
}

const SECONDARY = '#8E8E93'

/** Cubic path matching the Swift `addCurve` control points. */
function edgePath(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
): { path: string; midX: number; midY: number } {
  const dy = ty - sy
  const cpDist = Math.max(Math.abs(dy) * 0.45, 40)
  const path = `M ${sx},${sy} C ${sx},${sy + cpDist} ${tx},${ty - cpDist} ${tx},${ty}`
  return { path, midX: (sx + tx) / 2, midY: (sy + ty) / 2 }
}

function MetricEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps) {
  const d = data as MetricEdgeData
  const {
    transition,
    metric,
    maxValue,
    colorize,
    schema,
    normValue,
    normMetric,
    showNorms,
    showCompliance,
    normIsMinimum,
    outgoingTotal,
    hasNote,
    nodeH,
    edgeScale,
    onEdgeClick,
  } = d
  const eScale = edgeScale || 1

  const isSelfLoop = transition.fromStep === transition.toStep
  const isCountPct = normMetric === 'Count'

  let lineWidth: number
  let lineAlpha: number
  let lineColor: string
  let labelText: string
  let useBadge = false

  if (showNorms) {
    useBadge = true
    const actual = isCountPct
      ? outgoingTotal > 0
        ? (transition.occurrences / outgoingTotal) * 100
        : 0
      : (metricValue(transition, normMetric) ?? transition.occurrences)

    if (showCompliance) {
      // Compliance: width by actual metric ratio, colour by actual-vs-norm.
      const ratio = Math.max(0, Math.min(1, actual / Math.max(maxValue, 1)))
      lineWidth = 3 + ratio * 19
      lineAlpha = 0.45 + ratio * 0.35
      lineColor =
        normValue == null
          ? SECONDARY
          : (normIsMinimum ? actual >= normValue : actual <= normValue)
            ? '#34C759'
            : '#FF3B30'
      labelText = isCountPct
        ? `${Math.round(actual)}%`
        : isTimeBased(normMetric)
          ? (() => {
              const v = metricValue(transition, normMetric)
              return v == null ? '—' : formatDuration(v)
            })()
          : formatCount(transition.occurrences)
    } else {
      // Target process: uniform appearance, show the stored norm.
      lineWidth = 6
      lineAlpha = 0.4
      lineColor = SECONDARY
      labelText =
        normValue == null
          ? '—'
          : isCountPct
            ? `${Math.round(normValue)}%`
            : isTimeBased(normMetric)
              ? formatDuration(normValue)
              : formatCount(Math.round(normValue))
    }
  } else {
    const value = metricValue(transition, metric) ?? transition.occurrences
    const ratio = Math.max(0, Math.min(1, value / Math.max(maxValue, 1)))
    lineWidth = 3 + ratio * 19
    lineAlpha = 0.3 + ratio * 0.5
    const gradient = EDGE_SCHEMA_GRADIENTS[schema]
    lineColor =
      colorize && gradient ? interpolate(gradient.low, gradient.high, ratio) : SECONDARY
    labelText = isTimeBased(metric)
      ? (() => {
          const v = metricValue(transition, metric)
          return v == null ? '—' : formatDuration(v)
        })()
      : formatCount(transition.occurrences)
  }

  const stroke = rgba(lineColor, lineAlpha)
  const arrowSize = Math.max(5, lineWidth * 0.75)

  let path: string
  let midX: number
  let midY: number

  if (isSelfLoop) {
    // Circle above the node, radius 18, offset 2.2·r above the top edge.
    const r = 18
    const cx = sourceX
    const cy = sourceY - nodeH - r * 2.2 + r
    path = `M ${cx - r},${cy} a ${r},${r} 0 1,0 ${r * 2},0 a ${r},${r} 0 1,0 ${-r * 2},0`
    midX = cx
    midY = cy
  } else {
    const geometry = edgePath(sourceX, sourceY, targetX, targetY)
    path = geometry.path
    midX = geometry.midX
    midY = geometry.midY
  }

  const markerId = `arrow-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`

  const badgeWidth = Math.round(Math.max(44, labelText.length * 9 + 18) * eScale)
  const hasNorm = normValue != null
  const badgeColor = showCompliance
    ? lineColor
    : hasNorm
      ? 'var(--accent)'
      : SECONDARY
  const badgeOpacity = hasNorm || showCompliance ? 0.88 : 0.3

  return (
    <>
      {!isSelfLoop && (
        <defs>
          <marker
            id={markerId}
            markerWidth={arrowSize * 2}
            markerHeight={arrowSize * 1.6}
            refX={arrowSize}
            refY={arrowSize * 1.6}
            orient="auto-start-reverse"
            markerUnits="userSpaceOnUse"
          >
            <polygon
              points={`${arrowSize},${arrowSize * 1.6} 0,0 ${arrowSize * 2},0`}
              fill={rgba(lineColor, Math.min(1, lineAlpha + 0.1))}
            />
          </marker>
        </defs>
      )}

      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth={lineWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        markerEnd={isSelfLoop ? undefined : `url(#${markerId})`}
      />
      {/* Wide invisible hit area so thin edges stay clickable. */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={Math.max(lineWidth, 24)}
        style={{ cursor: onEdgeClick ? 'pointer' : 'default' }}
        onClick={(event) =>
          onEdgeClick?.(transition, { x: event.clientX, y: event.clientY })
        }
      />

      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${midX}px, ${midY}px)`,
            pointerEvents: 'all',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
          onClick={(event) =>
            onEdgeClick?.(transition, { x: event.clientX, y: event.clientY })
          }
        >
          {useBadge ? (
            <span
              className="edge-badge-text"
              style={{
                minWidth: badgeWidth,
                height: Math.round(22 * eScale),
                fontSize: `${13 * eScale}px`,
                display: 'grid',
                placeItems: 'center',
                borderRadius: Math.round(11 * eScale),
                background:
                  badgeColor === 'var(--accent)'
                    ? `rgba(10, 132, 255, ${badgeOpacity})`
                    : rgba(badgeColor, badgeOpacity),
                color: hasNorm || showCompliance ? '#fff' : 'var(--secondary)',
                cursor: onEdgeClick ? 'pointer' : 'default',
              }}
              title={`${transition.fromStep} → ${transition.toStep}`}
            >
              {labelText}
            </span>
          ) : (
            <span
              className="edge-badge-text"
              style={{
                padding: '1px 6px',
                borderRadius: 6,
                fontSize: `${13 * eScale}px`,
                background: 'var(--bg-grouped)',
                color: 'var(--primary)',
                cursor: onEdgeClick ? 'pointer' : 'default',
              }}
              title={`${transition.fromStep} → ${transition.toStep} · ${transition.occurrences.toLocaleString()}`}
            >
              {labelText}
            </span>
          )}

          {hasNote && (
            <span
              style={{
                width: 14,
                height: 14,
                borderRadius: 7,
                display: 'grid',
                placeItems: 'center',
                background: NOTE_YELLOW,
                color: 'rgba(0,0,0,0.75)',
                fontSize: 9,
                boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
              }}
              title="This transition has notes"
            >
              ✎
            </span>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

export const MetricEdge = memo(MetricEdgeComponent)
