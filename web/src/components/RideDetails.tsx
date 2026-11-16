import { useState, type FormEvent } from 'react'
import { useBikes, useUpdateMeta, type MetaPatch, type RideDetail } from '../api/client'
import { parseTags } from '../tags'
import { Stats, type Stat } from './Stats'

// What the rider added to a ride (bike, effort, tags, name, notes), and a form to change it.
export function RideDetails({ ride }: { ride: RideDetail }) {
  const [editing, setEditing] = useState(false)
  const [saved, setSaved] = useState(false)
  const meta = ride.meta

  const details: Stat[] = [
    ...(meta.bike
      ? [
          {
            label: 'Bike',
            value: meta.bike.name,
            note: meta.bike_from_default ? '(default)' : undefined,
          },
        ]
      : []),
    ...(meta.rpe !== null ? [{ label: 'Effort', value: `${meta.rpe}/10` }] : []),
    ...(meta.tags.length ? [{ label: 'Tags', value: meta.tags.join(', ') }] : []),
  ]

  return (
    <section aria-labelledby="details-heading">
      <h2 id="details-heading">Details</h2>
      {editing ? (
        <EditDetails
          ride={ride}
          onDone={(didSave) => {
            setEditing(false)
            setSaved(didSave)
          }}
        />
      ) : (
        <>
          {details.length > 0 && <Stats stats={details} testId="detail-stats" />}
          {meta.notes && (
            <p className="notes" data-testid="ride-notes">
              {meta.notes}
            </p>
          )}
          {details.length === 0 && !meta.notes && (
            <p className="hint">No bike, effort, tags or notes yet.</p>
          )}
          <div className="button-row">
            <button
              type="button"
              onClick={() => {
                setEditing(true)
                setSaved(false)
              }}
            >
              Edit details
            </button>
          </div>
          <div aria-live="polite">{saved && <p data-testid="form-notice">Saved.</p>}</div>
        </>
      )}
    </section>
  )
}

function EditDetails({ ride, onDone }: { ride: RideDetail; onDone: (saved: boolean) => void }) {
  const meta = ride.meta
  const bikes = useBikes()
  const update = useUpdateMeta(ride.id)
  const [name, setName] = useState(meta.name ?? '')
  const [notes, setNotes] = useState(meta.notes ?? '')
  const [rpe, setRpe] = useState(meta.rpe === null ? '' : String(meta.rpe))
  const [bikeId, setBikeId] = useState(meta.bike?.id ?? '')
  const [tags, setTags] = useState(meta.tags.join(', '))

  // Active bikes, plus the ride's own bike even if it has been retired since.
  const choices = (bikes.data ?? []).filter((b) => !b.retired || b.id === meta.bike?.id)

  function submit(event: FormEvent) {
    event.preventDefault()
    const patch: MetaPatch = {
      name,
      notes,
      rpe: rpe ? Number(rpe) : null,
      tags: parseTags(tags),
    }
    // Sending a bike marks it as chosen by hand, so only send it when it changed.
    if (bikeId !== (meta.bike?.id ?? '')) patch.bike_id = bikeId || null
    update.mutate(patch, { onSuccess: () => onDone(true) })
  }

  return (
    <form onSubmit={submit} className="edit-form" aria-label="Edit details">
      <label>
        Name
        <input value={name} placeholder={ride.name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Effort
        <select value={rpe} onChange={(e) => setRpe(e.target.value)}>
          <option value="">Not set</option>
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              {n}/10
            </option>
          ))}
        </select>
      </label>
      <label>
        Bike
        <select value={bikeId} onChange={(e) => setBikeId(e.target.value)}>
          <option value="">No bike</option>
          {choices.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tags
        <input
          value={tags}
          aria-describedby="tags-hint"
          onChange={(e) => setTags(e.target.value)}
        />
        <span id="tags-hint" className="hint">
          Separate tags with commas.
        </span>
      </label>
      <label className="wide-field">
        Notes
        <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="button-row">
        <button type="submit" disabled={update.isPending}>
          Save
        </button>
        <button type="button" onClick={() => onDone(false)}>
          Cancel
        </button>
      </div>
      <div aria-live="polite">
        {update.isError && (
          <p role="alert" data-testid="form-error">
            {update.error.message}
          </p>
        )}
      </div>
    </form>
  )
}
