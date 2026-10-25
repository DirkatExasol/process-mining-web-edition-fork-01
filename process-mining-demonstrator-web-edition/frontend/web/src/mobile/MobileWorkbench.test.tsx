/** WorkBench Mobile shell — the desktop-only-view redirect and the view switcher. */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, within } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    dashboard: vi.fn(async () => ({ connections: [] })),
    listNotifications: vi.fn(async () => ({ rules: [], canManage: false })),
    patchSettings: vi.fn(async () => ({})),
    settings: vi.fn(async () => ({})),
  },
}))

import { MobileWorkbench } from './MobileWorkbench'
import { useStore } from '../store'
import { renderSettled } from '../test/renderSettled'

beforeEach(() => {
  useStore.setState({ isPhone: true } as never)
})

describe('MobileWorkbench', () => {
  it('redirects a desktop-only view (A/B Comparison) to the Dashboard with a note', async () => {
    useStore.setState({ activeChartMode: 'A/B Comparison' } as never)
    await renderSettled(<MobileWorkbench onShowHelp={() => {}} />)
    expect(useStore.getState().activeChartMode).toBe('Dashboard')
    expect(screen.getByText(/isn.t available on mobile/)).toBeTruthy()
  })

  it('offers only the phone-supported views in the switcher', async () => {
    useStore.setState({ activeChartMode: 'Dashboard' } as never)
    await renderSettled(<MobileWorkbench onShowHelp={() => {}} />)
    fireEvent.click(screen.getByLabelText('Switch view'))
    const sheet = screen.getByRole('dialog', { name: 'Switch view' })
    for (const m of ['Dashboard', 'A-Chart', 'Individual Journey', 'Notes', 'AI supported Documentation']) {
      expect(within(sheet).getByText(m)).toBeTruthy()
    }
    // Desktop-only modes are absent from the sheet.
    expect(within(sheet).queryByText('A/B Comparison')).toBeNull()
    expect(within(sheet).queryByText('Simulation')).toBeNull()
    expect(within(sheet).queryByText('Statistics')).toBeNull()
  })
})
