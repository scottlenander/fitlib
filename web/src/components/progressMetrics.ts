// What the route progress chart can show, and each ride's figure for it. Kept apart from the
// charts so the ride page can offer the choice without loading ECharts.
import type { RideItem } from '../api/client'
import * as f from '../format'

export const PROGRESS_METRICS = [
  { id: 'speed', label: 'Avg speed' },
  { id: 'power', label: 'Avg power' },
  { id: 'hr', label: 'Avg heart rate' },
  { id: 'time', label: 'Moving time' },
] as const
export type ProgressMetric = (typeof PROGRESS_METRICS)[number]['id']

// A ride's figure for the route progress chart, in display units, or null without one.
export function progressValue(ride: RideItem, metric: ProgressMetric, units: f.Units) {
  switch (metric) {
    case 'speed':
      return ride.distance_m && ride.moving_s
        ? Number(f.speedValue(ride.distance_m / ride.moving_s, units).toFixed(1))
        : null
    case 'power':
      return ride.avg_power === null ? null : Math.round(ride.avg_power)
    case 'hr':
      return ride.avg_hr === null ? null : Math.round(ride.avg_hr)
    case 'time':
      return Number((ride.moving_s / 60).toFixed(1))
  }
}
