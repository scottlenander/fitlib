import { useTheme, type Theme } from '../theme'

// Light or dark, as a sun and a moon. The pressed one is the mode in use. Each shows its
// name as a hint on hover or keyboard focus; the same name is what screen readers announce.
const MODES: { theme: Theme; label: string; icon: React.JSX.Element }[] = [
  { theme: 'light', label: 'Light mode', icon: <SunIcon /> },
  { theme: 'dark', label: 'Dark mode', icon: <MoonIcon /> },
]

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <div role="group" aria-label="Theme" className="theme-toggle">
      {MODES.map((mode) => (
        <button
          key={mode.theme}
          type="button"
          aria-label={mode.label}
          aria-pressed={theme === mode.theme}
          className="icon-button"
          onClick={() => setTheme(mode.theme)}
        >
          {mode.icon}
          <span className="tooltip" aria-hidden="true">
            {mode.label}
          </span>
        </button>
      ))}
    </div>
  )
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="4.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <g stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22" />
        <path d="M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
      </g>
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  )
}
