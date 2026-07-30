/** Thin typed wrapper over the compute-backend REST API. */

import type {
  AssignedConnection,
  ConnectionStatus,
  ManagedConnection,
  DocumentationResponse,
  FilterSpec,
  GraphResult,
  HappyPath,
  JourneyPath,
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
import type { LoginAppearance } from './loginAppearance'

/** The signed-in user payload returned by password, passkey and MFA sign-in. */
export interface AuthUser {
  username: string
  isAdmin: boolean
  isPower: boolean
  displayName: string | null
  authSource: string | null
  passkeyAllowed: boolean
  mfaAllowed: boolean
  mfaEnabled: boolean
}

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
      passkeyAllowed: boolean
      mfaAllowed: boolean
      mfaEnabled: boolean
    }>('/auth/session'),
  // A password login either signs the user in, asks for a second factor, or —
  // when 2FA is required but not yet set up — asks the user to enrol it first.
  login: (username: string, password: string) =>
    post<
      | AuthUser
      | { mfaRequired: true; username: string }
      | { mfaSetupRequired: true; username: string }
    >('/auth/login', { username, password }),
  // Step 2: submit the TOTP (or recovery) code after a password login that
  // returned mfaRequired.
  verifyMfa: (code: string) => post<AuthUser>('/auth/mfa/verify', { code }),
  // Mandatory enrolment when 2FA is required but not configured (pre-session).
  mfaEnrollBegin: () =>
    post<{ secret: string; otpauthUri: string; qrSvg: string }>('/auth/mfa/enroll/begin'),
  mfaEnrollFinish: (code: string) =>
    post<AuthUser & { recoveryCodes: string[] }>('/auth/mfa/enroll/finish', { code }),
  logout: () => post<{ ok: boolean }>('/auth/logout'),
  // Directory (LDAP) availability for the login panel; configured=false ⇒ show nothing.
  directoryStatus: () =>
    get<{ configured: boolean; available: boolean }>('/auth/directory-status'),
  // Demo-mode / license state for the login panel; demoMode=false ⇒ show nothing.
  licenseStatus: () =>
    get<{
      state: string
      demoMode: boolean
      remainingSeconds: number | null
    }>('/auth/license-status'),
  // Login-page background chosen in the admin Customize tab (pre-auth).
  loginAppearance: () => get<LoginAppearance>('/auth/login-appearance'),

  // ── connections ──────────────────────────────────────────────────────────
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
  // Create the process-mining schema + tables (needs elevated DB privileges).
  provisionManagedSchema: (body: Record<string, unknown>) =>
    post<{ ok: boolean; error: string | null; created: string[] }>(
      '/api/connections/provision-schema',
      body,
    ),
  // Generate the bookstore demo event log into a schema (needs elevated DB privileges).
  generateDemoContent: (body: Record<string, unknown>) =>
    post<{
      ok: boolean
      error: string | null
      journeys: number
      project?: string
      message?: string
    }>('/api/connections/generate-demo', body),
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
  // Append a comment to a note's thread and/or toggle resolved (any viewer);
  // importance/isShared are applied server-side only for the note's author.
  updateNote: (
    projectId: string,
    noteId: string,
    body: {
      title?: string
      comment?: string
      resolved?: boolean
      importance?: string
      isShared?: boolean
    },
  ) =>
    post<ProcessNote>(`/api/projects/${enc(projectId)}/notes/${enc(noteId)}`, body),
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
}
