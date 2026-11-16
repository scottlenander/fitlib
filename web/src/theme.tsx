// Light or dark. Follows the system until the viewer flips the switch; the choice is then
// remembered in this browser. index.html applies a remembered choice before the first paint.
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark'

export const THEME_KEY = 'fitlib.theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

type ThemeState = { theme: Theme; setTheme: (theme: Theme) => void }

const ThemeContext = createContext<ThemeState | null>(null)

// A remembered choice, if there is one and storage can be read.
export function rememberedTheme(read: () => string | null): Theme | null {
  try {
    const value = read()
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

// The theme in effect: the viewer's choice, else the system's.
export function resolveTheme(chosen: Theme | null, systemDark: boolean): Theme {
  return chosen ?? (systemDark ? 'dark' : 'light')
}

function systemPrefersDark(): boolean {
  return typeof matchMedia === 'function' && matchMedia(DARK_QUERY).matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [chosen, setChosen] = useState<Theme | null>(() =>
    rememberedTheme(() => localStorage.getItem(THEME_KEY)),
  )
  const [systemDark, setSystemDark] = useState(systemPrefersDark)

  useEffect(() => {
    if (typeof matchMedia !== 'function') return
    const query = matchMedia(DARK_QUERY)
    const onChange = () => setSystemDark(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    if (chosen) document.documentElement.dataset.theme = chosen
    else delete document.documentElement.dataset.theme
  }, [chosen])

  function setTheme(theme: Theme) {
    setChosen(theme)
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // Storage blocked: the choice lasts until the page is reloaded.
    }
  }

  return (
    <ThemeContext value={{ theme: resolveTheme(chosen, systemDark), setTheme }}>
      {children}
    </ThemeContext>
  )
}

export function useTheme(): ThemeState {
  const state = useContext(ThemeContext)
  if (!state) throw new Error('useTheme outside ThemeProvider')
  return state
}
