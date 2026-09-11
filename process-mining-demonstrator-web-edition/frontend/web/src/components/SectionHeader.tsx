/** A collapsible section header (chevron + title + count, with an optional trailing
 *  control) used by the integration console's left-panel sections. Matches the main
 *  app sidebar's section-header styling. */

import type { ReactNode } from 'react'
import { Chevron } from './ui'

export function SectionHeader({
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
