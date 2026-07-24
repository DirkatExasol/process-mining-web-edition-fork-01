/** Store tests for the power-user connection-management slice and the auth
 *  `isPower` state. The compute-backend API is mocked; we exercise the Zustand
 *  actions directly. */

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  ApiError: class ApiError extends Error {
    status = 400
    constructor(message: string, status = 400) {
      super(message)
      this.status = status
    }
  },
  api: {
    session: vi.fn(),
    login: vi.fn(),
    logout: vi.fn().mockResolvedValue({ ok: true }),
    listConnections: vi.fn().mockResolvedValue([]),
    connectionStatus: vi.fn().mockResolvedValue({
      isConnected: false,
      isLLMReachable: false,
      activeProfileId: null,
      username: '',
      lastError: null,
    }),
    listManageableConnections: vi.fn(),
    listAssignableUsers: vi.fn(),
    saveManagedConnection: vi.fn(),
    deleteManagedConnection: vi.fn(),
    testManagedConnection: vi.fn(),
  },
}))

import { api, ApiError } from './api'
import { useStore } from './store'

const mockApi = api as unknown as Record<string, ReturnType<typeof vi.fn>>

const conn = {
  id: 'c1',
  name: 'Prod',
  comment: '',
  host: 'db',
  port: 8563,
  username: 'svc',
  schema: 'S',
  useTLS: false,
  certModeRaw: 'verify',
  fingerprint: '',
  minRSAKeySizeBits: 2048,
  hasPassword: true,
  llmURL: '',
  llmModel: '',
  hasLLMKey: false,
  assignments: ['pat'],
  owner: 'pat',
}

beforeEach(() => {
  vi.clearAllMocks()
  useStore.setState({
    authIsPower: false,
    authIsAdmin: false,
    manageableConnections: [],
    assignableUsers: [],
  })
})

describe('refreshManageable', () => {
  it('loads owned connections and assignable users for a power user', async () => {
    useStore.setState({ authIsPower: true })
    mockApi.listManageableConnections.mockResolvedValue([conn])
    mockApi.listAssignableUsers.mockResolvedValue(['pat', 'bob'])

    await useStore.getState().refreshManageable()

    expect(useStore.getState().manageableConnections).toHaveLength(1)
    expect(useStore.getState().assignableUsers).toEqual(['pat', 'bob'])
  })

  it('clears lists and never calls the API for a non-power, non-admin user', async () => {
    useStore.setState({ manageableConnections: [conn], assignableUsers: ['x'] })

    await useStore.getState().refreshManageable()

    expect(mockApi.listManageableConnections).not.toHaveBeenCalled()
    expect(useStore.getState().manageableConnections).toEqual([])
    expect(useStore.getState().assignableUsers).toEqual([])
  })
})

describe('saveManagedConnection', () => {
  it('posts the body, refreshes, and reports success', async () => {
    useStore.setState({ authIsPower: true })
    mockApi.saveManagedConnection.mockResolvedValue(conn)
    mockApi.listManageableConnections.mockResolvedValue([conn])
    mockApi.listAssignableUsers.mockResolvedValue(['pat'])

    const result = await useStore.getState().saveManagedConnection({ name: 'Prod' })

    expect(result).toEqual({ ok: true, error: null })
    expect(mockApi.saveManagedConnection).toHaveBeenCalledWith({ name: 'Prod' })
    expect(mockApi.listManageableConnections).toHaveBeenCalled() // refreshed after save
  })

  it('returns the error message when the API rejects', async () => {
    useStore.setState({ authIsPower: true })
    mockApi.saveManagedConnection.mockRejectedValue(new ApiError('Name is required.', 400))

    const result = await useStore.getState().saveManagedConnection({ name: '' })

    expect(result.ok).toBe(false)
    expect(result.error).toBe('Name is required.')
  })
})

describe('deleteManagedConnection', () => {
  it('deletes then refreshes and returns true', async () => {
    useStore.setState({ authIsPower: true })
    mockApi.deleteManagedConnection.mockResolvedValue({ ok: true })
    mockApi.listManageableConnections.mockResolvedValue([])
    mockApi.listAssignableUsers.mockResolvedValue([])

    const ok = await useStore.getState().deleteManagedConnection('c1')

    expect(ok).toBe(true)
    expect(mockApi.deleteManagedConnection).toHaveBeenCalledWith('c1')
  })

  it('returns false on failure', async () => {
    mockApi.deleteManagedConnection.mockRejectedValue(new ApiError('nope', 403))
    const ok = await useStore.getState().deleteManagedConnection('c1')
    expect(ok).toBe(false)
  })
})

describe('testManagedConnection', () => {
  it('passes the probe result through', async () => {
    mockApi.testManagedConnection.mockResolvedValue({
      dbError: null,
      llmError: null,
      llmModels: ['m1', 'm2'],
    })
    const r = await useStore.getState().testManagedConnection({ host: 'db' })
    expect(r.dbError).toBeNull()
    expect(r.llmModels).toEqual(['m1', 'm2'])
  })

  it('reports a message (not throw) when the probe rejects', async () => {
    mockApi.testManagedConnection.mockRejectedValue(new ApiError('unreachable', 0))
    const r = await useStore.getState().testManagedConnection({ host: 'db' })
    expect(r.dbError).toBe('unreachable')
    expect(r.llmModels).toEqual([])
  })
})

describe('auth isPower', () => {
  it('login sets authIsPower from the response', async () => {
    mockApi.login.mockResolvedValue({
      username: 'pat',
      isAdmin: false,
      isPower: true,
      displayName: '',
      authSource: 'local',
    })
    mockApi.listManageableConnections.mockResolvedValue([])
    mockApi.listAssignableUsers.mockResolvedValue([])

    const err = await useStore.getState().login('pat', 'pw')

    expect(err).toBeNull()
    expect(useStore.getState().authIsPower).toBe(true)
  })

  it('logout clears authIsPower and the managed lists', async () => {
    useStore.setState({
      authIsPower: true,
      manageableConnections: [conn],
      assignableUsers: ['pat'],
    })

    await useStore.getState().logout()

    expect(useStore.getState().authIsPower).toBe(false)
    expect(useStore.getState().manageableConnections).toEqual([])
    expect(useStore.getState().assignableUsers).toEqual([])
  })
})
