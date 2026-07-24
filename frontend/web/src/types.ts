/** TypeScript mirrors of the backend pydantic models (which mirror Models.swift). */

export const INT_MAX = 9223372036854775807
export const INT_MIN = -9223372036854775808

export interface DatabaseServer {
  id: string
  name: string
  comment: string
  host: string
  port: number
  username: string
  schema: string
  useTLS: boolean
  certModeRaw: string
  fingerprint: string
  minRSAKeySizeBits: number
}

export interface LLMServer {
  id: string
  name: string
  comment: string
  serverURL: string
  apiKey: string
  model: string
}

export interface ConnectionProfile {
  id: string
  name: string
  comment: string
  databaseServerId: string | null
  llmServerId: string | null
}

export interface ConnectionStatus {
  isConnected: boolean
  isLLMReachable: boolean
  activeProfileId: string | null
  username: string
  lastError: string | null
}

/** A connection assigned to the signed-in user by an administrator. Read-only:
 * the definition (and all secrets) lives in the admin interface. Mirrors the
 * backend's `Connection.user_public()`. */
export interface AssignedConnection {
  id: string
  name: string
  comment: string
  host: string
  port: number
  schema: string
  hasLLM: boolean
  llmURL: string | null
}

/** A connection a *power* user owns and may edit from the app (admin_public shape;
 * secrets are represented by the hasPassword / hasLLMKey flags, never values). */
export interface ManagedConnection {
  id: string
  name: string
  comment: string
  host: string
  port: number
  username: string
  schema: string
  useTLS: boolean
  certModeRaw: string
  fingerprint: string
  minRSAKeySizeBits: number
  hasPassword: boolean
  llmURL: string
  llmModel: string
  hasLLMKey: boolean
  assignments: string[]
  owner: string
}

export interface Project {
  projectId: string
  title: string
  description: string
}

export interface StepInfo {
  step: string
  description: string
  bgColor: string
  fgColor: string
  score: number | null
  shape: string
  endOfProcess: boolean
  belongsTo: string | null
  eventTime: string | null
}

export interface ProcessTransition {
  fromStep: string
  toStep: string
  occurrences: number
  avgSecs: number | null
  minSecs: number | null
  maxSecs: number | null
  stdDevSecs: number | null
}

export interface ProcessGraph {
  steps: Record<string, StepInfo>
  transitions: ProcessTransition[]
}

export const EMPTY_GRAPH: ProcessGraph = { steps: {}, transitions: [] }

export interface JourneyPath {
  path: string
  journeyCount: number
  stepCount: number
  totalScore: number
}

export interface DurationBucket {
  label: string
  count: number
}

export interface JourneyTimePoint {
  date: string
  count: number
}

export interface DurationStats {
  minSecs: number | null
  avgSecs: number | null
  stdDevSecs: number | null
  maxSecs: number | null
}

export const TRANSITION_METRICS = [
  'Count',
  'Avg Time',
  'Min Time',
  'Max Time',
  'Std Dev',
] as const
export type TransitionMetric = (typeof TRANSITION_METRICS)[number]

export function isTimeBased(metric: TransitionMetric): boolean {
  return metric !== 'Count'
}

export function metricValue(
  t: ProcessTransition,
  metric: TransitionMetric,
): number | null {
  switch (metric) {
    case 'Count':
      return t.occurrences
    case 'Avg Time':
      return t.avgSecs
    case 'Min Time':
      return t.minSecs
    case 'Max Time':
      return t.maxSecs
    case 'Std Dev':
      return t.stdDevSecs
  }
}

export function maxMetricValue(
  graph: ProcessGraph,
  metric: TransitionMetric,
): number {
  let max = -Infinity
  for (const t of graph.transitions) {
    const v = metricValue(t, metric)
    if (v != null && v > max) max = v
  }
  return max === -Infinity ? 1 : max
}

export const SAMPLE_SETS = ['ORIGINAL', 'SAMPLE_1', 'SAMPLE_2', 'SAMPLE_3'] as const
export type SampleSet = (typeof SAMPLE_SETS)[number]

export function sampleLabel(set: SampleSet): string {
  return {
    ORIGINAL: 'Original Data',
    SAMPLE_1: 'Sample Set 1',
    SAMPLE_2: 'Sample Set 2',
    SAMPLE_3: 'Sample Set 3',
  }[set]
}

export function sampleShortLabel(set: SampleSet): string {
  return {
    ORIGINAL: 'Original',
    SAMPLE_1: 'Sample 1',
    SAMPLE_2: 'Sample 2',
    SAMPLE_3: 'Sample 3',
  }[set]
}

export type SamplingMethod = 'random' | 'temporal' | 'pathDiverse'

export const SAMPLING_METHODS: {
  id: SamplingMethod
  label: string
  icon: string
  description: string
}[] = [
  {
    id: 'random',
    label: 'Random',
    icon: '🔀',
    description: 'Uniform random selection',
  },
  {
    id: 'temporal',
    label: 'Temporal Stratified',
    icon: '📅',
    description: 'Proportional across time periods',
  },
  {
    id: 'pathDiverse',
    label: 'Path Diversity',
    icon: '🌿',
    description: 'Coverage across journey variants',
  },
]

export const DETAIL_VIEW_MODES = [
  'A-Chart',
  'B-Chart',
  'A/B Comparison',
  'Individual Journey',
  'AI supported Documentation',
  'Statistics',
  'Conformance Check',
  'Happy Path',
  'Notes',
  'Simulation',
] as const
export type DetailViewMode = (typeof DETAIL_VIEW_MODES)[number]

export const VIEW_MODE_ICONS: Record<DetailViewMode, string> = {
  'A-Chart': '📈',
  'B-Chart': '📉',
  'A/B Comparison': '⇄',
  'Individual Journey': '🧍',
  'AI supported Documentation': '🧠',
  Statistics: '📊',
  'Conformance Check': '🛡️',
  'Happy Path': '🪧',
  Notes: '🗒️',
  Simulation: '🎲',
}

export type SliderMode = 'Range' | 'Day'
export type GraphStartMode = 'expanded' | 'collapsed' | 'persisted'

export interface FilterSpec {
  fromDate: string | null
  toDate: string | null
  includedSteps: string[]
  excludedSteps: string[]
  meta1: string
  meta2: string
  meta3: string
  minSteps: number
  maxSteps: number
  minJourneyTime: number
  maxJourneyTime: number
  minScore: number
  maxScore: number
  sampleSet: SampleSet
}

export interface FilterGroup {
  id: string
  name: string
  fromDate: string
  toDate: string
  includedSteps: string[]
  excludedSteps: string[]
  meta1: string
  meta2: string
  meta3: string
  minSteps: number
  maxSteps: number
  minJourneyTime: number
  maxJourneyTime: number
  minScore: number
  maxScore: number
}

export interface HappyPathBranch {
  id: string
  label: string
  steps: string[]
}

export interface HappyPath {
  id: string
  name: string
  steps: string[]
  branches: HappyPathBranch[]
}

export interface FilterSnapshot {
  fromDate: string
  toDate: string
  includedSteps: string[]
  excludedSteps: string[]
  meta1: string
  meta2: string
  meta3: string
  minSteps: number
  maxSteps: number
  minJourneyTime: number
  maxJourneyTime: number
  minScore: number
  maxScore: number
}

export interface NoteTarget {
  type: 'node' | 'edge'
  value?: string | null
  from?: string | null
  to?: string | null
}

export interface ProcessNote {
  id: string
  text: string
  createdAt: string
  editedAt: string | null
  target: NoteTarget
  filterSnapshot: FilterSnapshot
  username: string
  lastEditedBy: string
  isShared: boolean
}

export function noteTargetKey(target: NoteTarget): string {
  return target.type === 'edge'
    ? `edge:${target.from}->${target.to}`
    : `node:${target.value}`
}

export function noteTargetLabel(target: NoteTarget): string {
  return target.type === 'edge'
    ? `${target.from} → ${target.to}`
    : (target.value ?? '')
}

export interface GraphResult {
  processGraph: ProcessGraph
  journeyCount: number | null
  durations: DurationStats
  processGoodness: number | null
  variants: JourneyPath[]
}

export interface ProjectBootstrap {
  project: Project
  allSteps: string[]
  allStepInfos: Record<string, StepInfo>
  meta1Title: string | null
  meta2Title: string | null
  meta3Title: string | null
  meta1Values: string[]
  meta2Values: string[]
  meta3Values: string[]
  totalJourneyCount: number | null
  minDate: string | null
  maxDate: string | null
  initialFromDate: string | null
  initialToDate: string | null
  stepCountMin: number
  stepCountMax: number
  journeyTimeBoundsMin: number
  journeyTimeBoundsMax: number
  scoreBoundsMin: number
  scoreBoundsMax: number
  sampleCounts: Record<string, number>
}

export interface StatisticsResponse {
  paths: JourneyPath[]
  durationBuckets: DurationBucket[]
  timeSeries: JourneyTimePoint[]
  timeGranularity: 'day' | 'week' | 'month'
  processGraph: ProcessGraph
  journeyCount: number | null
  totalJourneyCount: number | null
  durations: DurationStats
  isTruncated: boolean
}

export interface SimulationConfig {
  journeyCount: number
  startDate: string
  avgInterArrivalHours: number
  excludedSteps: string[]
  requiredSteps: string[]
  maxStepsPerJourney: number
}

export interface SimulatedEvent {
  journeyId: string
  step: string
  timestamp: string
}

export interface SimulationVariant {
  path: string
  count: number
  percentage: number
  avgCycleTimeSecs: number
}

export interface SimulationResult {
  runId: string
  events: SimulatedEvent[]
  variants: SimulationVariant[]
  cycleTimes: number[]
  simProcessGraph: ProcessGraph
  totalJourneys: number
  avgCycleTimeSecs: number
  minCycleTimeSecs: number
  maxCycleTimeSecs: number
  stdDevCycleTimeSecs: number
}

export type SimSlot = 'Sim-A' | 'Sim-B'

export type ABDataSource =
  | { kind: 'sampleSet'; sampleSet: SampleSet }
  | { kind: 'simulation'; slot: SimSlot }

export function abDataSourceLabel(source: ABDataSource): string {
  return source.kind === 'sampleSet'
    ? sampleShortLabel(source.sampleSet)
    : source.slot
}

export interface DocumentationResponse {
  result: string | null
  error: string | null
  prompt: string
  model: string | null
  generatedAt: string
  journeyPathsSummary: string
  conformanceSummary: string
  happyPathSummary: string
}

export const KPI_DEFAULT_ORDER =
  'totalJourneys,filteredJourneys,shortestJourney,avgJourney,stdDev,longestJourney,graphValue,processGoodness,processSimilarity,activeSample'

export const KPI_META: Record<string, { label: string; icon: string }> = {
  totalJourneys: { label: 'Total Journeys', icon: '👥' },
  filteredJourneys: { label: 'Filtered Journeys', icon: '⛃' },
  shortestJourney: { label: 'Shortest Journey', icon: '🐇' },
  avgJourney: { label: 'Avg Journey', icon: '⏱️' },
  stdDev: { label: 'Std Dev', icon: '〰️' },
  longestJourney: { label: 'Longest Journey', icon: '🐢' },
  graphValue: { label: 'Graph Value', icon: 'ƒ' },
  processGoodness: { label: 'Process Goodness', icon: '◔' },
  processSimilarity: { label: 'Process Similarity', icon: '⇄' },
  activeSample: { label: 'Active Sample', icon: '▤' },
}
