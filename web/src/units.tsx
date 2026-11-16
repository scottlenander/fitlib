// The units figures are shown in. Starts from the config's units (GET /api/settings); a
// choice made in the header is remembered in this browser.
import { createContext, useContext, useState, type ReactNode } from 'react'
import { useSettings } from './api/client'
import type { Units } from './format'

const STORAGE_KEY = 'fitlib.units'

type UnitsState = { units: Units; setUnits: (units: Units) => void }

const UnitsContext = createContext<UnitsState | null>(null)

function remembered(): Units | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'imperial' || value === 'metric' ? value : null
  } catch {
    return null // storage blocked: fall back to the config
  }
}

export function UnitsProvider({ children }: { children: ReactNode }) {
  const settings = useSettings()
  const [chosen, setChosen] = useState<Units | null>(remembered)
  const units = chosen ?? settings.data?.units ?? 'imperial'

  function setUnits(value: Units) {
    setChosen(value)
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // Storage blocked: the choice lasts until the page is reloaded.
    }
  }

  return <UnitsContext value={{ units, setUnits }}>{children}</UnitsContext>
}

export function useUnits(): UnitsState {
  const state = useContext(UnitsContext)
  if (!state) throw new Error('useUnits outside UnitsProvider')
  return state
}
