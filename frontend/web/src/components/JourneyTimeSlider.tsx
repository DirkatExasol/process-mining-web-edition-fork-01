/** Date-window slider — port of `JourneyTimeSlider` from ProcessMapView.swift.
 *
 * `Range` mode has two thumbs; `Day` mode has one and commits a single day.
 * Committing only happens on release, so dragging never fires a query per pixel. */

import { useEffect, useState } from 'react'
import { addDays, daysBetween, formatDateShort, fromISODate, toISODate } from '../graph/format'
import type { SliderMode } from '../types'

export function JourneyTimeSlider({
  rangeMin,
  rangeMax,
  mode,
  fromDate,
  toDate,
  onChange,
  onCommit,
}: {
  rangeMin: string
  rangeMax: string
  mode: SliderMode
  fromDate: string
  toDate: string
  onChange: (from: string, to: string) => void
  onCommit: (from: string, to: string) => void
}) {
  const min = fromISODate(rangeMin)
  const max = fromISODate(rangeMax)

  const totalDays = min && max ? Math.max(0, daysBetween(min, max)) : 0

  const dayOf = (iso: string): number => {
    const date = fromISODate(iso)
    if (!date || !min) return 0
    return Math.max(0, Math.min(totalDays, daysBetween(min, date)))
  }

  const [localFrom, setLocalFrom] = useState(dayOf(fromDate))
  const [localTo, setLocalTo] = useState(dayOf(toDate))

  // External (programmatic) changes sync in silently — no commit.
  useEffect(() => {
    setLocalFrom(dayOf(fromDate))
    setLocalTo(dayOf(toDate))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromDate, toDate, rangeMin, rangeMax])

  if (!min || !max || totalDays <= 0) {
    return (
      <div className="journey-slider">
        <div className="row" style={{ gap: 8 }}>
          <input
            className="text-input"
            type="date"
            value={fromDate}
            onChange={(e) => onCommit(e.target.value, toDate)}
          />
          <span className="fg-secondary">–</span>
          <input
            className="text-input"
            type="date"
            value={toDate}
            onChange={(e) => onCommit(fromDate, e.target.value)}
          />
        </div>
      </div>
    )
  }

  const isoFor = (offset: number) => toISODate(addDays(min, offset))

  const commit = () => {
    if (mode === 'Day') {
      const day = isoFor(localFrom)
      onCommit(day, day)
    } else {
      onCommit(isoFor(localFrom), isoFor(localTo))
    }
  }

  const lowPct = (localFrom / totalDays) * 100
  const highPct = (localTo / totalDays) * 100

  return (
    <div className="journey-slider">
      <div className="dates">
        <span>{formatDateShort(isoFor(localFrom))}</span>
        {mode === 'Range' && <span>{formatDateShort(isoFor(localTo))}</span>}
      </div>

      <div className="range-track">
        <div className="rail" />
        {mode === 'Range' && (
          <div
            className="fill"
            style={{
              left: `calc(11px + ${lowPct}% - ${(lowPct / 100) * 22}px)`,
              width: `calc(${highPct - lowPct}% - ${((highPct - lowPct) / 100) * 22}px)`,
            }}
          />
        )}
        <input
          type="range"
          min={0}
          max={totalDays}
          value={localFrom}
          aria-label={mode === 'Day' ? 'Day' : 'Window start'}
          onChange={(e) => {
            const next = Number(e.target.value)
            if (mode === 'Day') {
              setLocalFrom(next)
              setLocalTo(next)
              onChange(isoFor(next), isoFor(next))
            } else {
              const clamped = Math.min(next, localTo)
              setLocalFrom(clamped)
              onChange(isoFor(clamped), isoFor(localTo))
            }
          }}
          onPointerUp={commit}
          onKeyUp={commit}
        />
        {mode === 'Range' && (
          <input
            type="range"
            min={0}
            max={totalDays}
            value={localTo}
            aria-label="Window end"
            onChange={(e) => {
              const clamped = Math.max(Number(e.target.value), localFrom)
              setLocalTo(clamped)
              onChange(isoFor(localFrom), isoFor(clamped))
            }}
            onPointerUp={commit}
            onKeyUp={commit}
          />
        )}
      </div>

      <div className="bounds">
        <span>{formatDateShort(rangeMin)}</span>
        <span>{formatDateShort(rangeMax)}</span>
      </div>
    </div>
  )
}
