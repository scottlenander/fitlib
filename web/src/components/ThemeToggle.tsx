import { useId } from 'react'
import { useTheme } from '../theme'

// Light or dark, as one button showing the mode in use: a sun in light mode, a moon in dark
// mode. Its hint (on hover or keyboard focus) and its name say which mode that is; clicking
// switches to the other mode, and the icon with it.
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const dark = theme === 'dark'
  const label = dark ? 'Dark mode' : 'Light mode'
  const hintId = useId()
  return (
    <button
      type="button"
      aria-label={label}
      aria-describedby={hintId}
      className="icon-button theme-toggle"
      onClick={() => setTheme(dark ? 'light' : 'dark')}
    >
      {dark ? <MoonIcon /> : <SunIcon />}
      <span className="tooltip" aria-hidden="true">
        {label}
      </span>
      <span id={hintId} className="visually-hidden">
        Switch to {dark ? 'light' : 'dark'} mode
      </span>
    </button>
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
