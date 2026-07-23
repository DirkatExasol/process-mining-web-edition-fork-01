/**
 * The `@AppStorage` / UserDefaults replacement.
 *
 * All preferences live in the backend's SQLite kv store so they survive a
 * browser change and so backups stay compatible with the macOS app. Reads come
 * from an in-memory cache hydrated once at startup; writes update the cache
 * immediately (optimistic) and are flushed to the backend, coalesced.
 */

import { useCallback, useSyncExternalStore } from 'react'
import { api } from './api'
import { KPI_DEFAULT_ORDER, type GraphStartMode, type SliderMode } from './types'
import { defaultSchemaFor, type EdgeColorSchema } from './graph/colors'

export const SETTING_DEFAULTS: Record<string, unknown> = {
  'app.theme': 'system',
  'slider.mode': 'Range' satisfies SliderMode,
  'graph.startMode': 'expanded' satisfies GraphStartMode,
  'graph.optimisedLayout': true,
  'graph.edge.colorizeByWeight': true,
  'graph.edge.colorSchema.Count': defaultSchemaFor('Count'),
  'graph.edge.colorSchema.Avg Time': defaultSchemaFor('Avg Time'),
  'graph.edge.colorSchema.Min Time': defaultSchemaFor('Min Time'),
  'graph.edge.colorSchema.Max Time': defaultSchemaFor('Max Time'),
  'graph.edge.colorSchema.Std Dev': defaultSchemaFor('Std Dev'),
  'processmap.showGrouping': true,
  'processmap.showNodeDescriptions': true,
  'processmap.kpiExpanded': true,
  'abComparison.valveOpen': true,
  'security.requireAuthentication': false,
  'legal.accepted': false,
  'sidebar.filtersDateExpanded': true,
  'sidebar.filtersMetaExpanded': false,
  'sidebar.filtersIncludeExpanded': false,
  'sidebar.filtersExcludeExpanded': false,
  'sidebar.filtersStepsExpanded': false,
  'sidebar.filtersJourneyTimeExpanded': false,
  'sidebar.filtersScoreExpanded': false,
  'sidebar.configStepsExpanded': true,
  'sidebar.configKpisExpanded': true,
  'achart.controlsExpanded': true,
  'bchart.controlsExpanded': true,
  'compliance.controlsExpanded': true,
  'compliance.kpiExpanded': true,
  'compliance.normIsMinimum': false,
  'abpanel.a.controlsExpanded': true,
  'abpanel.b.controlsExpanded': true,
  'abpanel.a.kpiExpanded': true,
  'abpanel.b.kpiExpanded': true,
  'kpi.order': KPI_DEFAULT_ORDER,
  'kpi.show.totalJourneys': true,
  'kpi.show.filteredJourneys': true,
  'kpi.show.shortestJourney': true,
  'kpi.show.avgJourney': true,
  'kpi.show.stdDev': true,
  'kpi.show.longestJourney': true,
  'kpi.show.graphValue': true,
  'kpi.show.processGoodness': true,
  'kpi.show.processSimilarity': true,
  'kpi.show.activeSample': true,
  'sampling.activeSampleSetA': 'ORIGINAL',
  'sampling.activeSampleSetB': 'ORIGINAL',
}

let cache: Record<string, unknown> = { ...SETTING_DEFAULTS }
let hydrated = false
const listeners = new Set<() => void>()

let pending: Record<string, unknown> = {}
let flushTimer: ReturnType<typeof setTimeout> | null = null

function notify() {
  for (const l of listeners) l()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function flush() {
  flushTimer = null
  const values = pending
  pending = {}
  if (Object.keys(values).length === 0) return
  api.patchSettings(values).catch(() => {
    // Preferences are non-critical; the cache keeps the UI consistent and the
    // next change retries the write.
  })
}

export async function hydrateSettings(): Promise<void> {
  try {
    const stored = await api.settings()
    cache = { ...SETTING_DEFAULTS, ...stored }
  } catch {
    cache = { ...SETTING_DEFAULTS }
  }
  hydrated = true
  notify()
}

export function settingsHydrated(): boolean {
  return hydrated
}

export function readSetting<T>(key: string, fallback?: T): T {
  if (key in cache && cache[key] !== undefined && cache[key] !== null) {
    return cache[key] as T
  }
  if (fallback !== undefined) return fallback
  return SETTING_DEFAULTS[key] as T
}

export function writeSetting(key: string, value: unknown): void {
  if (Object.is(cache[key], value)) return
  cache = { ...cache, [key]: value }
  pending[key] = value
  notify()
  if (flushTimer == null) flushTimer = setTimeout(flush, 250)
}

/** Bulk write without per-key debounce churn — used by backup restore. */
export function replaceSettings(values: Record<string, unknown>): void {
  cache = { ...SETTING_DEFAULTS, ...values }
  notify()
}

/** `@AppStorage("key")` — returns [value, setValue]. */
export function useSetting<T>(
  key: string,
  fallback?: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => readSetting<T>(key, fallback),
    () => readSetting<T>(key, fallback),
  )
  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved =
        typeof next === 'function'
          ? (next as (prev: T) => T)(readSetting<T>(key, fallback))
          : next
      writeSetting(key, resolved)
    },
    [key, fallback],
  )
  return [value, set]
}

// ── Typed convenience accessors ──────────────────────────────────────────────

export function edgeSchemaKey(metric: string): string {
  return `graph.edge.colorSchema.${metric}`
}

export function readEdgeSchema(metric: string): EdgeColorSchema {
  return readSetting<EdgeColorSchema>(edgeSchemaKey(metric))
}

/** Per-project JSON blobs, keyed exactly like the Swift UserDefaults entries. */
export const projectKeys = {
  filterGroups: (projectId: string) => `filterGroups_${projectId}`,
  happyPaths: (projectId: string) => `happyPaths_${projectId}`,
  norms: (projectId: string) => `norms_${projectId}`,
  normsMetric: (projectId: string) => `norms_metric_${projectId}`,
  llmPrompt: (projectId: string) => `llm_prompt_${projectId}`,
  layout: (projectId: string, chartMode: string) => `layout_${projectId}_${chartMode}`,
  collapsedGroups: (projectId: string, chartMode: string) =>
    `graph.collapsedGroups_${projectId}_${chartMode}`,
}

export function readJSON<T>(key: string, fallback: T): T {
  const value = cache[key]
  return value === undefined || value === null ? fallback : (value as T)
}

export function writeJSON(key: string, value: unknown): void {
  writeSetting(key, value)
}
