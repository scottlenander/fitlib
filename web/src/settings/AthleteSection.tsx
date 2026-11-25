// The athlete: dated FTP, weight and heart rates, today's values, and year of birth.
import { useState, type FormEvent } from 'react'
import { useAthlete, useDeleteAthlete, useSetAthlete, useSetBirthYear } from '../api/athlete'
import { Stats } from '../shared/Stats'
import * as f from '../shared/format'
import { THRESHOLD_NOTES } from '../shared/tss'
import { useUnits } from '../shared/units'
import { athleteValues } from './athleteForm'

// FTP, weight, max and threshold heart rate over time. Each value carries forward from its
// date until a later entry changes it, so rides use what was in effect on their day. The year
// of birth estimates threshold heart rate where none is set.
export function AthleteSection() {
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

  function submit(event: FormEvent) {
    event.preventDefault()
    const result = athleteValues({ from, ftp, weight, maxHr, thresholdHr }, units)
    if ('error' in result) return setError(result.error)
    setError('')
    save.mutate(result, {
      onSuccess: () => {
        setFtp('')
        setWeight('')
        setMaxHr('')
        setThresholdHr('')
      },
    })
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
