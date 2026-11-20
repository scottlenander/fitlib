// The compare page: how many rides, smoothing, and its address.

export const MIN_RIDES = 2
export const MAX_RIDES = 4
// Power and heart rate are averaged over this many seconds unless the URL says otherwise.
export const DEFAULT_SMOOTH = 10
export const SMOOTHING = [0, 10, 30] as const

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
