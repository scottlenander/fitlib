import { useUnits } from '../units'

// Imperial or metric, for every figure on every page.
export function UnitsToggle() {
  const { units, setUnits } = useUnits()
  return (
    <fieldset className="units-toggle">
      <legend>Units</legend>
      {(['imperial', 'metric'] as const).map((value) => (
        <label key={value}>
          <input
            type="radio"
            name="units"
            value={value}
            checked={units === value}
            onChange={() => setUnits(value)}
          />
          {value === 'imperial' ? 'Imperial' : 'Metric'}
        </label>
      ))}
    </fieldset>
  )
}
