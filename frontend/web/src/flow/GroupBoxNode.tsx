import { memo } from 'react'
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
      className="group-box"
      style={{
        width,
        height,
        background: rgba(color, collapsed ? 0.13 : 0.07),
        border: `${collapsed ? 2 : 1.5}px ${collapsed ? 'solid' : 'dashed'} ${rgba(color, 0.45)}`,
        pointerEvents: 'all',
      }}
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
          right: 6,
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
