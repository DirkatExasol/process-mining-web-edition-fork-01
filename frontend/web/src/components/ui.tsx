/** Small SwiftUI-equivalent building blocks reused across the app. */

import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export function Chevron({ open }: { open: boolean }) {
  return <span className={`chevron${open ? ' open' : ''}`}>›</span>
}

export function Divider() {
  return <hr className="divider" />
}

export function Spinner({ large = false }: { large?: boolean }) {
  return <span className={`spinner${large ? ' large' : ''}`} />
}

/** `ContentUnavailableView`. */
export function Unavailable({
  glyph,
  title,
  description,
  action,
}: {
  glyph: string
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="unavailable">
      <div className="glyph">{glyph}</div>
      <div className="u-title">{title}</div>
      {description && <div className="u-desc">{description}</div>}
      {action}
    </div>
  )
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="center-fill">
      <Spinner large />
      <span>{label}</span>
    </div>
  )
}

/** SwiftUI `Toggle` with `.switch` style. */
export function Switch({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className={`switch${checked ? ' on' : ''}`}
      onClick={() => onChange(!checked)}
    />
  )
}

export function ToggleRow({
  icon,
  label,
  checked,
  onChange,
  disabled,
}: {
  icon: string
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="toggle-row">
      <span aria-hidden>{icon}</span>
      <span className="toggle-label">{label}</span>
      <Switch checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  disabled = false,
}: {
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  disabled?: boolean
}) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button
          key={option.value}
          className={option.value === value ? 'active' : ''}
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/** Two-thumb range slider — ports `RangeSliderView`. */
export function RangeSlider({
  min,
  max,
  low,
  high,
  onChange,
  format = (v: number) => String(v),
  disabled = false,
}: {
  min: number
  max: number
  low: number
  high: number
  onChange: (low: number, high: number) => void
  format?: (value: number) => string
  disabled?: boolean
}) {
  const span = Math.max(1, max - min)
  const clampedLow = Math.max(min, Math.min(low, max))
  const clampedHigh = Math.max(min, Math.min(high, max))
  const lowPct = ((clampedLow - min) / span) * 100
  const highPct = ((clampedHigh - min) / span) * 100

  return (
    <div className="range-slider">
      <div className="range-values">
        <span>{format(clampedLow)}</span>
        <span>{format(clampedHigh)}</span>
      </div>
      <div className="range-track">
        <div className="rail" />
        <div
          className="fill"
          style={{
            left: `calc(11px + ${lowPct}% - ${(lowPct / 100) * 22}px)`,
            width: `calc(${highPct - lowPct}% - ${((highPct - lowPct) / 100) * 22}px)`,
          }}
        />
        <input
          type="range"
          min={min}
          max={max}
          value={clampedLow}
          disabled={disabled}
          onChange={(e) => {
            const next = Number(e.target.value)
            onChange(Math.min(next, clampedHigh), clampedHigh)
          }}
          aria-label="Lower bound"
        />
        <input
          type="range"
          min={min}
          max={max}
          value={clampedHigh}
          disabled={disabled}
          onChange={(e) => {
            const next = Number(e.target.value)
            onChange(clampedLow, Math.max(next, clampedLow))
          }}
          aria-label="Upper bound"
        />
      </div>
    </div>
  )
}

/** Text field with a filtered suggestion list — ports `MetaFilterFieldView`. */
export function AutocompleteField({
  label,
  value,
  suggestions,
  placeholder = 'Filter',
  onChange,
  onSubmit,
  maxSuggestions = 7,
}: {
  label?: string
  value: string
  suggestions: string[]
  placeholder?: string
  onChange: (value: string) => void
  onSubmit?: () => void
  maxSuggestions?: number
}) {
  const [focused, setFocused] = useState(false)
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const trimmed = value.trim().toLowerCase()
  const matches = trimmed
    ? suggestions
        .filter((s) => s.toLowerCase().includes(trimmed))
        .slice(0, maxSuggestions)
    : []

  useEffect(() => () => {
    if (blurTimer.current) clearTimeout(blurTimer.current)
  }, [])

  return (
    <div className="field" style={{ position: 'relative', zIndex: focused ? 10 : 0 }}>
      {label && <span className="field-label">{label}</span>}
      <div className="row" style={{ gap: 6 }}>
        <input
          className="text-input"
          value={value}
          placeholder={placeholder}
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            // Delay so a suggestion click still registers.
            blurTimer.current = setTimeout(() => setFocused(false), 180)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              setFocused(false)
              onSubmit?.()
            }
          }}
        />
        {value && (
          <button
            className="icon-btn"
            style={{ color: 'var(--secondary)', width: 22, height: 22 }}
            onClick={() => onChange('')}
            title="Clear"
          >
            ⊗
          </button>
        )}
      </div>
      {focused && matches.length > 0 && (
        <div className="suggestions" style={{ position: 'absolute', top: '100%', left: 0, right: 0 }}>
          {matches.map((match) => (
            <button
              key={match}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange(match)
                setFocused(false)
                onSubmit?.()
              }}
            >
              {match}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Modal sheet. */
export function Sheet({
  title,
  icon,
  wide = false,
  onClose,
  footer,
  children,
}: {
  title: string
  icon?: string
  wide?: boolean
  onClose: () => void
  footer?: ReactNode
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="scrim" onClick={onClose}>
      <div
        className={`sheet${wide ? ' wide' : ''}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="sheet-head">
          {icon && <span aria-hidden>{icon}</span>}
          <span className="sheet-title">{title}</span>
          <button className="icon-btn" onClick={onClose} title="Close">
            ✕
          </button>
        </div>
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </div>
  )
}

/** Text-input prompt, replacing SwiftUI's `.alert` with a TextField. */
export function PromptSheet({
  title,
  message,
  initialValue = '',
  confirmLabel = 'Save',
  onConfirm,
  onCancel,
}: {
  title: string
  message?: string
  initialValue?: string
  confirmLabel?: string
  onConfirm: (value: string) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(initialValue)
  const inputId = useId()

  return (
    <Sheet
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button className="btn" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn prominent" onClick={() => onConfirm(value)}>
            {confirmLabel}
          </button>
        </>
      }
    >
      {message && <div className="t-footnote fg-secondary">{message}</div>}
      <div className="field">
        <label className="field-label" htmlFor={inputId}>
          Name
        </label>
        <input
          id={inputId}
          className="text-input"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onConfirm(value)
          }}
        />
      </div>
    </Sheet>
  )
}

export function ConfirmSheet({
  title,
  message,
  confirmLabel = 'Delete',
  destructive = true,
  onConfirm,
  onCancel,
}: {
  title: string
  message?: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="scrim" onClick={onCancel}>
      <div className="alert-box" onClick={(e) => e.stopPropagation()} role="alertdialog">
        <div className="a-body">
          <div className="a-title">{title}</div>
          {message && <div className="a-message">{message}</div>}
        </div>
        <div className="a-actions">
          <button onClick={onCancel}>Cancel</button>
          <button
            className="emphasis"
            style={destructive ? { color: 'var(--red)' } : undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
