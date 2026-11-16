import { useTheme } from '../theme'
import { useUnits } from '../units'
import { Switch } from './Switch'

// Dark mode and metric units, in the header and on the Settings page; both stay in sync.
export function DisplaySwitches() {
  const { theme, setTheme } = useTheme()
  const { units, setUnits } = useUnits()
  return (
    <>
      <Switch
        label="Dark mode"
        checked={theme === 'dark'}
        onChange={(on) => setTheme(on ? 'dark' : 'light')}
      />
      <Switch
        label="Metric units"
        checked={units === 'metric'}
        onChange={(on) => setUnits(on ? 'metric' : 'imperial')}
      />
    </>
  )
}
