/** Sampling section of the sidebar — port of SamplingView.swift. */

import { useState } from 'react'
import { useSetting } from '../settings'
import { useStore } from '../store'
import {
  SAMPLE_SETS,
  SAMPLING_METHODS,
  sampleLabel,
  sampleShortLabel,
  type ABDataSource,
  type SampleSet,
  type SamplingMethod,
} from '../types'
import { ConfirmSheet, Divider, Sheet, Spinner } from './ui'

const SLOTS: SampleSet[] = ['SAMPLE_1', 'SAMPLE_2', 'SAMPLE_3']

function methodLabel(method: SamplingMethod | undefined): string | undefined {
  return SAMPLING_METHODS.find((m) => m.id === method)?.label
}

function ChartSourcePicker({
  label,
  labelColor,
  side,
}: {
  label: string
  labelColor: string
  side: 'a' | 'b'
}) {
  const store = useStore()
  const current = side === 'a' ? store.abDataSourceA : store.abDataSourceB

  const describe = (source: ABDataSource): string => {
    if (source.kind === 'simulation') {
      const result = source.slot === 'Sim-A' ? store.simResultA : store.simResultB
      return result
        ? `${source.slot} (${result.totalJourneys.toLocaleString()} sim)`
        : `${source.slot} — not loaded`
    }
    const set = source.sampleSet
    const count =
      set === 'ORIGINAL' ? store.totalJourneyCount : store.sampleCounts[set]
    const method = methodLabel(store.sampleMethods[set])
    if (count == null) return `${sampleShortLabel(set)} — not created`
    return method && set !== 'ORIGINAL'
      ? `${sampleShortLabel(set)} (${count.toLocaleString()} · ${method})`
      : `${sampleShortLabel(set)} (${count.toLocaleString()})`
  }

  const value =
    current.kind === 'simulation'
      ? `sim:${current.slot}`
      : `set:${current.sampleSet}`

  return (
    <div className="row" style={{ gap: 4 }}>
      <span className="t-caption2" style={{ fontWeight: 700, color: labelColor }}>
        {label}
      </span>
      <select
        className="select-input"
        style={{ width: 'auto', fontSize: 11, padding: '3px 6px' }}
        value={value}
        disabled={!store.selectedProject}
        onChange={(e) => {
          const [kind, key] = e.target.value.split(':')
          const source: ABDataSource =
            kind === 'sim'
              ? { kind: 'simulation', slot: key as 'Sim-A' | 'Sim-B' }
              : { kind: 'sampleSet', sampleSet: key as SampleSet }
          void store.setABDataSource(side, source)
        }}
      >
        {SAMPLE_SETS.map((set) => (
          <option
            key={set}
            value={`set:${set}`}
            disabled={set !== 'ORIGINAL' && store.sampleCounts[set] == null}
          >
            {describe({ kind: 'sampleSet', sampleSet: set })}
          </option>
        ))}
        {(['Sim-A', 'Sim-B'] as const).map((slot) => {
          const result = slot === 'Sim-A' ? store.simResultA : store.simResultB
          return (
            <option key={slot} value={`sim:${slot}`} disabled={result == null}>
              {describe({ kind: 'simulation', slot })}
            </option>
          )
        })}
      </select>
    </div>
  )
}

function CreateSampleSheet({
  target,
  onClose,
}: {
  target: SampleSet
  onClose: () => void
}) {
  const store = useStore()
  const [defaultMethod, setDefaultMethod] = useSetting<SamplingMethod>(
    'sampling.defaultMethod',
    'random',
  )
  const [countText, setCountText] = useState('1000')
  const [method, setMethod] = useState<SamplingMethod>(defaultMethod)
  const [creating, setCreating] = useState(false)

  const parsed = Number(countText.trim())
  const valid = Number.isInteger(parsed) && parsed > 0
  const available = store.sampleCounts.ORIGINAL ?? store.totalJourneyCount ?? 0

  return (
    <Sheet
      title={`Create ${sampleLabel(target)}`}
      icon="▤"
      onClose={creating ? () => undefined : onClose}
      footer={
        <>
          <button className="btn" disabled={creating} onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn prominent"
            disabled={!valid || creating}
            onClick={async () => {
              setCreating(true)
              setDefaultMethod(method)
              await store.createSample(target, parsed, method)
              setCreating(false)
              if (!useStore.getState().samplingError) onClose()
            }}
          >
            {creating && <Spinner />} Create Sample
          </button>
        </>
      }
    >
      {available > 0 && (
        <div className="t-footnote fg-secondary">
          {available.toLocaleString()} journeys available
        </div>
      )}

      <div className="row">
        <span className="t-body spacer">Journeys</span>
        <input
          className="text-input"
          style={{ width: 110, textAlign: 'right' }}
          value={countText}
          disabled={creating}
          onChange={(e) => setCountText(e.target.value)}
        />
      </div>

      <Divider />

      <div className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
        Sampling Method
      </div>
      <div className="col" style={{ gap: 4 }}>
        {SAMPLING_METHODS.map((m) => (
          <button
            key={m.id}
            className={`card${method === m.id ? ' selected' : ''}`}
            disabled={creating}
            onClick={() => setMethod(m.id)}
            style={{ alignItems: 'flex-start' }}
          >
            <span aria-hidden style={{ fontSize: 16 }}>
              {m.icon}
            </span>
            <div className="card-body">
              <span className="card-title">{m.label}</span>
              <span className="card-sub">{m.description}</span>
            </div>
            {method === m.id && <span className="fg-accent">✓</span>}
          </button>
        ))}
      </div>

      {store.samplingProgress && (
        <div className="row t-caption fg-secondary">
          <Spinner /> {store.samplingProgress}
        </div>
      )}
      {store.samplingError && (
        <div className="t-caption fg-red">⚠ {store.samplingError}</div>
      )}
    </Sheet>
  )
}

export function SamplingSection() {
  const store = useStore()
  const [createTarget, setCreateTarget] = useState<SampleSet | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<SampleSet | null>(null)

  return (
    <div className="col" style={{ gap: 0 }}>
      <div className="col" style={{ gap: 4, padding: '8px 20px' }}>
        <div className="row t-caption fg-secondary" style={{ gap: 6 }}>
          <span aria-hidden>▤</span> Active data
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <ChartSourcePicker label="A" labelColor="var(--accent)" side="a" />
          <span className="t-caption2 fg-tertiary">·</span>
          <ChartSourcePicker label="B" labelColor="#5E5CE6" side="b" />
        </div>
      </div>

      {store.isSampling && (
        <div className="row t-caption2 fg-secondary" style={{ padding: '6px 20px' }}>
          <Spinner /> {store.samplingProgress ?? 'Working…'}
        </div>
      )}
      {store.samplingError && (
        <div className="t-caption2 fg-red" style={{ padding: '0 20px 6px' }}>
          {store.samplingError}
        </div>
      )}

      <Divider />

      {SLOTS.map((slot) => {
        const count = store.sampleCounts[slot]
        const created = count != null
        const method = store.sampleMethods[slot]
        const isActive =
          (store.abDataSourceA.kind === 'sampleSet' &&
            store.abDataSourceA.sampleSet === slot) ||
          (store.abDataSourceB.kind === 'sampleSet' &&
            store.abDataSourceB.sampleSet === slot)

        return (
          <div key={slot}>
            <div className="row" style={{ padding: '7px 20px', gap: 10 }}>
              <span
                aria-hidden
                className={created ? 'fg-accent' : 'fg-secondary'}
                style={{ fontSize: 12 }}
              >
                {created ? '◉' : '◌'}
              </span>
              <div className="col spacer" style={{ gap: 1, minWidth: 0 }}>
                <span
                  className="t-caption truncate"
                  style={{
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? 'var(--accent)' : 'var(--primary)',
                  }}
                >
                  {sampleShortLabel(slot)}
                </span>
                <span className="t-caption2 fg-secondary truncate">
                  {created
                    ? `${count.toLocaleString()} journeys${
                        method ? ` · ${methodLabel(method)}` : ''
                      }`
                    : 'Not created'}
                </span>
              </div>
              {created ? (
                <button
                  className="icon-btn"
                  style={{ color: 'var(--secondary)', fontSize: 13 }}
                  title={`Delete ${sampleShortLabel(slot)}`}
                  onClick={() => setDeleteTarget(slot)}
                >
                  🗑
                </button>
              ) : (
                <button
                  className="icon-btn"
                  style={{ fontSize: 15 }}
                  title={`Create ${sampleShortLabel(slot)}`}
                  disabled={!store.selectedProject || store.isSampling}
                  onClick={() => setCreateTarget(slot)}
                >
                  ＋
                </button>
              )}
            </div>
            <Divider />
          </div>
        )
      })}

      {createTarget && (
        <CreateSampleSheet target={createTarget} onClose={() => setCreateTarget(null)} />
      )}
      {deleteTarget && (
        <ConfirmSheet
          title={`Delete ${sampleLabel(deleteTarget)}?`}
          message={
            store.sampleCounts[deleteTarget] != null
              ? `This removes ${store.sampleCounts[deleteTarget].toLocaleString()} sample journey rows from the database. Original data is not affected.`
              : 'This removes all sample journey rows from the database. Original data is not affected.'
          }
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => {
            void store.deleteSample(deleteTarget)
            setDeleteTarget(null)
          }}
        />
      )}
    </div>
  )
}
