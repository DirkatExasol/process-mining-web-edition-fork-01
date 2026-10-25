/** Create / edit dashboard notification rules — a Sheet that lists the existing rules
 *  (grouped by connection → process) and an editor for one rule. The only check kind today
 *  is a metric on the transition from one step to a following one; the editor is organised so
 *  a future kind can add its own sub-form behind a "Check type" selector. */

import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Sheet } from './ui'
import { formatDuration } from '../graph/format'
import { disablePush, enablePush, isPushEnabled, pushSupported } from '../push'
import {
  NOTE_IMPORTANCE_LEVELS,
  NOTE_IMPORTANCE_META,
  NOTIFICATION_COMPARATORS,
  NOTIFICATION_INTERVALS,
  NOTIFICATION_JOURNEY_METRICS,
  NOTIFICATION_KINDS,
  NOTIFICATION_LOOKBACK_UNITS,
  NOTIFICATION_METRICS,
  NOTIFICATION_NOTE_EVENTS,
  NOTIFICATION_NOTE_SCOPES,
  NOTIFICATION_SEVERITIES,
  NOTIFICATION_TIME_METRICS,
  type DashboardConnection,
  type NotificationMetric,
  type NotificationRule,
} from '../types'

const STYLE = `
.nwz-list{display:flex;flex-direction:column;gap:6px}
.nwz-grp{font-size:11px;font-weight:700;color:var(--secondary);text-transform:uppercase;
  letter-spacing:.03em;margin:8px 0 2px}
.nwz-row{display:flex;align-items:center;gap:10px;border:1px solid var(--separator);
  border-radius:var(--radius);padding:7px 10px;background:var(--bg-elevated)}
.nwz-row .dot{width:9px;height:9px;border-radius:50%;flex:none}
.nwz-row .desc{flex:1;min-width:0;font-size:12.5px}
.nwz-row .desc .sub{color:var(--secondary);font-size:11px}
.nwz-row.off{opacity:.55}
.nwz-empty{color:var(--secondary);font-size:12.5px;padding:10px 0}
.nwz-sevpick{display:flex;gap:6px}
.nwz-sev{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--separator);
  border-radius:999px;padding:3px 10px;font-size:12px;cursor:pointer;background:var(--bg-fill)}
.nwz-sev .dot{width:8px;height:8px;border-radius:50%}
.nwz-sev.on{border-color:var(--accent-border);background:var(--accent-soft);font-weight:700}
.nwz-crit{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.nwz-note{color:var(--orange);font-size:12px;margin-top:8px}
.nwz-test{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.nwz-tres{font-size:12.5px;font-weight:700}
.nwz-tres.fire{color:var(--red)}
.nwz-tres.ok{color:var(--green)}
.nwz-tres.warn{color:var(--orange)}
.nwz-tres.idle{color:var(--secondary)}
.nwz-testhint{font-size:10.5px;color:var(--secondary);flex-basis:100%}
.nwz-remote{display:flex;flex-direction:column;gap:7px;border:1px solid var(--separator);
  border-radius:10px;padding:10px 12px}
.nwz-remote-h{font-size:11px;font-weight:700;color:var(--secondary);text-transform:uppercase;
  letter-spacing:.03em}
.nwz-remote-note{font-size:12px;color:var(--primary);display:flex;flex-direction:column;gap:5px}
.nwz-remote-sub{font-size:11px;color:var(--secondary)}
.nwz-link{background:none;border:none;color:var(--accent);cursor:pointer;padding:0;
  font-size:12px;font-weight:600;text-decoration:underline}
.nwz-link[disabled]{opacity:.6;cursor:progress;text-decoration:none}
`

const UNITS: { key: string; label: string; secs: number }[] = [
  { key: 's', label: 'seconds', secs: 1 },
  { key: 'm', label: 'minutes', secs: 60 },
  { key: 'h', label: 'hours', secs: 3600 },
  { key: 'd', label: 'days', secs: 86400 },
]

/** Pick the coarsest unit that represents `secs` as a tidy number, for pre-filling the editor. */
function bestUnit(secs: number): { value: number; unit: string } {
  for (const u of [...UNITS].reverse()) {
    if (secs >= u.secs && secs % u.secs === 0) return { value: secs / u.secs, unit: u.key }
  }
  return { value: secs, unit: 's' }
}

interface Draft {
  id: string | null
  connectionId: string
  projectId: number
  kind: string
  name: string
  severity: string
  intervalSecs: number
  enabled: boolean
  fromStep: string
  toStep: string
  metric: NotificationMetric
  comparator: string
  thresholdValue: number
  thresholdUnit: string
  lookbackUnit: string
  lookbackValue: number
  // note kind
  noteEvent: string
  noteMinImportance: string
  noteScope: string
  noteThreshold: number
  webpush: boolean
  smtp: boolean
  smtpRecipients: string
}

function newDraft(groups: DashboardConnection[]): Draft {
  const g = groups[0]
  const p = g?.projects[0]
  return {
    id: null,
    connectionId: g?.id || '',
    projectId: p?.projectId ?? 0,
    kind: 'transition_metric',
    name: '',
    severity: 'IMPORTANT',
    intervalSecs: 300,
    enabled: true,
    fromStep: '',
    toStep: '',
    metric: 'Avg Time',
    comparator: '>',
    thresholdValue: 2,
    thresholdUnit: 'h',
    lookbackUnit: 'all',
    lookbackValue: 7,
    noteEvent: 'created',
    noteMinImportance: 'NORMAL',
    noteScope: 'shared',
    noteThreshold: 1,
    webpush: false,
    smtp: false,
    smtpRecipients: '',
  }
}

function draftFromRule(r: NotificationRule): Draft {
  const isTime = NOTIFICATION_TIME_METRICS.has(r.config.metric ?? '')
  const t = isTime ? bestUnit(r.config.threshold) : { value: r.config.threshold, unit: 's' }
  const smtp = r.delivery?.smtp || null
  return {
    id: r.id,
    connectionId: r.connectionId,
    projectId: r.projectId,
    kind: r.kind || 'transition_metric',
    name: r.name,
    severity: r.severity,
    intervalSecs: r.intervalSecs,
    enabled: r.enabled,
    fromStep: r.config.fromStep || '',
    toStep: r.config.toStep || '',
    metric: r.config.metric ?? 'Avg Time',
    comparator: r.kind === 'note' ? '>' : r.config.comparator,
    thresholdValue: t.value,
    thresholdUnit: t.unit,
    lookbackUnit: r.config.lookbackUnit || 'all',
    lookbackValue: r.config.lookbackValue && r.config.lookbackValue > 0 ? r.config.lookbackValue : 7,
    noteEvent: r.config.event || 'created',
    noteMinImportance: r.config.minImportance || 'NORMAL',
    noteScope: r.config.scope || 'shared',
    noteThreshold: r.kind === 'note' && r.config.threshold > 0 ? r.config.threshold : 1,
    webpush: !!r.delivery?.webpush,
    smtp: !!smtp,
    smtpRecipients: smtp ? (smtp.recipients || []).join(', ') : '',
  }
}

/** A one-line, human description of a rule's criterion (e.g. "Avg Time A → B is greater
 *  than 2h", or "Journey duration (Max Time) is greater than 2h"). Exported for the
 *  Dashboard tiles. */
export function ruleSummary(r: NotificationRule): string {
  const c = r.config
  const lb =
    c.lookbackUnit && c.lookbackUnit !== 'all' && c.lookbackValue
      ? ` · last ${c.lookbackValue} ${c.lookbackUnit}`
      : ''
  if (r.kind === 'note') return noteSummary(c) + lb
  const cmp = NOTIFICATION_COMPARATORS.find((x) => x.op === c.comparator)?.label || c.comparator
  const thr = NOTIFICATION_TIME_METRICS.has(c.metric ?? '')
    ? formatDuration(c.threshold)
    : c.threshold.toLocaleString()
  const subject =
    r.kind === 'journey_duration'
      ? `Journey duration (${c.metric})`
      : `${c.metric} ${c.fromStep} → ${c.toStep}`
  return `${subject} ${cmp} ${thr}${lb}`
}

/** One-line description of a note rule's criterion, e.g. "New shared notes (Important+)". */
function noteSummary(c: NotificationRule['config']): string {
  const ev = NOTIFICATION_NOTE_EVENTS.find((e) => e.event === c.event)?.label || 'Notes'
  const scope = c.scope === 'all' ? 'any' : 'shared'
  const imp = c.minImportance && c.minImportance !== 'NORMAL' ? ` (${titleCase(c.minImportance)}+)` : ''
  const n = c.threshold && c.threshold > 1 ? ` ≥ ${c.threshold}` : ''
  return `${ev} · ${scope}${imp}${n}`
}

function titleCase(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : s
}

/** A measured metric value formatted for display (duration metrics as a time). */
function fmtMeasured(metric: string, value: number | null): string {
  if (value == null) return '—'
  return NOTIFICATION_TIME_METRICS.has(metric) ? formatDuration(value) : value.toLocaleString()
}

export function NotificationWizard({
  groups,
  rules,
  onClose,
  onChanged,
}: {
  groups: DashboardConnection[]
  rules: NotificationRule[]
  onClose: () => void
  onChanged: () => void
}) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [steps, setSteps] = useState<string[]>([])
  const [stepsBusy, setStepsBusy] = useState(false)
  const [stepsErr, setStepsErr] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{
    ok: boolean
    value: number | null
    triggered: boolean
    hasData: boolean
    error: string | null
  } | null>(null)
  // Web Push device state: is this browser subscribed? (null = still checking)
  const pushAvailable = pushSupported()
  const [pushOn, setPushOn] = useState<boolean | null>(null)
  const [pushBusy, setPushBusy] = useState(false)
  const [pushErr, setPushErr] = useState<string | null>(null)
  const [testPushMsg, setTestPushMsg] = useState<string | null>(null)

  const canCreate = groups.some((g) => g.projects.length > 0)

  // Load the chosen project's step names for the from/to pickers whenever they change.
  // A journey_duration rule has no steps, so it never needs them.
  useEffect(() => {
    if (!draft || draft.kind !== 'transition_metric' || !draft.connectionId || !draft.projectId) {
      setSteps([])
      return
    }
    let alive = true
    setStepsBusy(true)
    setStepsErr(null)
    api
      .notificationSteps(draft.connectionId, draft.projectId)
      .then((r) => {
        if (!alive) return
        setSteps(r.steps)
      })
      .catch((e) => alive && setStepsErr(e?.message || 'Could not load steps.'))
      .finally(() => alive && setStepsBusy(false))
    return () => {
      alive = false
    }
  }, [draft?.kind, draft?.connectionId, draft?.projectId])

  const projectsFor = (connId: string) => groups.find((g) => g.id === connId)?.projects || []
  const isTime = draft ? NOTIFICATION_TIME_METRICS.has(draft.metric) : false
  // A journey_duration rule measures the whole case — no from/to steps, time metrics only.
  const isJourney = draft?.kind === 'journey_duration'
  const isNote = draft?.kind === 'note'
  const metricChoices = isJourney ? NOTIFICATION_JOURNEY_METRICS : NOTIFICATION_METRICS

  const grouped = useMemo(() => {
    const byKey = new Map<string, { title: string; connName: string; rules: NotificationRule[] }>()
    for (const r of rules) {
      const key = `${r.connectionId}::${r.projectId}`
      const bucket = byKey.get(key) || {
        title: r.projectTitle || `Project ${r.projectId}`,
        connName: r.connectionName || '',
        rules: [],
      }
      bucket.rules.push(r)
      byKey.set(key, bucket)
    }
    return [...byKey.values()]
  }, [rules])

  // The request body built from the current draft — shared by Save and Test.
  const buildBody = (d: Draft) => {
    const timed = NOTIFICATION_TIME_METRICS.has(d.metric)
    const factor = timed ? UNITS.find((u) => u.key === d.thresholdUnit)?.secs || 1 : 1
    const project = projectsFor(d.connectionId).find((p) => p.projectId === d.projectId)
    const criterion = {
      metric: d.metric,
      comparator: d.comparator,
      threshold: d.thresholdValue * factor,
      lookbackUnit: d.lookbackUnit,
      lookbackValue: d.lookbackUnit === 'all' ? 0 : d.lookbackValue,
    }
    // A note rule carries its own config (event/importance/scope/min-count/window).
    const noteConfig = {
      event: d.noteEvent,
      minImportance: d.noteMinImportance,
      scope: d.noteScope,
      comparator: '>=',
      threshold: Math.max(1, d.noteThreshold),
      lookbackUnit: d.noteEvent === 'open' ? 'all' : d.lookbackUnit,
      lookbackValue: d.noteEvent === 'open' || d.lookbackUnit === 'all' ? 0 : d.lookbackValue,
    }
    return {
      connectionId: d.connectionId,
      projectId: d.projectId,
      projectTitle: project?.title || '',
      kind: d.kind,
      name: d.name,
      severity: d.severity,
      intervalSecs: d.intervalSecs,
      enabled: d.enabled,
      // note → its own config; journey_duration → criterion; transition_metric → +steps.
      config:
        d.kind === 'note'
          ? noteConfig
          : d.kind === 'journey_duration'
            ? criterion
            : { fromStep: d.fromStep, toStep: d.toStep, ...criterion },
      delivery: {
        webpush: d.webpush,
        smtp: d.smtp
          ? {
              recipients: d.smtpRecipients
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean),
            }
          : false,
      },
    }
  }

  const save = async () => {
    if (!draft) return
    if (!draft.connectionId || !draft.projectId) {
      setErr('Choose a connection and a process.')
      return
    }
    if (draft.kind === 'transition_metric' && (!draft.fromStep || !draft.toStep)) {
      setErr('Choose both a from-step and a to-step.')
      return
    }
    setSaving(true)
    setErr(null)
    try {
      const body = buildBody(draft)
      if (draft.id) await api.updateNotification(draft.id, body)
      else await api.saveNotification(body)
      onChanged()
      setDraft(null)
    } catch (e) {
      setErr((e as Error)?.message || 'Could not save the rule.')
    } finally {
      setSaving(false)
    }
  }

  const runTest = async () => {
    if (!draft) return
    if (draft.kind === 'transition_metric' && (!draft.fromStep || !draft.toStep)) {
      setErr('Choose both a from-step and a to-step before testing.')
      return
    }
    setTesting(true)
    setErr(null)
    setTestResult(null)
    try {
      setTestResult(await api.testNotification(buildBody(draft)))
    } catch (e) {
      setErr((e as Error)?.message || 'Could not run the test.')
    } finally {
      setTesting(false)
    }
  }

  // Check whether this browser is already subscribed to push (only while editing).
  useEffect(() => {
    if (!draft || !pushAvailable) {
      setPushOn(pushAvailable ? pushOn : false)
      return
    }
    let alive = true
    isPushEnabled()
      .then((v) => alive && setPushOn(v))
      .catch(() => alive && setPushOn(false))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!draft, pushAvailable])

  const enableDevicePush = async () => {
    setPushBusy(true)
    setPushErr(null)
    try {
      await enablePush()
      setPushOn(true)
    } catch (e) {
      setPushErr((e as Error)?.message || 'Could not enable push on this device.')
    } finally {
      setPushBusy(false)
    }
  }

  const disableDevicePush = async () => {
    setPushBusy(true)
    setPushErr(null)
    try {
      await disablePush()
      setPushOn(false)
    } catch (e) {
      setPushErr((e as Error)?.message || 'Could not disable push.')
    } finally {
      setPushBusy(false)
    }
  }

  const sendTestPush = async () => {
    setPushBusy(true)
    setPushErr(null)
    setTestPushMsg(null)
    try {
      const r = await api.pushTest()
      if (r.sent > 0) {
        setTestPushMsg(
          `Sent to ${r.sent} device${r.sent === 1 ? '' : 's'}.` +
            (r.errors.length ? ` (${r.errors.join(' ')})` : ' It should appear shortly.'),
        )
      } else {
        setTestPushMsg(r.errors.join(' ') || 'No push was sent.')
      }
    } catch (e) {
      setPushErr((e as Error)?.message || 'Could not send a test push.')
    } finally {
      setPushBusy(false)
    }
  }

  // A result refers to one exact criterion — drop it as soon as any part of it changes.
  useEffect(() => {
    setTestResult(null)
  }, [
    draft?.kind,
    draft?.connectionId,
    draft?.projectId,
    draft?.fromStep,
    draft?.toStep,
    draft?.metric,
    draft?.comparator,
    draft?.thresholdValue,
    draft?.thresholdUnit,
    draft?.lookbackUnit,
    draft?.lookbackValue,
    draft?.noteEvent,
    draft?.noteMinImportance,
    draft?.noteScope,
    draft?.noteThreshold,
  ])

  const remove = async () => {
    if (!draft?.id) return
    setSaving(true)
    try {
      await api.deleteNotification(draft.id)
      onChanged()
      setDraft(null)
    } catch (e) {
      setErr((e as Error)?.message || 'Could not delete the rule.')
    } finally {
      setSaving(false)
      setConfirmDel(false)
    }
  }

  // ── the list view ──────────────────────────────────────────────────────────
  if (!draft) {
    const footer = (
      <>
        <button className="btn" onClick={onClose}>
          Close
        </button>
        <button
          className="btn prominent"
          disabled={!canCreate}
          title={canCreate ? 'Create a new rule' : 'No processes available'}
          onClick={() => {
            setErr(null)
            setDraft(newDraft(groups))
          }}
        >
          ＋ New rule
        </button>
      </>
    )
    return (
      <Sheet title="Notifications" icon="🔔" wide onClose={onClose} footer={footer}>
        <style>{STYLE}</style>
        {rules.length === 0 && (
          <div className="nwz-empty">
            No notification rules yet. Create one to be alerted when a transition's metric
            crosses a threshold.
          </div>
        )}
        <div className="nwz-list">
          {grouped.map((g) => (
            <div key={`${g.connName}:${g.title}`}>
              <div className="nwz-grp">
                {g.connName ? `${g.connName} · ` : ''}
                {g.title}
              </div>
              {g.rules.map((r) => {
                const sev = NOTIFICATION_SEVERITIES.find((s) => s.key === r.severity)
                return (
                  <button
                    key={r.id}
                    className={`nwz-row${r.enabled ? '' : ' off'}`}
                    style={{ width: '100%', textAlign: 'left', cursor: 'pointer' }}
                    onClick={() => {
                      setErr(null)
                      setConfirmDel(false)
                      setDraft(draftFromRule(r))
                    }}
                  >
                    <i className="dot" style={{ background: sev?.color || 'var(--secondary)' }} />
                    <span className="desc">
                      <div>{r.name || ruleSummary(r)}</div>
                      <div className="sub">
                        {r.name ? `${ruleSummary(r)} · ` : ''}
                        every {NOTIFICATION_INTERVALS.find((i) => i.secs === r.intervalSecs)?.label ||
                          `${r.intervalSecs}s`}
                        {r.enabled ? '' : ' · disabled'}
                      </div>
                    </span>
                    <span aria-hidden>✏️</span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </Sheet>
    )
  }

  // ── the editor view ──────────────────────────────────────────────────────────
  const footer = (
    <>
      {draft.id &&
        (confirmDel ? (
          <button className="btn destructive" disabled={saving} onClick={remove}>
            Confirm delete
          </button>
        ) : (
          <button className="btn destructive" disabled={saving} onClick={() => setConfirmDel(true)}>
            Delete
          </button>
        ))}
      <button className="btn" disabled={saving} onClick={() => setDraft(null)}>
        Cancel
      </button>
      <button className="btn prominent" disabled={saving} onClick={save}>
        {saving ? 'Saving…' : draft.id ? 'Save changes' : 'Create rule'}
      </button>
    </>
  )
  return (
    <Sheet
      title={draft.id ? 'Edit notification' : 'New notification'}
      icon="🔔"
      wide
      onClose={onClose}
      footer={footer}
    >
      <style>{STYLE}</style>
      <div className="form-grid">
        <label>
          Connection
          <select
            className="text-input"
            value={draft.connectionId}
            disabled={!!draft.id}
            onChange={(e) => {
              const connectionId = e.target.value
              const first = projectsFor(connectionId)[0]
              setDraft({
                ...draft,
                connectionId,
                projectId: first?.projectId ?? 0,
                fromStep: '',
                toStep: '',
              })
            }}
          >
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Process
          <select
            className="text-input"
            value={draft.projectId}
            disabled={!!draft.id}
            onChange={(e) =>
              setDraft({ ...draft, projectId: Number(e.target.value), fromStep: '', toStep: '' })
            }
          >
            {projectsFor(draft.connectionId).map((p) => (
              <option key={p.projectId} value={p.projectId}>
                {p.title}
              </option>
            ))}
          </select>
        </label>

        <label className="span-2">
          Check type
          <select
            className="text-input"
            value={draft.kind}
            onChange={(e) => {
              const kind = e.target.value
              // Journey duration has only time metrics — drop Count if it was selected.
              const metric =
                kind === 'journey_duration' && !NOTIFICATION_TIME_METRICS.has(draft.metric)
                  ? 'Avg Time'
                  : draft.metric
              setDraft({ ...draft, kind, metric })
            }}
          >
            {NOTIFICATION_KINDS.map((k) => (
              <option key={k.kind} value={k.kind}>
                {k.label}
              </option>
            ))}
          </select>
          <span className="nwz-testhint" style={{ marginTop: 4 }}>
            {NOTIFICATION_KINDS.find((k) => k.kind === draft.kind)?.help}
          </span>
        </label>

        {!isJourney && !isNote && (
          <>
            <label>
              From step
              <select
                className="text-input"
                value={draft.fromStep}
                onChange={(e) => setDraft({ ...draft, fromStep: e.target.value })}
              >
                <option value="">{stepsBusy ? 'Loading…' : 'Choose a step'}</option>
                {steps.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label>
              To step (the following step)
              <select
                className="text-input"
                value={draft.toStep}
                onChange={(e) => setDraft({ ...draft, toStep: e.target.value })}
              >
                <option value="">{stepsBusy ? 'Loading…' : 'Choose a step'}</option>
                {steps.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        {isNote && (
          <>
            <label>
              Watch
              <select
                className="text-input"
                value={draft.noteEvent}
                onChange={(e) => setDraft({ ...draft, noteEvent: e.target.value })}
              >
                {NOTIFICATION_NOTE_EVENTS.map((ev) => (
                  <option key={ev.event} value={ev.event}>
                    {ev.label}
                  </option>
                ))}
              </select>
              <span className="nwz-testhint" style={{ marginTop: 4 }}>
                {NOTIFICATION_NOTE_EVENTS.find((e) => e.event === draft.noteEvent)?.help}
              </span>
            </label>
            <label>
              Minimum importance
              <select
                className="text-input"
                value={draft.noteMinImportance}
                onChange={(e) => setDraft({ ...draft, noteMinImportance: e.target.value })}
              >
                {NOTE_IMPORTANCE_LEVELS.map((lvl) => (
                  <option key={lvl} value={lvl}>
                    {NOTE_IMPORTANCE_META[lvl].label}
                    {lvl !== 'URGENT' ? ' and up' : ''}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Which notes
              <select
                className="text-input"
                value={draft.noteScope}
                onChange={(e) => setDraft({ ...draft, noteScope: e.target.value })}
              >
                {NOTIFICATION_NOTE_SCOPES.map((s) => (
                  <option key={s.scope} value={s.scope}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Fire when at least
              <div className="nwz-crit">
                <input
                  className="text-input"
                  type="number"
                  min={1}
                  step={1}
                  style={{ width: 90 }}
                  value={draft.noteThreshold}
                  onChange={(e) =>
                    setDraft({ ...draft, noteThreshold: Math.max(1, Number(e.target.value) || 1) })
                  }
                />
                <span className="dash-ml" style={{ alignSelf: 'center' }}>
                  matching note(s)
                </span>
              </div>
            </label>
          </>
        )}

        {!isNote && (
          <label className="span-2">
            {isJourney ? 'Trigger when the journey duration’s' : 'Trigger when'}
            <div className="nwz-crit">
              <select
                className="text-input"
                style={{ width: 'auto' }}
                value={draft.metric}
                onChange={(e) => setDraft({ ...draft, metric: e.target.value as NotificationMetric })}
              >
                {metricChoices.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <select
                className="text-input"
                style={{ width: 'auto' }}
                value={draft.comparator}
                onChange={(e) => setDraft({ ...draft, comparator: e.target.value })}
              >
                {NOTIFICATION_COMPARATORS.map((c) => (
                  <option key={c.op} value={c.op}>
                    {c.label} ({c.op})
                  </option>
                ))}
              </select>
              <input
                className="text-input"
                type="number"
                min={0}
                step="any"
                style={{ width: 90 }}
                value={draft.thresholdValue}
                onChange={(e) => setDraft({ ...draft, thresholdValue: Number(e.target.value) })}
              />
              {isTime ? (
                <select
                  className="text-input"
                  style={{ width: 'auto' }}
                  value={draft.thresholdUnit}
                  onChange={(e) => setDraft({ ...draft, thresholdUnit: e.target.value })}
                >
                  {UNITS.map((u) => (
                    <option key={u.key} value={u.key}>
                      {u.label}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="dash-ml" style={{ alignSelf: 'center' }}>
                  occurrences
                </span>
              )}
            </div>
          </label>
        )}

        {!(isNote && draft.noteEvent === 'open') && (
        <label className="span-2">
          {isNote ? 'Look back over (how recent the note activity is)' : 'Look back over (base period for the measurement)'}
          <div className="nwz-crit">
            <select
              className="text-input"
              style={{ width: 'auto' }}
              value={draft.lookbackUnit}
              onChange={(e) => setDraft({ ...draft, lookbackUnit: e.target.value })}
            >
              {NOTIFICATION_LOOKBACK_UNITS.map((u) => (
                <option key={u.unit} value={u.unit}>
                  {u.label}
                </option>
              ))}
            </select>
            {draft.lookbackUnit !== 'all' && (
              <>
                <input
                  className="text-input"
                  type="number"
                  min={1}
                  step={1}
                  style={{ width: 90 }}
                  value={draft.lookbackValue}
                  onChange={(e) =>
                    setDraft({ ...draft, lookbackValue: Math.max(1, Number(e.target.value) || 1) })
                  }
                />
                <span className="dash-ml" style={{ alignSelf: 'center' }}>
                  before now
                </span>
              </>
            )}
          </div>
        </label>
        )}

        <label>
          Check every
          <select
            className="text-input"
            value={draft.intervalSecs}
            onChange={(e) => setDraft({ ...draft, intervalSecs: Number(e.target.value) })}
          >
            {NOTIFICATION_INTERVALS.map((i) => (
              <option key={i.secs} value={i.secs}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Severity
          <div className="nwz-sevpick">
            {NOTIFICATION_SEVERITIES.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`nwz-sev${draft.severity === s.key ? ' on' : ''}`}
                onClick={() => setDraft({ ...draft, severity: s.key })}
              >
                <i className="dot" style={{ background: s.color }} />
                {s.label}
              </button>
            ))}
          </div>
        </label>

        <label className="span-2">
          Name (optional)
          <input
            className="text-input"
            type="text"
            placeholder={
              isJourney || isNote || (draft.fromStep && draft.toStep)
                ? ruleSummaryDraft(draft)
                : 'A short label'
            }
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </label>

        <label className="span-2" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            style={{ width: 'auto' }}
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          Enabled (the engine checks this rule)
        </label>

        <div className="span-2 nwz-remote">
          <div className="nwz-remote-h">Remote notifications</div>
          <label className="row" style={{ gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              style={{ width: 'auto' }}
              checked={draft.webpush}
              onChange={(e) => setDraft({ ...draft, webpush: e.target.checked })}
            />
            Web browser push
          </label>
          {draft.webpush && (
            <div className="nwz-remote-note">
              <div className="nwz-remote-sub">
                Sends a browser notification when this rule triggers to everyone on this
                connection who has enabled push on a device.
              </div>
              {!pushAvailable ? (
                <span className="nwz-tres warn">
                  This browser doesn&rsquo;t support push notifications (a secure https:// context
                  is required).
                </span>
              ) : pushOn === null ? (
                <span className="nwz-remote-sub">Checking this device…</span>
              ) : pushOn ? (
                <span>
                  ✓ Push is enabled on this device.{' '}
                  <button
                    type="button"
                    className="nwz-link"
                    disabled={pushBusy}
                    onClick={sendTestPush}
                  >
                    {pushBusy ? 'Working…' : 'Send a test notification'}
                  </button>
                  {' · '}
                  <button
                    type="button"
                    className="nwz-link"
                    disabled={pushBusy}
                    onClick={disableDevicePush}
                  >
                    Disable on this device
                  </button>
                  {testPushMsg && <div className="nwz-remote-sub">{testPushMsg}</div>}
                </span>
              ) : (
                <span>
                  To receive these on this device,{' '}
                  <button
                    type="button"
                    className="nwz-link"
                    disabled={pushBusy}
                    onClick={enableDevicePush}
                  >
                    {pushBusy ? 'Enabling…' : 'enable browser push'}
                  </button>
                  .
                </span>
              )}
              {pushErr && <div className="nwz-note">{pushErr}</div>}
            </div>
          )}
          <label className="row" style={{ gap: 8, alignItems: 'center', marginTop: 2 }}>
            <input
              type="checkbox"
              style={{ width: 'auto' }}
              checked={draft.smtp}
              onChange={(e) => setDraft({ ...draft, smtp: e.target.checked })}
            />
            Email
          </label>
          {draft.smtp && (
            <div className="nwz-remote-note">
              <input
                className="text-input"
                type="text"
                placeholder="recipients, comma-separated (optional)"
                value={draft.smtpRecipients}
                onChange={(e) => setDraft({ ...draft, smtpRecipients: e.target.value })}
              />
              <div className="nwz-remote-sub">
                Leave blank to email everyone assigned to this connection who has an address on
                file. Requires an SMTP server configured by an administrator (Admin &rarr;
                Notifications).
              </div>
            </div>
          )}
        </div>

        <div className="span-2 nwz-test">
          <button
            type="button"
            className="btn"
            disabled={testing || (draft.kind === 'transition_metric' && (!draft.fromStep || !draft.toStep))}
            onClick={runTest}
            title="Evaluate this rule against the current data now, without saving"
          >
            {testing ? 'Testing…' : 'Test now'}
          </button>
          {testResult &&
            (testResult.error ? (
              <span className="nwz-tres warn">Couldn't run: {testResult.error}</span>
            ) : !testResult.hasData ? (
              <span className="nwz-tres idle">
                {isNote
                  ? 'No matching notes in the selected window.'
                  : isJourney
                    ? 'No data — no journeys in the selected base period.'
                    : 'No data — that transition does not occur in the current data.'}
              </span>
            ) : isNote ? (
              <span className={`nwz-tres ${testResult.triggered ? 'fire' : 'ok'}`}>
                {(testResult.value ?? 0).toLocaleString()} matching note
                {testResult.value === 1 ? '' : 's'} —{' '}
                {testResult.triggered ? 'would trigger now' : 'below the threshold'}
              </span>
            ) : (
              <span className={`nwz-tres ${testResult.triggered ? 'fire' : 'ok'}`}>
                Measured {fmtMeasured(draft.metric, testResult.value)} —{' '}
                {testResult.triggered ? 'would trigger now' : 'within threshold'}
              </span>
            ))}
          <span className="nwz-testhint">
            Runs the check against the current data without saving.
          </span>
        </div>
      </div>
      {stepsErr && <div className="nwz-note">Couldn't load the process steps: {stepsErr}</div>}
      {err && <div className="nwz-note">{err}</div>}
    </Sheet>
  )
}

/** Live preview label for the editor's name placeholder. */
function ruleSummaryDraft(d: Draft): string {
  if (d.kind === 'note') {
    return noteSummary({
      event: d.noteEvent, minImportance: d.noteMinImportance, scope: d.noteScope,
      threshold: d.noteThreshold, comparator: '>=',
    } as NotificationRule['config'])
  }
  const cmp = NOTIFICATION_COMPARATORS.find((x) => x.op === d.comparator)?.label || d.comparator
  const isTime = NOTIFICATION_TIME_METRICS.has(d.metric)
  const unit = isTime ? UNITS.find((u) => u.key === d.thresholdUnit)?.key || '' : ''
  const subject =
    d.kind === 'journey_duration'
      ? `Journey duration (${d.metric})`
      : `${d.metric} ${d.fromStep} → ${d.toStep}`
  return `${subject} ${cmp} ${d.thresholdValue}${unit}`
}
