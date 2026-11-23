import { useStreetMap } from '../streetMap'
import { useUnits } from '../units'
import { Switch } from './Switch'
import { ThemeToggle } from './ThemeToggle'

// The display settings on the Settings page: light or dark (also in the header), units, and
// the street map under outdoor routes.
export function DisplaySwitches() {
  const { units, setUnits } = useUnits()
  const [streetMap, setStreetMap] = useStreetMap()
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
      <Switch label="Street map under outdoor routes" checked={streetMap} onChange={setStreetMap} />
      <p className="hint" id="street-map-hint">
        Loads map images from OpenStreetMap, which then sees the areas you look at. Off, routes are
        drawn on a plain background and nothing leaves this computer. Zwift routes are always on a
        plain background.
      </p>
    </>
  )
}
