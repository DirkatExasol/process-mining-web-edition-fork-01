/** Thin typed wrapper over the compute-backend REST API. */

import type {
  AssignedConnection,
  ConnectionStatus,
  DatabaseServer,
  ManagedConnection,
  DocumentationResponse,
  FilterSpec,
  GraphResult,
  HappyPath,
  JourneyPath,
  LLMServer,
  ProcessGraph,
  ProcessNote,
  Project,
  ProjectBootstrap,
  SampleSet,
  SamplingMethod,
  SimulationConfig,
  SimulationResult,
  StatisticsResponse,
  StepInfo,
  TransitionMetric,
} from './types'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError('The server is not reachable.', 0)
  }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* non-JSON error body — keep the status text */
    }
    throw new ApiError(detail, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) })
const put = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) })
const patch = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) })
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' })

const enc = encodeURIComponent

export const api = {
  // ── authentication ─────────────────────────────────────────────────────────
  session: () =>
    get<{
      authenticated: boolean
      username: string | null
      isAdmin: boolean
      isPower: boolean
      displayName: string | null
      authSource: string | null
      requireLogin: boolean
      idleTimeoutMins: number
    }>('/auth/session'),
  login: (username: string, password: string) =>
    post<{
      username: string
      isAdmin: boolean
      isPower: boolean
      displayName: string
      authSource: string
    }>('/auth/login', { username, password }),
  logout: () => post<{ ok: boolean }>('/auth/logout'),
  // Directory (LDAP) availability for the login panel; configured=false ⇒ show nothing.
  directoryStatus: () =>
    get<{ configured: boolean; available: boolean }>('/auth/directory-status'),

  // ── connections ──────────────────────────────────────────────────────────
  listDbServers: () => get<DatabaseServer[]>('/api/servers/db'),
  saveDbServer: (server: DatabaseServer, password?: string) =>
    post<DatabaseServer>('/api/servers/db', { server, password }),
  dbServerPassword: (id: string) =>
    get<{ password: string }>(`/api/servers/db/${enc(id)}/password`),
  deleteDbServer: (id: string) => del<void>(`/api/servers/db/${enc(id)}`),
  testDbServer: (server: DatabaseServer, password?: string) =>
    post<{ error: string | null }>('/api/servers/db/test', { server, password }),

  listLlmServers: () => get<LLMServer[]>('/api/servers/llm'),
  saveLlmServer: (server: LLMServer) => post<LLMServer>('/api/servers/llm', server),
  deleteLlmServer: (id: string) => del<void>(`/api/servers/llm/${enc(id)}`),
  testLlmServer: (server: LLMServer) =>
    post<{ error: string | null; models: string[] }>('/api/servers/llm/test', {
      server,
    }),

  // Admin-defined connections assigned to the signed-in user.
  listConnections: () => get<AssignedConnection[]>('/api/connections'),
  connectConnection: (id: string) =>
    post<ConnectionStatus>(`/api/connections/${enc(id)}/connect`),

  // Power-user connection management (create / edit / assign, from the app).
  listManageableConnections: () =>
    get<ManagedConnection[]>('/api/connections/manageable'),
  listAssignableUsers: () => get<string[]>('/api/assignable-users'),
  saveManagedConnection: (body: Record<string, unknown>) =>
    post<ManagedConnection>('/api/connections', body),
  deleteManagedConnection: (id: string) =>
    del<{ ok: boolean }>(`/api/connections/${enc(id)}`),
  testManagedConnection: (body: Record<string, unknown>) =>
    post<{ dbError: string | null; llmError: string | null; llmModels: string[] }>(
      '/api/connections/test',
      body,
    ),
  disconnect: () => post<ConnectionStatus>('/api/disconnect'),
  connectionStatus: () => get<ConnectionStatus>('/api/connection/status'),

  // ── project data ─────────────────────────────────────────────────────────
  listProjects: () => get<Project[]>('/api/projects'),
  bootstrap: (projectId: string, sampleSet: SampleSet) =>
    get<ProjectBootstrap>(
      `/api/projects/${enc(projectId)}/bootstrap?sampleSet=${sampleSet}`,
    ),
  graph: (
    projectId: string,
    filter: FilterSpec,
    options: {
      totalJourneyCount?: number | null
      includeGoodness?: boolean
      includeVariants?: boolean
      variantLimit?: number
    } = {},
  ) =>
    post<GraphResult>(`/api/projects/${enc(projectId)}/graph`, {
      filter,
      totalJourneyCount: options.totalJourneyCount ?? null,
      includeGoodness: options.includeGoodness ?? true,
      includeVariants: options.includeVariants ?? false,
      variantLimit: options.variantLimit ?? 500,
    }),
  journeyPaths: (projectId: string, filter: FilterSpec, variantLimit = 500) =>
    post<JourneyPath[]>(`/api/projects/${enc(projectId)}/journey-paths`, {
      filter,
      variantLimit,
    }),
  statistics: (
    projectId: string,
    filter: FilterSpec,
    routeLimit: number,
    totalJourneyCount: number | null,
  ) =>
    post<StatisticsResponse>(`/api/projects/${enc(projectId)}/statistics`, {
      filter,
      routeLimit,
      totalJourneyCount,
    }),
  similarity: (payload: {
    variantsA: JourneyPath[]
    variantsB: JourneyPath[]
    graphA: ProcessGraph
    graphB: ProcessGraph
  }) => post<{ score: number | null }>('/api/similarity', payload),
  eventIds: (projectId: string, prefix: string, sampleSet: SampleSet) =>
    get<string[]>(
      `/api/projects/${enc(projectId)}/event-ids?prefix=${enc(prefix)}&sampleSet=${sampleSet}`,
    ),
  journey: (projectId: string, eventId: string, sampleSet: SampleSet) =>
    get<{
      queriedEventId: string
      processGraph: ProcessGraph
      journeyCount: number
      startDate: string | null
      endDate: string | null
      meta1: string | null
      meta2: string | null
      meta3: string | null
    }>(
      `/api/projects/${enc(projectId)}/journey?eventId=${enc(eventId)}&sampleSet=${sampleSet}`,
    ),
  updateStep: (
    projectId: string,
    step: string,
    payload: {
      bgColor: string
      fgColor: string
      score: number | null
      shape: string
      belongsTo: string | null
      description: string | null
    },
  ) =>
    put<{
      scoreBoundsMin: number
      scoreBoundsMax: number
      allStepInfos: Record<string, StepInfo>
    }>(`/api/projects/${enc(projectId)}/steps/${enc(step)}`, payload),
  nearestDay: (projectId: string, day: string, sampleSet: SampleSet) =>
    post<{ date: string | null }>(`/api/projects/${enc(projectId)}/nearest-day`, {
      day,
      sampleSet,
    }),

  // ── notes ────────────────────────────────────────────────────────────────
  listNotes: (projectId: string) =>
    get<ProcessNote[]>(`/api/projects/${enc(projectId)}/notes`),
  saveNote: (projectId: string, note: ProcessNote) =>
    put<ProcessNote>(`/api/projects/${enc(projectId)}/notes`, note),
  deleteNote: (projectId: string, noteId: string) =>
    del<void>(`/api/projects/${enc(projectId)}/notes/${enc(noteId)}`),

  // ── sampling ─────────────────────────────────────────────────────────────
  sampleCounts: (projectId: string) =>
    get<{ counts: Record<string, number>; methods: Record<string, SamplingMethod> }>(
      `/api/projects/${enc(projectId)}/samples`,
    ),
  createSample: (
    projectId: string,
    sampleSet: SampleSet,
    count: number,
    method: SamplingMethod,
  ) =>
    post<{ counts: Record<string, number>; created: number }>(
      `/api/projects/${enc(projectId)}/samples`,
      { sampleSet, count, method },
    ),
  deleteSample: (projectId: string, sampleSet: SampleSet) =>
    del<{ counts: Record<string, number> }>(
      `/api/projects/${enc(projectId)}/samples/${sampleSet}`,
    ),

  // ── simulation & conformance ─────────────────────────────────────────────
  simulate: (
    graph: ProcessGraph,
    stepInfos: Record<string, StepInfo>,
    config: SimulationConfig,
  ) => post<SimulationResult>('/api/simulate', { graph, stepInfos, config }),
  conformance: (projectId: string, filter: FilterSpec, happyPaths: HappyPath[]) =>
    post<Record<string, number | null>>(`/api/projects/${enc(projectId)}/conformance`, {
      filter,
      happyPaths,
    }),

  // ── AI documentation ─────────────────────────────────────────────────────
  documentation: (
    projectId: string,
    payload: {
      projectTitle: string
      filter: FilterSpec
      graph: ProcessGraph
      promptTemplate: string
      targetNorms: Record<string, Record<string, number>>
      targetMetric: TransitionMetric
      happyPaths: HappyPath[]
    },
  ) =>
    post<DocumentationResponse>(`/api/projects/${enc(projectId)}/documentation`, payload),

  // ── settings ─────────────────────────────────────────────────────────────
  settings: () => get<Record<string, unknown>>('/api/settings'),
  patchSettings: (values: Record<string, unknown>) =>
    patch<{ ok: boolean }>('/api/settings', { values }),

  // ── backup ───────────────────────────────────────────────────────────────
  exportBackup: async (payload: {
    includePasswords: boolean
    includeUsername: boolean
    includeLlmApiKey: boolean
    password: string
  }) => {
    const response = await fetch('/api/backup/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw new ApiError('Export failed.', response.status)
    return response.blob()
  },
  inspectBackup: (content: string, password: string) =>
    post<Record<string, unknown>>('/api/backup/inspect', { content, password }),
  restoreBackup: (
    content: string,
    password: string,
    options: Record<string, boolean>,
  ) => post<{ ok: boolean }>('/api/backup/restore', { content, password, options }),
}
