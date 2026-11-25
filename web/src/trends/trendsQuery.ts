// The trends page's range and choices, kept in the URL so links, reloads and the back button
// all work, and the date sums behind them. Dates are the rider's local dates as YYYY-MM-DD.
import type { VolumeBucket } from '../api/client'
import * as f from '../shared/format'

export const PRESETS = [
  { id: '6w', label: '6 weeks', days: 42 },
  { id: '3m', label: '3 months', days: 91 },
  { id: '6m', label: '6 months', days: 183 },
  { id: '1y', label: '1 year', days: 365 },
  { id: 'all', label: 'All', days: null },
] as const
export type Preset = (typeof PRESETS)[number]['id']
export const DEFAULT_PRESET: Preset = '3m'

export const METRICS = [
  { id: 'time', label: 'Time' },
  { id: 'distance', label: 'Distance' },
  { id: 'ascent', label: 'Climbing' },
  { id: 'tss', label: 'TSS' },
  { id: 'rides', label: 'Rides' },
] as const
export type Metric = (typeof METRICS)[number]['id']

// What the best efforts of the range are shown against.
export const AGAINST = [
  { id: 'year', label: 'Past year' },
  { id: 'all', label: 'All time' },
  { id: 'previous', label: 'Previous period' },
] as const
export type Against = (typeof AGAINST)[number]['id']

export type Period = 'week' | 'month'
export type CurveKind = 'power' | 'hr'

export type TrendsState = {
  // A preset, or 'custom' when dates are in the URL.
  range: Preset | 'custom'
  since: string // custom only
  until: string // custom only
  period: Period
  metric: Metric
  curve: CurveKind
  against: Against
}

export type DateRange = { since: string; until: string }

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

const pick = <T extends string>(value: string | null, allowed: readonly T[], fallback: T): T =>
  allowed.includes(value as T) ? (value as T) : fallback

const isDate = (value: string | null): value is string =>
  !!value && ISO_DATE.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`))

export function fromParams(params: URLSearchParams): TrendsState {
  const since = params.get('since')
  const until = params.get('until')
  const custom = isDate(since) || isDate(until)
  return {
    range: custom
      ? 'custom'
      : pick(
          params.get('range'),
          PRESETS.map((p) => p.id),
          DEFAULT_PRESET,
        ),
    since: isDate(since) ? since : '',
    until: isDate(until) ? until : '',
    period: pick(params.get('period'), ['week', 'month'] as const, 'week'),
    metric: pick(
      params.get('metric'),
      METRICS.map((m) => m.id),
      'time',
    ),
    curve: pick(params.get('curve'), ['power', 'hr'] as const, 'power'),
    against: pick(
      params.get('against'),
      AGAINST.map((a) => a.id),
      'year',
    ),
  }
}

// Only what differs from the defaults goes in the URL; dates only for a custom range.
export function toParams(state: TrendsState): URLSearchParams {
  const params = new URLSearchParams()
  if (state.range === 'custom') {
    if (state.since) params.set('since', state.since)
    if (state.until) params.set('until', state.until)
  } else if (state.range !== DEFAULT_PRESET) {
    params.set('range', state.range)
  }
  if (state.period !== 'week') params.set('period', state.period)
  if (state.metric !== 'time') params.set('metric', state.metric)
  if (state.curve !== 'power') params.set('curve', state.curve)
  if (state.against !== 'year') params.set('against', state.against)
  return params
}

// A YYYY-MM-DD date moved by a number of days.
export function addDays(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

// Days from one date to another: 0 for the same day.
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000)
}

// Today on this computer's clock, as YYYY-MM-DD.
export function localToday(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

// The dates a state covers. A preset ends today and counts today as one of its days; "All"
// starts at the first ride (today for an empty library). A custom range left open ends today,
// or starts 90 days before its end.
export function resolveRange(
  state: TrendsState,
  today: string,
  firstRide: string | null,
): DateRange {
  if (state.range === 'custom') {
    const until = state.until || today
    return { since: state.since || addDays(until, -89), until }
  }
  const preset = PRESETS.find((p) => p.id === state.range)!
  if (preset.days === null) {
    const since = firstRide && firstRide < today ? firstRide : today
    return { since, until: today }
  }
  return { since: addDays(today, -(preset.days - 1)), until: today }
}

// The dates the range's best efforts are compared with: the year up to its end, everything
// up to its end, or as many days again just before it.
export function againstRange(
  against: Against,
  range: DateRange,
  firstRide: string | null,
): DateRange {
  if (against === 'year') return { since: addDays(range.until, -364), until: range.until }
  if (against === 'all') {
    const since = firstRide && firstRide < range.until ? firstRide : range.until
    return { since, until: range.until }
  }
  const length = daysBetween(range.since, range.until) + 1
  return { since: addDays(range.since, -length), until: addDays(range.since, -1) }
}

// Each point's average over the points in the `days` days up to and including its own day
// (points in date order).
export function rollingAverage<T extends { day: string }>(
  points: T[],
  value: (point: T) => number,
  days = 28,
): number[] {
  return points.map((point) => {
    const inWindow = points.filter((p) => {
      const back = daysBetween(p.day, point.day)
      return back >= 0 && back < days
    })
    return inWindow.reduce((sum, p) => sum + value(p), 0) / inWindow.length
  })
}

// A week's or month's total for the volume chart, as a number in the display units (hours,
// miles or km, feet or metres), and as text for its table.
export function volumeValue(bucket: VolumeBucket, metric: Metric, units: f.Units): number {
  switch (metric) {
    case 'time':
      return Number((bucket.moving_s / 3600).toFixed(2))
    case 'distance':
      return Number(f.distanceValue(bucket.distance_m, units).toFixed(1))
    case 'ascent':
      return Math.round(f.elevationValue(bucket.ascent_m, units))
    case 'tss':
      return Math.round(bucket.tss)
    case 'rides':
      return bucket.rides
  }
}

// The volume chart's axis name for a metric: "h", "mi", "ft", "TSS", "Rides".
export function volumeUnit(metric: Metric, units: f.Units): string {
  return {
    time: 'h',
    distance: f.distanceUnit(units),
    ascent: f.elevationUnit(units),
    tss: 'TSS',
    rides: 'Rides',
  }[metric]
}

// A week ("Week of 18 Aug") or month ("Aug 2025") as labelled in tables.
export function periodLabel(start: string, period: Period): string {
  return period === 'week' ? `Week of ${f.shortDay(start)} ${start.slice(0, 4)}` : f.month(start)
}
