/** DetailPane view-mode menu — the advanced-analysis views (Conformance Check,
 *  Happy Path, Simulation) are power/admin only. */
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { DetailPane } from './DetailPane'
import { useStore } from '../store'

function openMenuAs(role: { authIsPower?: boolean; authIsAdmin?: boolean }) {
  useStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    connection: { isConnected: true } as any,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    selectedProject: { projectId: 'p', title: 'Project' } as any,
    activeChartMode: 'A-Chart',
    authIsPower: !!role.authIsPower,
    authIsAdmin: !!role.authIsAdmin,
    // No transitions → the active A-Chart shows a lightweight "no data" state
    // instead of mounting the full flow chart.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    processGraph: { steps: {}, transitions: [] } as any,
    isLoading: false,
  })
  render(
    <DetailPane sidebarHidden onShowSidebar={() => {}} onShowHelp={() => {}} />,
  )
  fireEvent.click(screen.getByTitle('Switch view'))
}

const POWER_ONLY = ['Conformance Check', 'Happy Path', 'Simulation']
const ALWAYS = ['A-Chart', 'Individual Journey', 'Statistics', 'Notes']

describe('DetailPane view-mode menu', () => {
  it('hides the power-only views from a plain user', () => {
    openMenuAs({})
    for (const label of ALWAYS) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument()
    }
    for (const label of POWER_ONLY) {
      expect(screen.queryByRole('button', { name: new RegExp(label) })).toBeNull()
    }
  })

  it('shows the power-only views to a power user', () => {
    openMenuAs({ authIsPower: true })
    for (const label of POWER_ONLY) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument()
    }
  })

  it('shows the power-only views to an admin', () => {
    openMenuAs({ authIsAdmin: true })
    for (const label of POWER_ONLY) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument()
    }
  })
})
