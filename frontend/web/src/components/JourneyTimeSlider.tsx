/** Date-window slider — port of `JourneyTimeSlider` from ProcessMapView.swift.
 *
 * `Range` mode has two thumbs; `Day` mode has one and commits a single day.
 * Committing only happens on release, so dragging never fires a query per pixel.
 *
 * Implemented with pointer-driven thumbs rather than two overlapping native
 * `<input type=range>` — those overlap unpredictably (the top input swallows the
 * other thumb's pointer events), which made Range mode effectively undraggable. */

import { useEffect, useRef, useState } from 'react'
import { addDays, daysBetween, formatDateShort, fromISODate, toISODate } from '../graph/format'
import type { SliderMode } from '../types'

const THUMB = 22 // px — keep in sync with .range-track .thumb width

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
  // Mirror of the live values for the pointer/key handlers (avoids stale closures).
  const vals = useRef({ from: localFrom, to: localTo })
  vals.current = { from: localFrom, to: localTo }

  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef<'from' | 'to' | null>(null)

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
    const { from, to } = vals.current
    if (mode === 'Day') {
      const day = isoFor(from)
      onCommit(day, day)
    } else {
      onCommit(isoFor(from), isoFor(to))
    }
  }

  const dayFromClientX = (clientX: number): number => {
    const el = trackRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const usable = rect.width - THUMB
    const frac = usable <= 0 ? 0 : (clientX - rect.left - THUMB / 2) / usable
    return Math.round(Math.max(0, Math.min(1, frac)) * totalDays)
  }

  // Move a thumb to `day`, clamped so the window can't invert, and push the
  // preview upward (no commit — that happens on release).
  const apply = (which: 'from' | 'to', day: number) => {
    if (mode === 'Day') {
      setLocalFrom(day)
      setLocalTo(day)
      vals.current = { from: day, to: day }
      onChange(isoFor(day), isoFor(day))
      return
    }
    if (which === 'from') {
      const clamped = Math.min(day, vals.current.to)
      setLocalFrom(clamped)
      vals.current = { ...vals.current, from: clamped }
      onChange(isoFor(clamped), isoFor(vals.current.to))
    } else {
      const clamped = Math.max(day, vals.current.from)
      setLocalTo(clamped)
      vals.current = { ...vals.current, to: clamped }
      onChange(isoFor(vals.current.from), isoFor(clamped))
    }
  }

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const day = dayFromClientX(e.clientX)
    // Grab the nearer thumb (Day mode has only one). Ties favour the start thumb.
    const which: 'from' | 'to' =
      mode === 'Range' &&
      Math.abs(day - vals.current.to) < Math.abs(day - vals.current.from)
        ? 'to'
        : 'from'
    dragging.current = which
    apply(which, day)
    // Capture so moves outside the track still track; guard — a synthetic or
    // already-released pointer id makes setPointerCapture throw, which must not
    // abort the drag.
    try {
      trackRef.current?.setPointerCapture?.(e.pointerId)
    } catch {
      /* ignore */
    }
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragging.current) apply(dragging.current, dayFromClientX(e.clientX))
  }

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return
    dragging.current = null
    try {
      trackRef.current?.releasePointerCapture?.(e.pointerId)
    } catch {
      /* ignore */
    }
    commit()
  }

  const onKeyDown = (which: 'from' | 'to') => (e: React.KeyboardEvent) => {
    let day: number | null = null
    const cur = which === 'to' ? vals.current.to : vals.current.from
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') day = cur - 1
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') day = cur + 1
    else if (e.key === 'Home') day = 0
    else if (e.key === 'End') day = totalDays
    else return
    e.preventDefault()
    apply(which, Math.max(0, Math.min(totalDays, day)))
    commit()
  }

  const frac = (day: number) => day / totalDays
  const thumbStyle = (day: number) => ({
    left: `calc(${frac(day)} * (100% - ${THUMB}px))`,
  })

  return (
    <div className="journey-slider">
      <div className="dates">
        <span>{formatDateShort(isoFor(localFrom))}</span>
        {mode === 'Range' && <span>{formatDateShort(isoFor(localTo))}</span>}
      </div>

      <div
        className="range-track"
        ref={trackRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div className="rail" />
        {mode === 'Range' && (
          <div
            className="fill"
            style={{
              left: `calc(${THUMB / 2}px + ${frac(localFrom)} * (100% - ${THUMB}px))`,
              width: `calc(${frac(localTo) - frac(localFrom)} * (100% - ${THUMB}px))`,
            }}
          />
        )}
        <div
          className="thumb"
          role="slider"
          tabIndex={0}
          aria-label={mode === 'Day' ? 'Day' : 'Window start'}
          aria-valuemin={0}
          aria-valuemax={totalDays}
          aria-valuenow={localFrom}
          style={thumbStyle(localFrom)}
          onKeyDown={onKeyDown('from')}
        />
        {mode === 'Range' && (
          <div
            className="thumb"
            role="slider"
            tabIndex={0}
            aria-label="Window end"
            aria-valuemin={0}
            aria-valuemax={totalDays}
            aria-valuenow={localTo}
            style={thumbStyle(localTo)}
            onKeyDown={onKeyDown('to')}
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
