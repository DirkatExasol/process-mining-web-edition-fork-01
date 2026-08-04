/** The theme selector (System / Light / Dark) shared by the app and integration
 *  sidebars. Persists to the per-user `app.theme` setting. An optional collapse
 *  button (app sidebar only) hides the panel. */

import { useSetting } from '../settings'

const THEMES = [
  { value: 'system', icon: '◐', label: 'System' },
  { value: 'light', icon: '☀', label: 'Light' },
  { value: 'dark', icon: '☾', label: 'Dark' },
]

export function ThemeBar({ onCollapse }: { onCollapse?: () => void }) {
  const [theme, setTheme] = useSetting<string>('app.theme')
  return (
    <div className="theme-bar">
      <span aria-hidden>🎨</span>
      <span className="t-caption fg-secondary">Theme</span>
      <span className="spacer" />
      {THEMES.map((option) => (
        <button
          key={option.value}
          className={`theme-btn${theme === option.value ? ' active' : ''}`}
          title={option.label}
          aria-label={option.label}
          onClick={() => setTheme(option.value)}
        >
          {option.icon}
        </button>
      ))}
      {onCollapse && (
        <button
          className="theme-btn"
          title="Hide sidebar"
          aria-label="Hide sidebar"
          onClick={onCollapse}
        >
          ⇤
        </button>
      )}
    </div>
  )
}
