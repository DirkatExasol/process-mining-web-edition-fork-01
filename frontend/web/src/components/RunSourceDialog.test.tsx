import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    runSource: vi.fn(async () => ({ records: 12, detail: '12 events written, 1 skipped' })),
    integrationStatus: vi.fn(async () => ({ state: 'completed', recordsDone: 0, recordsTotal: 0 })),
  },
}))

import { api } from '../api'
import { useStore } from '../store'
import { RunSourceDialog } from './RunSourceDialog'
import type { Source } from '../types'

const SOURCE: Source = {
  id: 's1', owner: 'dev', name: 'Access log', kind: 'file',
  config: { path: '/x.log', sourceTypeId: 'st1' }, createdAt: '',
}

afterEach(() => {
  vi.clearAllMocks()
  useStore.setState({ connections: [], connection: { isConnected: false, activeProfileId: null } as never })
})

describe('RunSourceDialog', () => {
  it('runs the extraction against the active connection', async () => {
    useStore.setState({
      connections: [{ id: 'c1', name: 'Prod DB' }] as never,
      connection: { isConnected: true, activeProfileId: 'c1' } as never,
    })
    render(<RunSourceDialog source={SOURCE} onClose={() => {}} onDone={() => {}} />)

    fireEvent.change(screen.getByPlaceholderText(/RETAIL-DEMO/i), { target: { value: 'P1' } })
    fireEvent.click(screen.getByRole('button', { name: /Run extraction/i }))

    await waitFor(() => expect(api.runSource).toHaveBeenCalledWith('s1', 'P1'))
    await waitFor(() => expect(screen.getByText(/12 events written/)).toBeTruthy())
  })

  it('blocks running when not connected', () => {
    useStore.setState({
      connections: [] as never,
      connection: { isConnected: false, activeProfileId: null } as never,
    })
    render(<RunSourceDialog source={SOURCE} onClose={() => {}} onDone={() => {}} />)
    expect(screen.getByText(/Connect to a destination database/i)).toBeTruthy()
    expect((screen.getByRole('button', { name: /Run extraction/i }) as HTMLButtonElement).disabled).toBe(true)
  })
})
