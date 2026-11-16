import { useUnits } from '../units'
import { Switch } from './Switch'
import { ThemeToggle } from './ThemeToggle'

// The display settings on the Settings page: light or dark (also in the header), and units.
export function DisplaySwitches() {
  const { units, setUnits } = useUnits()
  return (
    <>
      <div className="setting">
        <span>Theme</span>
        <ThemeToggle />
      </div>
      <Switch
        label="Metric units"
        checked={units === 'metric'}
        onChange={(on) => setUnits(on ? 'metric' : 'imperial')}
      />
    </>
  )
}
