import { useState, type FormEvent } from 'react'
import { useBikes } from '../api/bikes'
import { missingRides } from '../api/client'
import { useBulkEdit, useTags } from '../api/rides'
import { KEEP_ALL, bulkChange, rideCount, type BulkForm } from './bulkEdit'

const EFFORTS = Array.from({ length: 10 }, (_, i) => String(i + 1))

// onMissing: some of the rides are gone (the library unselects them and says so).
type Props = { ids: string[]; onClose: () => void; onMissing: (ids: string[]) => void }

// The library's form for changing the effort, bike and tags of the selected rides at once.
// Name and notes are edited one ride at a time, on the ride's page.
export function BulkEditPanel({ ids, onClose, onMissing }: Props) {
  const bikes = useBikes()
  const tags = useTags()
  const edit = useBulkEdit()
  const [form, setForm] = useState<BulkForm>(KEEP_ALL)
  const change = bulkChange(form)
  const set = (changes: Partial<BulkForm>) => setForm({ ...form, ...changes })

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!change) return
    edit.mutate(
      { ids, ...change },
      {
        onSuccess: () => setForm(KEEP_ALL),
        onError: (error) => {
          const missing = missingRides(error)
          if (missing.length) onMissing(missing)
        },
      },
    )
  }

  return (
    <form
      onSubmit={submit}
      className="inline-form bulk-edit"
      aria-labelledby="bulk-edit-heading"
      data-testid="bulk-edit"
    >
      <h2 id="bulk-edit-heading">Edit {rideCount(ids.length)}</h2>
      <p className="hint">
        Fields left on Keep stay as each ride has them. Tags are added to or taken off each ride,
        keeping its other tags.
      </p>
      <label>
        Effort
        <select value={form.effort} onChange={(e) => set({ effort: e.target.value })}>
          <option value="">Keep</option>
          <option value="clear">No effort</option>
          {EFFORTS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        Bike
        <select value={form.bike} onChange={(e) => set({ bike: e.target.value })}>
          <option value="">Keep</option>
          <option value="none">No bike</option>
          {bikes.data
            ?.filter((b) => !b.retired)
            .map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Add tags
        <input
          type="text"
          list="bulk-tags"
          value={form.add}
          onChange={(e) => set({ add: e.target.value })}
          aria-describedby="bulk-tags-hint"
        />
      </label>
      <label>
        Remove tags
        <input
          type="text"
          list="bulk-tags"
          value={form.remove}
          onChange={(e) => set({ remove: e.target.value })}
          aria-describedby="bulk-tags-hint"
        />
      </label>
      <datalist id="bulk-tags">
        {tags.data?.map((t) => (
          <option key={t.name} value={t.name} />
        ))}
      </datalist>
      <span id="bulk-tags-hint" className="hint">
        Separate tags with commas.
      </span>
      <div className="button-row">
        <button type="submit" disabled={!change || edit.isPending}>
          Apply to {rideCount(ids.length)}
        </button>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <div aria-live="polite" className="form-status">
        {edit.isError && missingRides(edit.error).length === 0 && (
          <p role="alert" data-testid="form-error">
            {edit.error.message}
          </p>
        )}
        {edit.isSuccess && <p data-testid="form-notice">Updated {rideCount(edit.data.updated)}.</p>}
      </div>
    </form>
  )
}
