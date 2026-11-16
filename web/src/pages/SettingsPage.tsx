import { useState, type FormEvent } from 'react'
import { useAthlete, useDeleteAthlete, useSetAthlete, type AthleteValues } from '../api/client'
import { DisplaySwitches } from '../components/DisplaySwitches'
import { Stats } from '../components/Stats'
import * as f from '../format'
import { useUnits } from '../units'
import { usePageTitle } from '../usePageTitle'

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
      <AthleteSection />
    </>
  )
}

// FTP, weight and max heart rate over time. Each value carries forward from its date until
// a later entry changes it, so rides use what was in effect on their day.
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
        FTP, weight and max heart rate from a date on. A value carries forward until a later entry
        changes it; rides before your first FTP use an estimate.
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
            ]}
          />
        </>
      )}
      {athlete.data && athlete.data.history.length > 0 && (
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
  const [error, setError] = useState('')

  const number = (text: string) => (text.trim() === '' ? null : Number(text))

  function submit(event: FormEvent) {
    event.preventDefault()
    const kg = number(weight)
    const values: AthleteValues = {
      ftp: number(ftp),
      weight_kg: kg === null ? null : Math.round(f.kgFrom(kg, units) * 100) / 100,
      max_hr: number(maxHr),
    }
    if (!from) return setError('Choose the date the values apply from.')
    if (values.ftp === null && values.weight_kg === null && values.max_hr === null)
      return setError('Give at least one of FTP, weight or max heart rate.')
    setError('')
    save.mutate(
      { from, values },
      {
        onSuccess: () => {
          setFtp('')
          setWeight('')
          setMaxHr('')
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
