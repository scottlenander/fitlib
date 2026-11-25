// The library's selection: what's picked across pages, and picking a whole page.
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'
import { rideCount } from './bulkEdit'
import { MAX_RIDES, MIN_RIDES, compareUrl } from '../compare/compare'
import { MAX_SELECTED, type Picked } from './selection'

// What's selected (from any page of the library): compare 2 to 4 rides, or edit them.
type BarProps = {
  picked: Picked[]
  editing: boolean
  onEdit: () => void
  onDelete: () => void
  onClear: () => void
}

export function SelectionBar({ picked, editing, onEdit, onDelete, onClear }: BarProps) {
  const navigate = useNavigate()
  const count = picked.length
  let status = `Tick ${MIN_RIDES} to ${MAX_RIDES} rides to compare them, or any number to edit or delete them together.`
  if (count >= MAX_SELECTED) status = `${MAX_SELECTED} rides is the most you can select at once.`
  else if (count > MAX_RIDES)
    status = `${count} rides selected. Compare takes ${MIN_RIDES} to ${MAX_RIDES}.`
  else if (count > 0) status = `Selected: ${picked.map((p) => p.name).join(', ')}.`
  return (
    <div className="selection-bar" data-testid="selection-bar">
      <p aria-live="polite" data-testid="selection-status">
        {status}
      </p>
      <button
        type="button"
        disabled={count < MIN_RIDES || count > MAX_RIDES}
        onClick={() => void navigate(compareUrl(picked.map((p) => p.id)))}
      >
        Compare ({count})
      </button>
      {count > 0 && (
        <>
          <button type="button" aria-expanded={editing} onClick={onEdit}>
            Edit {rideCount(count)}
          </button>
          <button type="button" onClick={onDelete}>
            Delete {rideCount(count)}
          </button>
          <button type="button" onClick={onClear}>
            Clear selection
          </button>
        </>
      )}
    </div>
  )
}

type PageCheckboxProps = {
  rides: Picked[]
  picked: Picked[]
  onSelect: (rides: Picked[]) => void
  onUnselect: (rides: Picked[]) => void
}

// Selects every ride on this page, or unselects them all; part-ticked when some are.
export function PageCheckbox({ rides, picked, onSelect, onUnselect }: PageCheckboxProps) {
  const ref = useRef<HTMLInputElement>(null)
  const ids = new Set(picked.map((p) => p.id))
  const onPage = rides.filter((r) => ids.has(r.id)).length
  const all = onPage === rides.length
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = onPage > 0 && !all
  }, [onPage, all])
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label="Select all rides on this page"
      checked={all}
      disabled={!all && picked.length >= MAX_SELECTED}
      onChange={() => (all ? onUnselect(rides) : onSelect(rides))}
    />
  )
}
