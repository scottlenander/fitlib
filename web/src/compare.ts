// Picking rides to compare, and the compare page's address.
import { useCallback, useState } from 'react'

export const MIN_RIDES = 2
export const MAX_RIDES = 4
// Power and heart rate are averaged over this many seconds unless the URL says otherwise.
export const DEFAULT_SMOOTH = 10
export const SMOOTHING = [0, 10, 30] as const

const STORAGE_KEY = 'fitlib.compare'

// A ride picked in the library: its id, and its name for listing what's picked.
export type Picked = { id: string; name: string }

// Adds a ride, or takes it out if it's already picked. Nothing is added past the limit.
export function toggle(picked: Picked[], ride: Picked): Picked[] {
  if (picked.some((p) => p.id === ride.id)) return picked.filter((p) => p.id !== ride.id)
  return picked.length >= MAX_RIDES ? picked : [...picked, ride]
}

// Ride ids from the URL's `ids` (comma-separated), without blanks or repeats.
export function parseIds(value: string | null): string[] {
  const ids = (value ?? '')
    .split(',')
    .map((id) => id.trim())
    .filter(Boolean)
  return [...new Set(ids)]
}

// The compare page for some rides; the first is the one others are measured against.
export function compareUrl(ids: string[]): string {
  return `/compare?ids=${ids.map(encodeURIComponent).join(',')}`
}

// Reads the picked rides, ignoring anything stored that isn't a list of picks.
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
      .slice(0, MAX_RIDES)
  } catch {
    return []
  }
}

// The rides picked for comparing. Kept for the browser tab (sessionStorage), so picks
// survive paging, filtering and opening a ride, and are gone in a new tab.
export function usePicked() {
  const [picked, setPicked] = useState<Picked[]>(() =>
    readPicked(() => sessionStorage.getItem(STORAGE_KEY)),
  )
  const save = useCallback((next: Picked[]) => {
    setPicked(next)
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // Storage blocked: picks last until the page is left.
    }
  }, [])
  return {
    picked,
    toggle: (ride: Picked) => save(toggle(picked, ride)),
    clear: () => save([]),
  }
}
