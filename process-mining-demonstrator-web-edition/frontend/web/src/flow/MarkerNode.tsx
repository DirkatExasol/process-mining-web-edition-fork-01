import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { END_ARROW_COLOR, START_ARROW_COLOR } from '../graph/colors'

export interface MarkerData extends Record<string, unknown> {
  kind: 'start' | 'end'
}

/** Geometry from `drawStartArrow` / `drawEndArrow`: 46 pt stem, 15 pt head,
 *  13 pt half-width, 7 pt dot. */
export const MARKER_W = 30
export const MARKER_H = 60

function MarkerNodeComponent({ data }: NodeProps) {
  const { kind } = data as MarkerData
  const color = kind === 'start' ? START_ARROW_COLOR : END_ARROW_COLOR

  // Both markers point downward (matching drawStartArrow / drawEndArrow): the dot
  // sits at the top and the arrowhead at the bottom. The start marker is placed
  // above a node so it points into it; the end marker is placed below a node so
  // it points away from it — same glyph, opposite placement.
  const cx = MARKER_W / 2
  const dotY = 7
  const tipY = MARKER_H
  const headBaseY = MARKER_H - 15
  const stemFrom = dotY + 9

  return (
    <svg
      width={MARKER_W}
      height={MARKER_H}
      style={{ overflow: 'visible', pointerEvents: 'none' }}
      aria-hidden
    >
      <g style={{ filter: 'drop-shadow(0 2px 5px rgba(0,0,0,0.35))' }}>
        <line
          x1={cx}
          y1={stemFrom}
          x2={cx}
          y2={headBaseY}
          stroke={color}
          strokeWidth={4}
          strokeLinecap="round"
        />
        <polygon
          points={`${cx},${tipY} ${cx - 13},${headBaseY} ${cx + 13},${headBaseY}`}
          fill={color}
        />
        <circle cx={cx} cy={dotY} r={7} fill={color} />
      </g>
    </svg>
  )
}

export const MarkerNode = memo(MarkerNodeComponent)
