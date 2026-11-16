import { useState, type FormEvent } from 'react'
import {
  useAddBike,
  useBackfill,
  useBikes,
  useDefaults,
  useDeleteDefault,
  useSetDefault,
  useUpdateBike,
  type BikeKind,
  type BikeSlot,
  type BikeWithTotals,
} from '../api/client'
import { KINDS, KIND_LABELS, SLOTS, SLOT_LABELS } from '../bikes'
import * as f from '../format'
import { useUnits } from '../units'
import { usePageTitle } from '../usePageTitle'

export function BikesPage() {
  usePageTitle('Bikes')
  return (
    <>
      <h1>Bikes</h1>
      <BikeList />
      <AddBike />
      <Defaults />
      <Backfill />
    </>
  )
}

function BikeList() {
  const bikes = useBikes()
  const [showRetired, setShowRetired] = useState(false)
  const shown = bikes.data?.filter((b) => showRetired || !b.retired) ?? []
  const retired = bikes.data?.filter((b) => b.retired).length ?? 0

  return (
    <section aria-labelledby="bikes-heading">
      <h2 id="bikes-heading">Your bikes</h2>
      {bikes.isError && <p role="alert">Couldn't load bikes.</p>}
      {bikes.data?.length === 0 && <p>No bikes yet. Add one below.</p>}
      {retired > 0 && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showRetired}
            onChange={(e) => setShowRetired(e.target.checked)}
          />
          Show retired bikes ({retired})
        </label>
      )}
      {shown.length > 0 && (
        <div className="table-scroll">
          <table className="wide">
            <caption className="visually-hidden">Bikes</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Kind</th>
                <th scope="col" className="num">
                  Rides
                </th>
                <th scope="col" className="num">
                  Distance
                </th>
                <th scope="col" className="num">
                  Time
                </th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((bike) => (
                <BikeRow key={bike.id} bike={bike} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function BikeRow({ bike }: { bike: BikeWithTotals }) {
  const { units } = useUnits()
  const update = useUpdateBike()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(bike.name)
  const [kind, setKind] = useState<BikeKind | ''>(bike.kind ?? '')

  function save(event: FormEvent) {
    event.preventDefault()
    update.mutate(
      { id: bike.id, patch: { name, kind: kind || null } },
      { onSuccess: () => setEditing(false) },
    )
  }

  if (editing)
    return (
      <tr data-testid="bike-row">
        <td colSpan={6}>
          <form onSubmit={save} className="inline-form" aria-label={`Edit ${bike.name}`}>
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <KindSelect value={kind} onChange={setKind} />
            <button type="submit" disabled={update.isPending}>
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false)
                setName(bike.name)
                setKind(bike.kind ?? '')
                update.reset()
              }}
            >
              Cancel
            </button>
            {update.isError && (
              <p role="alert" data-testid="form-error" className="form-status">
                {update.error.message}
              </p>
            )}
          </form>
        </td>
      </tr>
    )

  return (
    <tr data-testid="bike-row">
      <th scope="row">
        {bike.name}
        {bike.retired && <span className="stat-note"> (retired)</span>}
      </th>
      <td>{bike.kind ? KIND_LABELS[bike.kind] : f.DASH}</td>
      <td className="num">{bike.rides}</td>
      <td className="num">{f.distance(bike.distance_m, units)}</td>
      <td className="num">{f.duration(bike.moving_s)}</td>
      <td className="actions">
        <button type="button" aria-label={`Edit ${bike.name}`} onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          type="button"
          aria-label={`${bike.retired ? 'Bring back' : 'Retire'} ${bike.name}`}
          onClick={() => update.mutate({ id: bike.id, patch: { retired: !bike.retired } })}
        >
          {bike.retired ? 'Bring back' : 'Retire'}
        </button>
      </td>
    </tr>
  )
}

function KindSelect(props: { value: BikeKind | ''; onChange: (kind: BikeKind | '') => void }) {
  return (
    <label>
      Kind
      <select value={props.value} onChange={(e) => props.onChange(e.target.value as BikeKind | '')}>
        <option value="">Not set</option>
        {KINDS.map((kind) => (
          <option key={kind} value={kind}>
            {KIND_LABELS[kind]}
          </option>
        ))}
      </select>
    </label>
  )
}

function AddBike() {
  const add = useAddBike()
  const [name, setName] = useState('')
  const [kind, setKind] = useState<BikeKind | ''>('')

  function submit(event: FormEvent) {
    event.preventDefault()
    add.mutate(
      { name, kind: kind || null },
      {
        onSuccess: () => {
          setName('')
          setKind('')
        },
      },
    )
  }

  return (
    <form onSubmit={submit} className="inline-form" data-testid="add-bike-form">
      <h3>Add a bike</h3>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <KindSelect value={kind} onChange={setKind} />
      <button type="submit" disabled={add.isPending}>
        Add bike
      </button>
      <div aria-live="polite" className="form-status">
        {add.isError && (
          <p role="alert" data-testid="form-error">
            {add.error.message}
          </p>
        )}
        {add.isSuccess && <p data-testid="form-notice">Added {add.data.name}.</p>}
      </div>
    </form>
  )
}

// The dated default bikes: new imports get the bike in effect on their date for their kind
// of ride.
function Defaults() {
  const defaults = useDefaults()
  const bikes = useBikes()
  const set = useSetDefault()
  const remove = useDeleteDefault()
  const [slot, setSlot] = useState<BikeSlot>('outdoor')
  const [from, setFrom] = useState('')
  const [bikeId, setBikeId] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    set.mutate({ slot, from, bikeId: bikeId || null })
  }

  function confirmRemove(entrySlot: BikeSlot, entryFrom: string) {
    if (window.confirm(`Remove the ${SLOT_LABELS[entrySlot]} default from ${entryFrom}?`))
      remove.mutate({ slot: entrySlot, from: entryFrom })
  }

  const active = bikes.data?.filter((b) => !b.retired) ?? []
  return (
    <section aria-labelledby="defaults-heading">
      <h2 id="defaults-heading">Default bikes</h2>
      <p className="hint">
        New rides get the default bike for their kind of ride and date. Older rides can have a
        different bike from newer ones: add an entry for each change.
      </p>
      {defaults.data && defaults.data.length > 0 && (
        <table>
          <caption className="visually-hidden">Default bikes</caption>
          <thead>
            <tr>
              <th scope="col">Rides</th>
              <th scope="col">From</th>
              <th scope="col">Bike</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {defaults.data.map((d) => {
              const label = `${SLOT_LABELS[d.slot]} from ${d.effective_from}`
              return (
                <tr key={`${d.slot}-${d.effective_from}`} data-testid="default-row">
                  <th scope="row">{SLOT_LABELS[d.slot]}</th>
                  <td>{d.effective_from}</td>
                  <td>{d.bike?.name ?? 'No bike'}</td>
                  <td>
                    <button
                      type="button"
                      aria-label={`Remove ${label}`}
                      onClick={() => confirmRemove(d.slot, d.effective_from)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {remove.isError && <p role="alert">{remove.error.message}</p>}
      <form onSubmit={submit} className="inline-form" data-testid="default-form">
        <h3>Set a default</h3>
        <label>
          Rides
          <select value={slot} onChange={(e) => setSlot(e.target.value as BikeSlot)}>
            {SLOTS.map((s) => (
              <option key={s} value={s}>
                {SLOT_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} required />
        </label>
        <label>
          Bike
          <select value={bikeId} onChange={(e) => setBikeId(e.target.value)}>
            <option value="">No bike</option>
            {active.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={set.isPending}>
          Set default
        </button>
        <div aria-live="polite" className="form-status">
          {set.isError && (
            <p role="alert" data-testid="form-error">
              {set.error.message}
            </p>
          )}
        </div>
      </form>
    </section>
  )
}

// Gives existing rides their default bike. Rides whose bike was set by hand are left alone.
function Backfill() {
  const backfill = useBackfill()
  const result = backfill.data
  const total = result?.changes.reduce((sum, c) => sum + c.rides, 0) ?? 0

  return (
    <section aria-labelledby="backfill-heading">
      <h2 id="backfill-heading">Apply defaults to existing rides</h2>
      <p className="hint">
        Gives rides without a bike, or with a default bike, the default for their date. Bikes you
        chose for a ride are never changed.
      </p>
      <div className="button-row">
        <button type="button" onClick={() => backfill.mutate(true)} disabled={backfill.isPending}>
          Preview
        </button>
        <button type="button" onClick={() => backfill.mutate(false)} disabled={backfill.isPending}>
          Apply
        </button>
      </div>
      <div aria-live="polite" data-testid="backfill-result">
        {backfill.isError && <p role="alert">{backfill.error.message}</p>}
        {result && (
          <>
            <p>
              {total === 0
                ? 'Every ride already has its default bike.'
                : `${result.dry_run ? 'Would change' : 'Changed'} ${total} ${total === 1 ? 'ride' : 'rides'}:`}
            </p>
            {total > 0 && (
              <ul>
                {result.changes.map((c) => (
                  <li key={c.bike?.id ?? 'none'}>
                    {c.bike?.name ?? 'No bike'}: {c.rides} {c.rides === 1 ? 'ride' : 'rides'}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </section>
  )
}
