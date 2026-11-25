// The trends page's range: presets, custom dates, and week or month.
import { PRESETS, type DateRange, type TrendsState } from './trendsQuery'

export type ControlsProps = {
  state: TrendsState
  range: DateRange
  onChange: (changes: Partial<TrendsState>) => void
}

export function Controls({ state, range, onChange }: ControlsProps) {
  return (
    <fieldset className="filters trend-controls">
      <legend>Range</legend>
      <div role="radiogroup" aria-label="Range" className="radios">
        {[...PRESETS, { id: 'custom', label: 'Custom' } as const].map((preset) => (
          <label key={preset.id}>
            <input
              type="radio"
              name="range"
              value={preset.id}
              checked={state.range === preset.id}
              onChange={() =>
                onChange(
                  preset.id === 'custom'
                    ? { range: 'custom', since: range.since, until: range.until }
                    : { range: preset.id, since: '', until: '' },
                )
              }
            />
            {preset.label}
          </label>
        ))}
      </div>
      <label>
        From
        <input
          type="date"
          value={range.since}
          required
          onChange={(e) =>
            e.target.value &&
            onChange({ range: 'custom', since: e.target.value, until: range.until })
          }
        />
      </label>
      <label>
        To
        <input
          type="date"
          value={range.until}
          required
          onChange={(e) =>
            e.target.value &&
            onChange({ range: 'custom', since: range.since, until: e.target.value })
          }
        />
      </label>
      <label>
        Group by
        <select
          value={state.period}
          onChange={(e) => onChange({ period: e.target.value as TrendsState['period'] })}
        >
          <option value="week">Week</option>
          <option value="month">Month</option>
        </select>
      </label>
    </fieldset>
  )
}
