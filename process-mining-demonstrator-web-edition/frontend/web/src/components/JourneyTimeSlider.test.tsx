/** JourneyTimeSlider — the pointer/keyboard date-window slider.
 *
 * Pointer dragging depends on real layout (getBoundingClientRect), which jsdom
 * reports as zero-sized, so drag geometry is verified in the browser harness.
 * Here we cover the structure and the keyboard path — which drives the same
 * `apply`/`commit`/clamp logic a drag does — so a regression in either thumb's
 * movement or the no-invert clamp is caught. */

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { JourneyTimeSlider } from './JourneyTimeSlider'

const base = {
  rangeMin: '2024-01-01',
  rangeMax: '2024-12-31',
  fromDate: '2024-02-01',
  toDate: '2024-03-01',
}

describe('JourneyTimeSlider', () => {
  it('renders two independent thumbs in Range mode', () => {
    render(<JourneyTimeSlider {...base} mode="Range" onChange={() => {}} onCommit={() => {}} />)
    expect(screen.getByRole('slider', { name: 'Window start' })).toBeInTheDocument()
    expect(screen.getByRole('slider', { name: 'Window end' })).toBeInTheDocument()
  })

  it('renders a single thumb in Day mode', () => {
    render(<JourneyTimeSlider {...base} mode="Day" onChange={() => {}} onCommit={() => {}} />)
    expect(screen.getAllByRole('slider')).toHaveLength(1)
    expect(screen.getByRole('slider', { name: 'Day' })).toBeInTheDocument()
  })

  it('moves the start thumb with the keyboard and commits the new window', () => {
    const onCommit = vi.fn()
    render(
      <JourneyTimeSlider {...base} mode="Range" onChange={() => {}} onCommit={onCommit} />,
    )
    fireEvent.keyDown(screen.getByRole('slider', { name: 'Window start' }), {
      key: 'ArrowRight',
    })
    // 2024-02-01 → +1 day = 2024-02-02; end untouched.
    expect(onCommit).toHaveBeenCalledWith('2024-02-02', '2024-03-01')
  })

  it('moves the end thumb independently of the start thumb', () => {
    const onCommit = vi.fn()
    render(
      <JourneyTimeSlider {...base} mode="Range" onChange={() => {}} onCommit={onCommit} />,
    )
    fireEvent.keyDown(screen.getByRole('slider', { name: 'Window end' }), {
      key: 'ArrowLeft',
    })
    // 2024-03-01 → −1 day = 2024-02-29 (leap year); start untouched.
    expect(onCommit).toHaveBeenCalledWith('2024-02-01', '2024-02-29')
  })

  it('clamps so the start thumb cannot pass the end thumb', () => {
    const onCommit = vi.fn()
    render(
      <JourneyTimeSlider {...base} mode="Range" onChange={() => {}} onCommit={onCommit} />,
    )
    // End key jumps the start thumb to the far right — but it is clamped to the
    // end thumb's day, never beyond it.
    fireEvent.keyDown(screen.getByRole('slider', { name: 'Window start' }), { key: 'End' })
    expect(onCommit).toHaveBeenCalledWith('2024-03-01', '2024-03-01')
  })

  it('commits a single day in Day mode', () => {
    const onCommit = vi.fn()
    render(
      <JourneyTimeSlider
        {...base}
        fromDate="2024-02-10"
        toDate="2024-02-10"
        mode="Day"
        onChange={() => {}}
        onCommit={onCommit}
      />,
    )
    fireEvent.keyDown(screen.getByRole('slider', { name: 'Day' }), { key: 'ArrowRight' })
    expect(onCommit).toHaveBeenCalledWith('2024-02-11', '2024-02-11')
  })
})
