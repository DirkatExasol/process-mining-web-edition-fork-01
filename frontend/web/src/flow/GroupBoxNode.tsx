import { memo, type CSSProperties } from 'react'
import type { NodeProps } from '@xyflow/react'
import { COLLAPSE_BADGE_GREEN, COLLAPSE_BADGE_RED, rgba } from '../graph/colors'

export interface GroupBoxData extends Record<string, unknown> {
  group: string
  width: number
  height: number
  color: string
  collapsed: boolean
  scale: number // group-title font scale
  onToggle: (group: string) => void
}

/**
 * The dashed BELONGS_TO box drawn behind the nodes, with its name pill and the
 * green/red collapse badge — ports the group section of `drawContent`.
 * Dragging the box moves every member node, matching the Swift group drag.
 */
function GroupBoxNodeComponent({ data }: NodeProps) {
  const { group, width, height, color, collapsed, scale, onToggle } = data as GroupBoxData
  const gs = scale || 1

  return (
    <div
      className={`group-box${collapsed ? ' collapsed' : ''}`}
      style={
        {
          width,
          height,
          // The box tint + border derive from this per-group colour in CSS, so
          // the opacity can be theme-aware (stronger, and lightened on dark).
          '--gc': color,
          pointerEvents: 'all',
        } as CSSProperties & Record<string, string | number>
      }
    >
      <span
        className="group-label"
        style={{
          background: rgba(color, 0.9),
          // Scale the title pill (font + box) with the group-title font setting.
          fontSize: `${11 * gs}px`,
          height: Math.round(20 * gs),
          top: Math.round((-20 * gs) / 2),
          padding: `0 ${Math.round(10 * gs)}px`,
          borderRadius: Math.round(10 * gs),
        }}
      >
        {group}
      </span>
      <button
        className="group-toggle"
        style={{
          // Scale the collapse/expand handle with the group-title font setting so
          // it stays proportional to the (scaled) title pill.
          right: Math.round(6 * gs),
          top: Math.round(-11 * gs),
          width: Math.round(22 * gs),
          height: Math.round(22 * gs),
          borderRadius: Math.round(11 * gs),
          fontSize: `${14 * gs}px`,
          background: collapsed ? COLLAPSE_BADGE_GREEN : COLLAPSE_BADGE_RED,
        }}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation()
          onToggle(group)
        }}
        title={collapsed ? `Expand ${group}` : `Collapse ${group}`}
        aria-label={collapsed ? `Expand ${group}` : `Collapse ${group}`}
      >
        {collapsed ? '+' : '−'}
      </button>
    </div>
  )
}

export const GroupBoxNode = memo(GroupBoxNodeComponent)
