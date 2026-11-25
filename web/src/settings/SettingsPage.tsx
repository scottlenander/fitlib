import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  useAthlete,
  useDeleteAthlete,
  useSetAthlete,
  useSetBirthYear,
  type AthleteValues,
} from '../api/athlete'
import { useSettings, useSetTimeZone, useTimeZones } from '../api/settings'
import { DisplaySwitches } from './DisplaySwitches'
import { Stats } from '../shared/Stats'
import { WatchedFolders } from './WatchedFolders'
import * as f from '../shared/format'
import { THRESHOLD_NOTES } from '../shared/tss'
import { useUnits } from '../shared/units'
import { usePageTitle } from '../app/usePageTitle'

export function SettingsPage() {
  usePageTitle('Settings')
  return (
    <>
      <h1>Settings</h1>
      <section aria-labelledby="display-heading">
        <h2 id="display-heading">Display</h2>
        <div className="switches" data-testid="display-settings">
          <DisplaySwitches />
        </div>
        <p className="hint">
          Remembered in this browser. The theme is also in the header, and follows your system until
          you choose one.
        </p>
      </section>
      <TimeZoneSection />
      <WatchedFolders />
      <AthleteSection />
    </>
  )
}

// The library's default time zone, for rides whose files don't say where they were ridden.
function TimeZoneSection() {
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

// FTP, weight, max and threshold heart rate over time. Each value carries forward from its
// date until a later entry changes it, so rides use what was in effect on their day. The year
// of birth estimates threshold heart rate where none is set.
function AthleteSection() {
  const athlete = useAthlete()
  const remove = useDeleteAthlete()
  const { units } = useUnits()

  function confirmRemove(from: string) {
    if (window.confirm(`Remove the athlete values from ${from}?`)) remove.mutate(from)
  }

  const today = athlete.data?.today
  return (
    <section aria-labelledby="athlete-heading">
      <h2 id="athlete-heading">Athlete</h2>
      <p className="hint">
        FTP, weight, max and threshold heart rate from a date on. A value carries forward until a
        later entry changes it; rides before your first FTP use an estimate. Threshold heart rate
        gives rides without power a TSS from heart rate.
      </p>
      {athlete.isError && <p role="alert">Couldn't load the athlete history.</p>}
      {today && (
        <>
          <h3>Today</h3>
          <Stats
            testId="athlete-today"
            stats={[
              { label: 'FTP', value: f.watts(today.ftp) },
              { label: 'Weight', value: f.weight(today.weight_kg, units) },
              { label: 'Max heart rate', value: f.bpm(today.max_hr) },
              {
                label: 'Threshold heart rate',
                value: f.bpm(athlete.data?.threshold_hr_today ?? null),
                note: THRESHOLD_NOTES[athlete.data?.threshold_hr_source_today ?? 'set'],
              },
            ]}
          />
        </>
      )}
      {athlete.data && <BirthYearForm saved={athlete.data.birth_year} />}
      {athlete.data && athlete.data.history.length > 0 && (
        // Scrolls sideways on a phone; its Remove buttons can be reached with Tab.
        <div className="table-scroll">
          <table>
            <caption>Athlete history</caption>
            <thead>
              <tr>
                <th scope="col">From</th>
                <th scope="col" className="num">
                  FTP
                </th>
                <th scope="col" className="num">
                  Weight
                </th>
                <th scope="col" className="num">
                  Max HR
                </th>
                <th scope="col" className="num">
                  Threshold HR
                </th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {athlete.data.history.map((entry) => (
                <tr key={entry.effective_from}>
                  <th scope="row">{entry.effective_from}</th>
                  <td className="num">{f.watts(entry.ftp)}</td>
                  <td className="num">{f.weight(entry.weight_kg, units)}</td>
                  <td className="num">{f.bpm(entry.max_hr)}</td>
                  <td className="num">{f.bpm(entry.threshold_hr ?? null)}</td>
                  <td>
                    <button
                      type="button"
                      aria-label={`Remove values from ${entry.effective_from}`}
                      onClick={() => confirmRemove(entry.effective_from)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {remove.isError && <p role="alert">{remove.error.message}</p>}
      <AthleteForm />
    </section>
  )
}

function AthleteForm() {
  const save = useSetAthlete()
  const { units } = useUnits()
  const [from, setFrom] = useState('')
  const [ftp, setFtp] = useState('')
  const [weight, setWeight] = useState('')
  const [maxHr, setMaxHr] = useState('')
  const [thresholdHr, setThresholdHr] = useState('')
  const [error, setError] = useState('')

  const number = (text: string) => (text.trim() === '' ? null : Number(text))

  function submit(event: FormEvent) {
    event.preventDefault()
    const kg = number(weight)
    const values: AthleteValues = {
      ftp: number(ftp),
      weight_kg: kg === null ? null : Math.round(f.kgFrom(kg, units) * 100) / 100,
      max_hr: number(maxHr),
      threshold_hr: number(thresholdHr),
    }
    if (!from) return setError('Choose the date the values apply from.')
    if (Object.values(values).every((v) => v === null))
      return setError('Give at least one of FTP, weight, max or threshold heart rate.')
    setError('')
    save.mutate(
      { from, values },
      {
        onSuccess: () => {
          setFtp('')
          setWeight('')
          setMaxHr('')
          setThresholdHr('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="inline-form" data-testid="athlete-form" noValidate>
      <h3>Add or replace values from a date</h3>
      <label>
        From
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      </label>
      <label>
        FTP (W)
        <input type="number" min={1} value={ftp} onChange={(e) => setFtp(e.target.value)} />
      </label>
      <label>
        Weight ({f.weightUnit(units)})
        <input
          type="number"
          min={1}
          step="0.1"
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
        />
      </label>
      <label>
        Max heart rate (bpm)
        <input type="number" min={1} value={maxHr} onChange={(e) => setMaxHr(e.target.value)} />
      </label>
      <label>
        Threshold heart rate (bpm)
        <input
          type="number"
          min={1}
          value={thresholdHr}
          onChange={(e) => setThresholdHr(e.target.value)}
        />
      </label>
      <button type="submit" disabled={save.isPending}>
        Save values
      </button>
      <div aria-live="polite" className="form-status">
        {(error || save.isError) && (
          <p role="alert" data-testid="form-error">
            {error || save.error?.message}
          </p>
        )}
        {save.isSuccess && !error && (
          <p data-testid="form-notice">Saved values from {save.data.effective_from}.</p>
        )}
      </div>
    </form>
  )
}

// The year of birth: threshold heart rate is estimated from age on days with none set.
function BirthYearForm({ saved }: { saved: number | null }) {
  const save = useSetBirthYear()
  const [year, setYear] = useState(saved === null ? '' : String(saved))

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(year.trim() === '' ? null : Number(year))
  }

  const result = save.data
  return (
    <form onSubmit={submit} className="inline-form" data-testid="birth-year-form" noValidate>
      <h3>Year of birth</h3>
      <p className="hint">
        Without a threshold heart rate set, it is worked out from your recent rides with power and
        heart rate, or else estimated from your age: 90% of 208 − 0.7 × age.
      </p>
      <label>
        Year of birth
        <input
          type="number"
          min={1900}
          inputMode="numeric"
          value={year}
          onChange={(e) => setYear(e.target.value)}
        />
      </label>
      <button type="submit" disabled={save.isPending}>
        Save year of birth
      </button>
      <div aria-live="polite" className="form-status">
        {save.isError && (
          <p role="alert" data-testid="form-error">
            {save.error.message}
          </p>
        )}
        {result && (
          <p data-testid="form-notice">
            {result.birth_year === null
              ? 'Year of birth cleared.'
              : `Saved: born ${result.birth_year}. Estimated threshold heart rate today: ${f.bpm(result.estimated_threshold_hr)}.`}
          </p>
        )}
      </div>
    </form>
  )
}
