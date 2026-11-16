// The library's search, filters, sort and page, kept in the URL so links, reloads and the
// back button all work. Turns URL parameters into an API query and back.
import type { RideQuery, SortKey } from '../api/client'

export const PAGE_SIZES = [10, 25, 50, 100]
export const DEFAULT_LIMIT = 25
const SORTS: SortKey[] = ['start', 'duration', 'distance', 'power']

export type LibraryState = {
  q: string
  source: '' | 'zwift' | 'garmin' | 'other'
  where: '' | 'indoor' | 'outdoor'
  since: string // YYYY-MM-DD
  until: string // YYYY-MM-DD, inclusive
  power: '' | 'yes' | 'no'
  minMinutes: string
  sort: SortKey
  asc: boolean
  page: number // from 1
  limit: number
}

const pick = <T extends string>(value: string | null, allowed: readonly T[], fallback: T): T =>
  allowed.includes(value as T) ? (value as T) : fallback

const positive = (value: string | null, fallback: number) => {
  const number = Number(value)
  return Number.isInteger(number) && number > 0 ? number : fallback
}

export function fromParams(params: URLSearchParams): LibraryState {
  return {
    q: params.get('q') ?? '',
    source: pick(params.get('source'), ['', 'zwift', 'garmin', 'other'] as const, ''),
    where: pick(params.get('where'), ['', 'indoor', 'outdoor'] as const, ''),
    since: params.get('since') ?? '',
    until: params.get('until') ?? '',
    power: pick(params.get('power'), ['', 'yes', 'no'] as const, ''),
    minMinutes: params.get('min') ?? '',
    sort: pick(params.get('sort'), SORTS, 'start'),
    asc: params.get('dir') === 'asc',
    page: positive(params.get('page'), 1),
    limit: Math.min(positive(params.get('limit'), DEFAULT_LIMIT), 200),
  }
}

// Only what differs from the defaults goes in the URL.
export function toParams(state: LibraryState): URLSearchParams {
  const params = new URLSearchParams()
  const set = (key: string, value: string, unless = '') => {
    if (value !== unless) params.set(key, value)
  }
  set('q', state.q.trim())
  set('source', state.source)
  set('where', state.where)
  set('since', state.since)
  set('until', state.until)
  set('power', state.power)
  set('min', state.minMinutes)
  set('sort', state.sort, 'start')
  set('dir', state.asc ? 'asc' : 'desc', 'desc')
  set('page', String(state.page), '1')
  set('limit', String(state.limit), String(DEFAULT_LIMIT))
  return params
}

// The day after a YYYY-MM-DD date, so "until" includes the whole day.
function nextDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + 1)
  return date.toISOString().slice(0, 10)
}

export function toQuery(state: LibraryState): RideQuery {
  const minutes = Number(state.minMinutes)
  return {
    q: state.q.trim() || undefined,
    source: state.source || undefined,
    indoor: state.where ? state.where === 'indoor' : undefined,
    since: state.since || undefined,
    until: state.until ? nextDay(state.until) : undefined,
    has_power: state.power ? state.power === 'yes' : undefined,
    min_duration_s: state.minMinutes && minutes > 0 ? Math.round(minutes * 60) : undefined,
    sort: state.sort,
    desc: !state.asc,
    offset: (state.page - 1) * state.limit,
    limit: state.limit,
  }
}

export function hasFilters(state: LibraryState): boolean {
  return (
    Boolean(state.q || state.source || state.where || state.since || state.until || state.power) ||
    Boolean(state.minMinutes)
  )
}
