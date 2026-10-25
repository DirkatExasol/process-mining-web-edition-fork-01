/** filterNotifications — the Dashboard Notifications section's client-side filters
 *  (severity / triggered / enabled / triggered-at). Pure, so unit-tested directly. */

import { describe, expect, it } from 'vitest'
import {
  NOTIF_FILTER_DEFAULTS,
  filterNotifications,
  notifFiltersActive,
  type NotifFilters,
} from './DashboardView'
import type { NotificationRule } from '../types'

const NOW = Date.parse('2026-10-08T12:00:00Z')
const ago = (secs: number) => new Date(NOW - secs * 1000).toISOString()

const rule = (over: Partial<NotificationRule> = {}): NotificationRule => ({
  id: 'r', connectionId: 'c', projectId: 1, projectTitle: 'P', kind: 'transition_metric',
  name: '', severity: 'IMPORTANT', intervalSecs: 300, enabled: true,
  config: { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 60 },
  state: {},
  ...over,
})

const f = (over: Partial<NotifFilters> = {}): NotifFilters => ({ ...NOTIF_FILTER_DEFAULTS, ...over })
const ids = (rs: NotificationRule[]) => rs.map((r) => r.id)

describe('notifFiltersActive', () => {
  it('is false for the defaults and true once any filter is set', () => {
    expect(notifFiltersActive(NOTIF_FILTER_DEFAULTS)).toBe(false)
    expect(notifFiltersActive(f({ severity: 'URGENT' }))).toBe(true)
    expect(notifFiltersActive(f({ triggeredAt: 'hour' }))).toBe(true)
  })
})

describe('filterNotifications', () => {
  const urgentFiring = rule({ id: 'u', severity: 'URGENT', state: { triggered: true, triggeredAt: ago(1800) } })
  const infoOk = rule({ id: 'i', severity: 'INFO', state: { triggered: false, lastRunAt: 'x' } })
  const disabled = rule({ id: 'd', enabled: false, state: { triggered: true, triggeredAt: ago(60) } })
  const oldFiring = rule({ id: 'o', state: { triggered: true, triggeredAt: ago(3 * 86400) } })
  const all = [urgentFiring, infoOk, disabled, oldFiring]

  it('returns everything with the default filters', () => {
    expect(ids(filterNotifications(all, NOTIF_FILTER_DEFAULTS, NOW))).toEqual(['u', 'i', 'd', 'o'])
  })

  it('filters by severity', () => {
    expect(ids(filterNotifications(all, f({ severity: 'URGENT' }), NOW))).toEqual(['u'])
    expect(ids(filterNotifications(all, f({ severity: 'INFO' }), NOW))).toEqual(['i'])
  })

  it('filters by triggered (a disabled firing rule does not count as triggered)', () => {
    expect(ids(filterNotifications(all, f({ triggered: 'yes' }), NOW))).toEqual(['u', 'o'])
    expect(ids(filterNotifications(all, f({ triggered: 'no' }), NOW))).toEqual(['i', 'd'])
  })

  it('filters by enabled', () => {
    expect(ids(filterNotifications(all, f({ enabled: 'no' }), NOW))).toEqual(['d'])
    expect(ids(filterNotifications(all, f({ enabled: 'yes' }), NOW))).toEqual(['u', 'i', 'o'])
  })

  it('filters by the triggered-at window (only currently-firing rules within it)', () => {
    // Last hour: only the rule that fired 30 min ago.
    expect(ids(filterNotifications(all, f({ triggeredAt: 'hour' }), NOW))).toEqual(['u'])
    // Last week: the 30-min and the 3-day firing rules; never the non-triggered / disabled ones.
    expect(ids(filterNotifications(all, f({ triggeredAt: 'week' }), NOW))).toEqual(['u', 'o'])
  })

  it('combines filters (AND)', () => {
    expect(ids(filterNotifications(all, f({ severity: 'URGENT', triggeredAt: 'hour' }), NOW))).toEqual(['u'])
    // Contradictory: triggered=No with a time window → nothing.
    expect(filterNotifications(all, f({ triggered: 'no', triggeredAt: 'hour' }), NOW)).toEqual([])
  })
})

describe('filterNotifications — type / note scope / note severity', () => {
  const event = rule({ id: 'e' })
  const noteShared = rule({
    id: 'ns', kind: 'note',
    config: { comparator: '>=', threshold: 1, scope: 'shared', minImportance: 'IMPORTANT' },
    state: { triggered: true, triggeredAt: ago(60), note: { noteId: 'n1', importance: 'URGENT', scope: 'shared' } as never },
  })
  const notePersonal = rule({
    id: 'np', kind: 'note',
    config: { comparator: '>=', threshold: 1, scope: 'all', minImportance: 'NORMAL' },
    state: { triggered: true, triggeredAt: ago(60), note: { noteId: 'n2', importance: 'INFO', scope: 'personal' } as never },
  })
  const noteUntriggered = rule({
    id: 'nu', kind: 'note',
    config: { comparator: '>=', threshold: 1, scope: 'shared', minImportance: 'IMPORTANT' },
    state: {},
  })
  const all = [event, noteShared, notePersonal, noteUntriggered]

  it('filters by type (event vs note)', () => {
    expect(ids(filterNotifications(all, f({ type: 'event' }), NOW))).toEqual(['e'])
    expect(ids(filterNotifications(all, f({ type: 'note' }), NOW))).toEqual(['ns', 'np', 'nu'])
  })

  it('narrows notes by scope — using the matched note, or the config when untriggered', () => {
    // 'ns' matched a shared note; 'nu' is untriggered but configured shared → both pass. The
    // event rule passes too (scope only narrows notes).
    expect(ids(filterNotifications(all, f({ scope: 'shared' }), NOW))).toEqual(['e', 'ns', 'nu'])
    expect(ids(filterNotifications(all, f({ scope: 'personal' }), NOW))).toEqual(['e', 'np'])
  })

  it('narrows notes by the matched note severity (config fallback when untriggered)', () => {
    expect(ids(filterNotifications(all, f({ type: 'note', noteSeverity: 'URGENT' }), NOW))).toEqual(['ns'])
    // 'nu' falls back to its configured minImportance (IMPORTANT).
    expect(ids(filterNotifications(all, f({ type: 'note', noteSeverity: 'IMPORTANT' }), NOW))).toEqual(['nu'])
  })
})
