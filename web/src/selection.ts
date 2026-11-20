// Rides selected in the library, to compare (2 to 4 of them) or to edit together.
import { useCallback, useState } from 'react'

// The most rides that can be selected (and edited) at once; the API takes as many.
export const MAX_SELECTED = 500

const STORAGE_KEY = 'fitlib.selection'

// A selected ride: its id, and its name for listing what's selected.
export type Picked = { id: string; name: string }

// Adds a ride, or takes it out if it's already selected. Nothing is added past the limit.
export function toggle(picked: Picked[], ride: Picked): Picked[] {
  if (picked.some((p) => p.id === ride.id)) return picked.filter((p) => p.id !== ride.id)
  return picked.length >= MAX_SELECTED ? picked : [...picked, ride]
}

// Adds the rides not yet selected, in order, up to the limit.
export function selectAll(picked: Picked[], rides: Picked[]): Picked[] {
  const have = new Set(picked.map((p) => p.id))
  const added = rides.filter((r) => !have.has(r.id))
  return [...picked, ...added].slice(0, MAX_SELECTED)
}

// Takes these rides out of the selection.
export function unselectAll(picked: Picked[], rides: Picked[]): Picked[] {
  const drop = new Set(rides.map((r) => r.id))
  return picked.filter((p) => !drop.has(p.id))
}

// Reads the selected rides, ignoring anything stored that isn't a list of picks.
export function readPicked(read: () => string | null): Picked[] {
  try {
    const parsed: unknown = JSON.parse(read() ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(
        (p): p is Picked =>
          typeof p === 'object' &&
          p !== null &&
          typeof (p as Picked).id === 'string' &&
          typeof (p as Picked).name === 'string',
      )
      .slice(0, MAX_SELECTED)
  } catch {
    return []
  }
}

// The selected rides. Kept for the browser tab (sessionStorage), so the selection
// survives paging, filtering and opening a ride, and is gone in a new tab.
export function usePicked() {
  const [picked, setPicked] = useState<Picked[]>(() =>
    readPicked(() => sessionStorage.getItem(STORAGE_KEY)),
  )
  const save = useCallback((next: Picked[]) => {
    setPicked(next)
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // Storage blocked: the selection lasts until the page is left.
    }
  }, [])
  return {
    picked,
    toggle: (ride: Picked) => save(toggle(picked, ride)),
    selectAll: (rides: Picked[]) => save(selectAll(picked, rides)),
    unselectAll: (rides: Picked[]) => save(unselectAll(picked, rides)),
    clear: () => save([]),
  }
}
