// Finding moments of a ride on its simplified route, for the map.
import type { MapPoint } from './api/client'

// The position at a moment: between the two points around it, in proportion.
export function positionAt(points: MapPoint[], t: number): [number, number] | null {
  const first = points[0]
  const last = points[points.length - 1]
  if (!first || !last || t < first.t || t > last.t) return null
  let lo = 0
  let hi = points.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if ((points[mid]?.t ?? 0) <= t) lo = mid
    else hi = mid
  }
  const a = points[lo]
  const b = points[hi]
  if (!a || !b) return null
  const share = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t)
  return [a.lat + (b.lat - a.lat) * share, a.lon + (b.lon - a.lon) * share]
}

// The stretch of a route between two moments, with its ends placed exactly.
export function stretch(points: MapPoint[], from: number, to: number): [number, number][] {
  const start = positionAt(points, from)
  const end = positionAt(points, to)
  const inside = points
    .filter((p) => p.t > from && p.t < to)
    .map((p) => [p.lat, p.lon] as [number, number])
  return [...(start ? [start] : []), ...inside, ...(end ? [end] : [])]
}
