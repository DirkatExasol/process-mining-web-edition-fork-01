/** Thin typed wrapper over the compute-backend REST API. */

import type {
  AssignedConnection,
  ConnectionProjectsResult,
  ConnectionProjectDeleteResult,
  ConnectionStatus,
  ManagedConnection,
  DocumentationResponse,
  FilterSpec,
  GraphResult,
  HappyPath,
  JourneyEvent,
  JourneyPath,
  ProcessGraph,
  ProcessNote,
  Project,
  ProjectBootstrap,
  ExtractionField,
  ExtractorInfo,
  IntegrationFile,
  IntegrationStatus,
  RecordDetection,
  SampleSet,
  Source,
  SourceCheckpoint,
  SourceInput,
  SourceType,
  SourceTypeInput,
  StructureDetection,
  SamplingMethod,
  SimulationConfig,
  SimulationResult,
  StatisticsResponse,
  StepInfo,
  TransitionMetric,
} from './types'
import type { LoginAppearance } from './loginAppearance'
import type { ActionRunResult, ActionSpec, SavedAction } from './actions/types'
import type { AggregateLink, CreateAggregateBody, CreateAggregateResult } from './aggregate/types'

/** The signed-in user payload returned by password, passkey and MFA sign-in. */
export interface AuthUser {
  username: string
  isAdmin: boolean
  isPower: boolean
  isDeveloper: boolean
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
      isDeveloper: boolean
      displayName: string | null
      authSource: string | null
      requireLogin: boolean
      idleTimeoutMins: number
      actionsEnabled: boolean
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
  // Projects stored in a manageable connection's schema (journey/event counts + delete).
  listConnectionProjects: (id: string) =>
    get<ConnectionProjectsResult>(`/api/connections/${enc(id)}/projects`),
  deleteConnectionProject: (id: string, projectId: string) =>
    post<ConnectionProjectDeleteResult>(`/api/connections/${enc(id)}/projects/delete`, {
      projectId,
    }),
  disconnect: () => post<ConnectionStatus>('/api/disconnect'),
  connectionStatus: () => get<ConnectionStatus>('/api/connection/status'),

  // ── integration abstraction layer ────────────────────────────────────────
  integrationStatus: () => get<IntegrationStatus>('/api/integration/status'),
  integrationExtractors: () => get<ExtractorInfo[]>('/api/integration/extractors'),
  listSourceTypes: () => get<SourceType[]>('/api/integration/source-types'),
  createSourceType: (body: SourceTypeInput) =>
    post<SourceType>('/api/integration/source-types', body),
  updateSourceType: (id: string, body: SourceTypeInput) =>
    put<SourceType>(`/api/integration/source-types/${enc(id)}`, body),
  deleteSourceType: (id: string) =>
    del<{ ok: boolean }>(`/api/integration/source-types/${enc(id)}`),
  parseDetect: (sample: string) =>
    post<{ fields: ExtractionField[] }>('/api/integration/parse/detect', { sample }),
  parseSegment: (sample: string, start: number, end: number) =>
    post<{ regex: string; value: string }>('/api/integration/parse/segment', { sample, start, end }),
  parseTimestamp: (value: string) =>
    post<{ format: string; normalized: string }>('/api/integration/parse/timestamp', { value }),
  listSources: () => get<Source[]>('/api/integration/sources'),
  createSource: (body: SourceInput) => post<Source>('/api/integration/sources', body),
  updateSource: (id: string, body: SourceInput) =>
    put<Source>(`/api/integration/sources/${enc(id)}`, body),
  deleteSource: (id: string) => del<{ ok: boolean }>(`/api/integration/sources/${enc(id)}`),
  previewSource: (path: string, limit: number) =>
    post<{ lines: string[]; truncated: boolean }>('/api/integration/sources/preview', { path, limit }),
  // Source-type wizard file picker: list the sandbox files, and detect a file's record
  // delimiter (or split on an explicit one), returning the first N records.
  listIntegrationFiles: () => get<IntegrationFile[]>('/api/integration/files'),
  detectRecords: (path: string, delimiter = '', limit = 5) =>
    post<RecordDetection>('/api/integration/files/records', { path, delimiter, limit }),
  // Detect a file's data format (text / JSON / XML) and return rendered sample records
  // plus suggested fields with their path selectors.
  detectStructure: (path: string, limit = 5) =>
    post<StructureDetection>('/api/integration/files/structure', { path, limit }),
  // Projects already in a destination connection's schema (gated on assignment, unlike
  // the manager-only /api/connections/{id}/projects).
  destinationProjects: (connectionId: string) =>
    get<ConnectionProjectsResult>(`/api/integration/connections/${enc(connectionId)}/projects`),
  runSource: (id: string, projectId: string, connectionId: string, delta = true) =>
    post<{ records: number; detail: string }>(`/api/integration/sources/${enc(id)}/run`, {
      projectId,
      connectionId,
      delta,
    }),
  sourceCheckpoint: (id: string) =>
    get<SourceCheckpoint>(`/api/integration/sources/${enc(id)}/checkpoint`),
  resetSourceCheckpoint: (id: string) =>
    post<{ ok: boolean }>(`/api/integration/sources/${enc(id)}/checkpoint/reset`),

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
      // The raw ordered trace (loops unrolled) for the sequential swimlane view.
      sequence: JourneyEvent[]
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
      notes?: ProcessNote[]
      connectionId?: string
      sankeySvg?: string
      sankeyCaption?: string
      preparedFor?: string
    },
  ) =>
    post<DocumentationResponse>(`/api/projects/${enc(projectId)}/documentation`, payload),

  // The report analysis prompt for a (connection, project). Power/developer/admin only —
  // the same mapping the admin Reporting tab manages.
  reportPrompt: (projectId: string, connectionId: string) =>
    get<{ prompt: string }>(
      `/api/projects/${enc(projectId)}/report-prompt?connectionId=${enc(connectionId)}`,
    ),
  setReportPrompt: (projectId: string, connectionId: string, prompt: string) =>
    put<{ prompt: string }>(`/api/projects/${enc(projectId)}/report-prompt`, {
      connectionId,
      prompt,
    }),

  // ── actions (saved node-menu actions, per connection + project) ───────────
  listActions: (projectId: string, connectionId: string) =>
    get<{ actions: SavedAction[] }>(
      `/api/projects/${enc(projectId)}/actions?connectionId=${enc(connectionId)}`,
    ),
  createAction: (
    projectId: string,
    body: { connectionId: string; name: string; script: string; spec: ActionSpec; enabled: boolean },
  ) => post<SavedAction>(`/api/projects/${enc(projectId)}/actions`, body),
  updateAction: (
    projectId: string,
    actionId: string,
    body: { connectionId: string; name: string; script: string; spec: ActionSpec; enabled: boolean },
  ) => put<SavedAction>(`/api/projects/${enc(projectId)}/actions/${enc(actionId)}`, body),
  deleteAction: (projectId: string, actionId: string, connectionId: string) =>
    del<{ ok: boolean }>(
      `/api/projects/${enc(projectId)}/actions/${enc(actionId)}?connectionId=${enc(connectionId)}`,
    ),
  runAction: (
    projectId: string,
    actionId: string,
    body: { connectionId: string; filter: FilterSpec; contextNode: string; resolvedSteps: string[] },
  ) => post<ActionRunResult>(`/api/projects/${enc(projectId)}/actions/${enc(actionId)}/run`, body),
  previewRunAction: (
    projectId: string,
    body: {
      connectionId: string
      spec: ActionSpec
      filter: FilterSpec
      contextNode: string
      resolvedSteps: string[]
    },
  ) => post<ActionRunResult>(`/api/projects/${enc(projectId)}/actions/preview-run`, body),
  previewActionSql: (
    projectId: string,
    body: {
      connectionId: string
      spec: ActionSpec
      filter: FilterSpec
      contextNode: string
      resolvedSteps: string[]
    },
  ) => post<{ sql: string }>(`/api/projects/${enc(projectId)}/actions/preview-sql`, body),

  // ── aggregates (collapse connected steps into a Σ super-step) ─────────────
  createAggregate: (projectId: string, body: CreateAggregateBody) =>
    post<CreateAggregateResult>(`/api/projects/${enc(projectId)}/aggregate`, body),
  listAggregates: (projectId: string, connectionId: string) =>
    get<{ aggregates: AggregateLink[] }>(
      `/api/projects/${enc(projectId)}/aggregates?connectionId=${enc(connectionId)}`,
    ),

  // ── settings ─────────────────────────────────────────────────────────────
  settings: () => get<Record<string, unknown>>('/api/settings'),
  patchSettings: (values: Record<string, unknown>) =>
    patch<{ ok: boolean }>('/api/settings', { values }),
}
