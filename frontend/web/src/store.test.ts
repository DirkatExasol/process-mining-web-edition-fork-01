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
    provisionManagedSchema: vi.fn(),
    generateDemoContent: vi.fn(),
    bootstrap: vi.fn(),
    graph: vi.fn(),
    listNotes: vi.fn().mockResolvedValue([]),
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

describe('provisionSchema', () => {
  it('passes the provisioner result through', async () => {
    mockApi.provisionManagedSchema.mockResolvedValue({
      ok: true,
      error: null,
      created: ['schema PM', 'PROJECTS', 'NOTES'],
    })
    const r = await useStore.getState().provisionSchema({ schema: 'PM' })
    expect(r.ok).toBe(true)
    expect(r.created).toContain('PROJECTS')
  })

  it('maps an ApiError to a failure result (never throws)', async () => {
    mockApi.provisionManagedSchema.mockRejectedValue(new ApiError('CREATE SCHEMA denied', 400))
    const r = await useStore.getState().provisionSchema({ schema: 'PM' })
    expect(r.ok).toBe(false)
    expect(r.error).toBe('CREATE SCHEMA denied')
    expect(r.created).toEqual([])
  })
})

describe('generateDemo', () => {
  it('passes the generator result through', async () => {
    mockApi.generateDemoContent.mockResolvedValue({
      ok: true,
      error: null,
      journeys: 500,
      project: 'Online Bookstore',
      message: 'Created 500 journeys',
    })
    const r = await useStore.getState().generateDemo({ schema: 'PM', journeys: 500 })
    expect(r.ok).toBe(true)
    expect(r.journeys).toBe(500)
  })

  it('maps an ApiError to a failure result (never throws)', async () => {
    mockApi.generateDemoContent.mockRejectedValue(new ApiError('INSERT denied', 400))
    const r = await useStore.getState().generateDemo({ schema: 'PM', journeys: 10 })
    expect(r.ok).toBe(false)
    expect(r.error).toBe('INSERT denied')
    expect(r.journeys).toBe(0)
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

describe('selectProject sampling methods', () => {
  const bootstrap = {
    project: { projectId: 'BOOKSTORE', title: 'Online Bookstore', description: '' },
    allSteps: [],
    allStepInfos: {},
    meta1Title: null,
    meta2Title: null,
    meta3Title: null,
    meta1Values: [],
    meta2Values: [],
    meta3Values: [],
    totalJourneyCount: 100,
    minDate: null,
    maxDate: null,
    initialFromDate: null,
    initialToDate: null,
    stepCountMin: 1,
    stepCountMax: 10,
    journeyTimeBoundsMin: 0,
    journeyTimeBoundsMax: 3600,
    scoreBoundsMin: 0,
    scoreBoundsMax: 10,
    sampleCounts: { SAMPLE_1: 500 },
    sampleMethods: { SAMPLE_1: 'temporal' },
  }
  const graph = {
    processGraph: { steps: {}, transitions: [] },
    journeyCount: 100,
    durations: { minSecs: null, avgSecs: null, stdDevSecs: null, maxSecs: null },
    processGoodness: null,
    variants: [],
  }

  it('populates sampleMethods from the bootstrap so the badges survive a reload', async () => {
    useStore.setState({ sampleMethods: {}, sampleCounts: {} })
    mockApi.bootstrap.mockResolvedValue(bootstrap)
    mockApi.graph.mockResolvedValue(graph)

    await useStore.getState().selectProject(bootstrap.project)

    expect(useStore.getState().sampleCounts).toEqual({ SAMPLE_1: 500 })
    expect(useStore.getState().sampleMethods).toEqual({ SAMPLE_1: 'temporal' })
  })
})

describe('transitions mode indicator', () => {
  const base = {
    processGraph: {
      steps: {},
      transitions: [
        { fromStep: 'A', toStep: 'B', occurrences: 1, avgSecs: 1, minSecs: null, maxSecs: null, stdDevSecs: null },
      ],
    },
    journeyCount: 5,
    durations: { minSecs: null, avgSecs: null, stdDevSecs: null, maxSecs: null },
    processGoodness: null,
    queryMs: 42.5,
    variants: [],
  }

  it('reloadGraph records the effective mode and query time from the backend', async () => {
    mockApi.graph.mockResolvedValue({ ...base, transitionsMode: 'materialized' })
    useStore.setState({
      selectedProject: { projectId: 'P', title: 'P', description: '' },
      transitionsMode: null,
      queryMs: null,
    })
    await useStore.getState().reloadGraph()
    expect(useStore.getState().transitionsMode).toBe('materialized')
    expect(useStore.getState().queryMs).toBe(42.5)
  })

  it('surfaces the fallback mode (enabled but TRANSITIONS_RAW not built)', async () => {
    mockApi.graph.mockResolvedValue({ ...base, transitionsMode: 'fallback' })
    useStore.setState({ selectedProject: { projectId: 'P', title: 'P', description: '' } })
    await useStore.getState().reloadGraph()
    expect(useStore.getState().transitionsMode).toBe('fallback')
  })
})
