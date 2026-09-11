/** ChartControls — the filter-preset picker with its inline manage/delete menu. */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ChartControls } from './ChartControls'
import { useStore } from '../store'
import { readSetting, writeSetting } from '../settings'
import type { FilterGroup } from '../types'

// One test flips the shared slider.mode setting. Restore it after unmounting: writeSetting
// notifies useSyncExternalStore subscribers, so resetting while ChartControls is still
// mounted would re-render it outside act().
afterEach(() => {
  cleanup()
  writeSetting('slider.mode', 'Range')
})

const group = (id: string, name: string): FilterGroup => ({
  id,
  name,
  fromDate: '',
  toDate: '',
  includedSteps: [],
  excludedSteps: [],
  meta1: '',
  meta2: '',
  meta3: '',
  minSteps: 0,
  maxSteps: 0,
  minJourneyTime: 0,
  maxJourneyTime: 0,
  minScore: 0,
  maxScore: 0,
})

const baseProps = {
  expanded: false, // collapsed → only the head (with the preset menu) renders
  onToggleExpanded: () => {},
  sliderMode: 'Range' as const,
  rangeMin: '2024-01-01',
  rangeMax: '2024-12-31',
  fromDate: '2024-01-01',
  toDate: '2024-12-31',
  onSliderChange: () => {},
  onSliderCommit: () => {},
  metric: 'Count' as const,
  onMetricChange: () => {},
  metricsDisabled: false,
  selectedPresetId: null,
  onApplyPreset: () => {},
}

describe('ChartControls preset menu', () => {
  it('is hidden when there are no presets', () => {
    useStore.setState({ filterGroups: [], selectedFilterGroupId: null, selectedProject: null })
    render(<ChartControls {...baseProps} />)
    expect(screen.queryByTitle('Filter presets')).toBeNull()
  })

  it('lists presets alphabetically ascending (A→Z)', () => {
    useStore.setState({
      filterGroups: [group('g1', 'Zeta'), group('g2', 'Alpha'), group('g3', 'Mid')],
      selectedFilterGroupId: null,
      selectedProject: null,
    })
    render(<ChartControls {...baseProps} />)

    fireEvent.click(screen.getByTitle('Filter presets'))
    const names = screen.getAllByRole('menuitem').map((b) => b.textContent?.trim())
    expect(names).toEqual(['Alpha', 'Mid', 'Zeta'])
  })

  it('shows every preset even when there are many (scrollable, none clipped)', () => {
    useStore.setState({
      filterGroups: Array.from({ length: 12 }, (_, i) =>
        group(`g${i}`, `Preset ${String.fromCharCode(65 + i)}`),
      ),
      selectedFilterGroupId: null,
      selectedProject: null,
    })
    render(<ChartControls {...baseProps} />)

    fireEvent.click(screen.getByTitle('Filter presets'))
    const menu = screen.getByRole('menu')
    expect(within(menu).getAllByRole('menuitem')).toHaveLength(12)
    // The list carries the .preset-menu scroll container (max-height + overflow
    // live in styles.css) rather than being an unbounded column.
    expect(menu).toHaveClass('preset-menu')
  })

  it('lists presets and applies the chosen one', () => {
    useStore.setState({
      filterGroups: [group('g1', 'Q1'), group('g2', 'Q2')],
      selectedFilterGroupId: null,
      selectedProject: null,
    })
    const onApplyPreset = vi.fn()
    render(<ChartControls {...baseProps} onApplyPreset={onApplyPreset} />)

    fireEvent.click(screen.getByTitle('Filter presets'))
    fireEvent.click(screen.getByRole('menuitem', { name: /Q1/ }))

    expect(onApplyPreset).toHaveBeenCalledWith(expect.objectContaining({ id: 'g1' }))
  })

  it('deletes a preset from its row in the menu', () => {
    useStore.setState({
      filterGroups: [group('g1', 'Q1'), group('g2', 'Q2')],
      selectedFilterGroupId: null,
      selectedProject: null,
    })
    render(<ChartControls {...baseProps} />)

    fireEvent.click(screen.getByTitle('Filter presets'))
    fireEvent.click(screen.getByLabelText('Delete preset Q1'))

    expect(useStore.getState().filterGroups.map((g) => g.id)).toEqual(['g2'])
  })
})

describe('ChartControls date-slider mode', () => {
  it('shows the Range/Day control right-aligned in the metric row', () => {
    useStore.setState({ filterGroups: [], selectedFilterGroupId: null, selectedProject: null })
    const { container } = render(<ChartControls {...baseProps} expanded />)
    const slider = container.querySelector('.metric-bar .metric-bar-slider')
    expect(slider).not.toBeNull()
    expect(slider?.textContent).toContain('Range')
    expect(slider?.textContent).toContain('Day')
  })

  it('writes slider.mode when a mode is picked', () => {
    writeSetting('slider.mode', 'Range')
    useStore.setState({ filterGroups: [], selectedFilterGroupId: null, selectedProject: null })
    const { container } = render(<ChartControls {...baseProps} expanded />)
    const slider = container.querySelector('.metric-bar-slider') as HTMLElement
    fireEvent.click(within(slider).getByText('Day'))
    expect(readSetting('slider.mode')).toBe('Day')
  })
})
