/** Per-step colour / score / shape / group editor — port of StepEditorView.swift. */

import { useEffect, useState } from 'react'
import { namedColor } from '../graph/colors'
import { useStore } from '../store'
import { Divider, Spinner } from './ui'

const SHAPES = [
  { id: 'stadium', label: 'Stadium', glyph: '▭' },
  { id: 'round', label: 'Rounded', glyph: '▢' },
  { id: 'hex', label: 'Hexagon', glyph: '⬡' },
  { id: 'circle', label: 'Circle', glyph: '◯' },
] as const

export function StepEditor() {
  const store = useStore()
  const [selectedStep, setSelectedStep] = useState('')
  const [bgColor, setBgColor] = useState('#007AFF')
  const [fgColor, setFgColor] = useState('#FFFFFF')
  const [score, setScore] = useState(0)
  const [hasScore, setHasScore] = useState(false)
  const [shape, setShape] = useState<string>('stadium')
  const [belongsTo, setBelongsTo] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)

  // Reset when a different project is opened.
  useEffect(() => {
    setSelectedStep('')
  }, [store.selectedProject?.projectId])

  // Load the selected step's current values.
  useEffect(() => {
    if (!selectedStep) return
    const info = store.allStepInfos[selectedStep]
    if (!info) return
    setBgColor(namedColor(info.bgColor))
    setFgColor(namedColor(info.fgColor))
    setHasScore(info.score != null)
    setScore(info.score ?? 0)
    setShape(info.shape || 'stadium')
    setBelongsTo(info.belongsTo ?? '')
    setDescription(info.description === selectedStep ? '' : (info.description ?? ''))
    // Deliberately keyed on the step name only — editing fields must not be
    // clobbered by unrelated store updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStep])

  const save = async () => {
    if (!selectedStep) return
    setSaving(true)
    await store.updateStep(selectedStep, {
      // The database stores 6-digit hex without the leading '#'.
      bgColor: bgColor.replace('#', '').toUpperCase(),
      fgColor: fgColor.replace('#', '').toUpperCase(),
      score: hasScore ? score : null,
      shape,
      belongsTo: belongsTo.trim() || null,
      description: description.trim() || null,
    })
    setSaving(false)
  }

  const groups = Array.from(
    new Set(
      Object.values(store.allStepInfos)
        .map((s) => s.belongsTo)
        .filter((g): g is string => !!g),
    ),
  ).sort()

  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="row">
        <span className="t-caption fg-secondary" style={{ width: 52 }}>
          Step
        </span>
        <select
          className="select-input"
          value={selectedStep}
          disabled={store.allSteps.length === 0}
          onChange={(e) => setSelectedStep(e.target.value)}
        >
          <option value="">— Select a step —</option>
          {store.allSteps.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {selectedStep && (
        <>
          <Divider />

          <div className="row">
            <span className="t-caption fg-secondary" style={{ width: 52 }}>
              Colors
            </span>
            <div className="row" style={{ gap: 14 }}>
              <label className="col" style={{ gap: 3, alignItems: 'center' }}>
                <input
                  type="color"
                  value={bgColor}
                  onChange={(e) => setBgColor(e.target.value)}
                  style={{ width: 34, height: 28, border: 'none', background: 'none' }}
                />
                <span className="t-caption2 fg-secondary">BG</span>
              </label>
              <label className="col" style={{ gap: 3, alignItems: 'center' }}>
                <input
                  type="color"
                  value={fgColor}
                  onChange={(e) => setFgColor(e.target.value)}
                  style={{ width: 34, height: 28, border: 'none', background: 'none' }}
                />
                <span className="t-caption2 fg-secondary">FG</span>
              </label>
              <div
                className="row"
                style={{
                  background: bgColor,
                  color: fgColor,
                  padding: '4px 12px',
                  borderRadius: 999,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {selectedStep}
              </div>
            </div>
          </div>

          <div className="row">
            <span className="t-caption fg-secondary" style={{ width: 52 }}>
              Score
            </span>
            <label className="row t-caption" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={hasScore}
                onChange={(e) => setHasScore(e.target.checked)}
              />
              set
            </label>
            <input
              className="text-input"
              type="number"
              min={-999}
              max={999}
              value={score}
              disabled={!hasScore}
              onChange={(e) => setScore(Number(e.target.value))}
              style={{ width: 90 }}
            />
          </div>

          <div className="row" style={{ alignItems: 'flex-start' }}>
            <span className="t-caption fg-secondary" style={{ width: 52, paddingTop: 6 }}>
              Shape
            </span>
            <div className="row wrap" style={{ gap: 6 }}>
              {SHAPES.map((s) => (
                <button
                  key={s.id}
                  className={`chip${shape === s.id ? ' active' : ''}`}
                  onClick={() => setShape(s.id)}
                >
                  <span aria-hidden>{s.glyph}</span> {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="row">
            <span className="t-caption fg-secondary" style={{ width: 52 }}>
              Group
            </span>
            <input
              className="text-input"
              value={belongsTo}
              list="step-groups"
              placeholder="BELONGS_TO"
              onChange={(e) => setBelongsTo(e.target.value)}
            />
            <datalist id="step-groups">
              {groups.map((g) => (
                <option key={g} value={g} />
              ))}
            </datalist>
          </div>

          <div className="row" style={{ alignItems: 'flex-start' }}>
            <span className="t-caption fg-secondary" style={{ width: 52, paddingTop: 6 }}>
              Note
            </span>
            <textarea
              className="text-input"
              style={{ minHeight: 56 }}
              value={description}
              placeholder="Shown under the step name on the map"
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <Divider />

          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            {store.errorMessage && (
              <span className="t-caption2 fg-red truncate spacer">
                {store.errorMessage}
              </span>
            )}
            <button className="btn prominent small" disabled={saving} onClick={save}>
              {saving && <Spinner />} Save Step
            </button>
          </div>
        </>
      )}
    </div>
  )
}
