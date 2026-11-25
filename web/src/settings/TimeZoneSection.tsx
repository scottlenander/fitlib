// Settings: the default time zone, from a list or this computer's.
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useSettings, useSetTimeZone, useTimeZones } from '../api/settings'

// The library's default time zone, for rides whose files don't say where they were ridden.
export function TimeZoneSection() {
  const settings = useSettings()
  const zones = useTimeZones()
  return (
    <section aria-labelledby="timezone-heading">
      <h2 id="timezone-heading">Time zone</h2>
      <p className="hint">
        For rides whose files don't say where they were ridden. Garmin files carry their own time
        zone and Zwift files are dated by their names, so this is for renamed files and other
        devices. Rides using it change as soon as you save.
      </p>
      {(settings.isError || zones.isError) && <p role="alert">Couldn't load the time zones.</p>}
      {settings.data && zones.data && (
        // Starts from the saved zone; not keyed on it, so the result stays shown after saving.
        <TimeZoneForm current={settings.data.timezone ?? null} zones={zones.data} />
      )}
    </section>
  )
}

// The time zone this browser reports, e.g. "America/New_York".
function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

function TimeZoneForm({ current, zones }: { current: string | null; zones: string[] }) {
  const save = useSetTimeZone()
  const [chosen, setChosen] = useState(current ?? '')
  const here = browserZone()
  const hereKnown = zones.includes(here)

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(chosen || null)
  }

  const result = save.data
  return (
    <form onSubmit={submit} className="inline-form" data-testid="timezone-form">
      <label>
        Default time zone
        <select value={chosen} onChange={(e) => setChosen(e.target.value)}>
          <option value="">None (show UTC)</option>
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
      </label>
      <button type="button" disabled={!hereKnown} onClick={() => setChosen(here)}>
        Use this computer's time zone ({here.replaceAll('_', ' ')})
      </button>
      <button type="submit" disabled={save.isPending || chosen === (current ?? '')}>
        Save time zone
      </button>
      <div aria-live="polite" className="form-status">
        {save.isError && (
          <p role="alert" data-testid="form-error">
            {save.error.message}
          </p>
        )}
        {result && (
          <p data-testid="form-notice">
            Saved: {result.timezone?.replaceAll('_', ' ') ?? 'none (UTC)'}.{' '}
            {result.updated === 1 ? '1 ride' : `${result.updated} rides`} updated.
            {result.bikes_to_check > 0 && (
              <>
                {' '}
                {result.bikes_to_check} moved to another day, so their default bike may differ: use
                Apply on the <Link to="/bikes">Bikes page</Link>.
              </>
            )}
          </p>
        )}
      </div>
    </form>
  )
}
