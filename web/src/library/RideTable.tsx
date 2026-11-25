// The library's table of rides (sortable column headers, one row per ride) and its pager.
import { Link } from 'react-router'
import type { RideItem, SortKey } from '../api/rides'
import { TssValue } from '../shared/TssDisplay'
import * as f from '../shared/format'
import { MAX_SELECTED, type Picked } from './selection'
import { PAGE_SIZES, type LibraryState } from './libraryQuery'
import { PageCheckbox } from './SelectionBar'

const SOURCE_LABELS: Record<string, string> = {
  zwift: 'Zwift',
  garmin: 'Garmin',
  other: 'Other',
}

// Sortable columns: the API sorts by start, moving time, distance and average power.
const NUMERIC = new Set(['Time', 'Distance', 'Climbing', 'Avg power', 'NP', 'TSS', 'Avg HR'])

const SORTABLE: Record<string, SortKey> = {
  Date: 'start',
  Time: 'duration',
  Distance: 'distance',
  'Avg power': 'power',
}

type HeaderProps = {
  name: string
  sortKey: SortKey | undefined
  state: LibraryState
  onSort: (key: SortKey) => void
}

function ColumnHeader({ name, sortKey, state, onSort }: HeaderProps) {
  const className = NUMERIC.has(name) ? 'num' : undefined
  if (!sortKey)
    return (
      <th scope="col" className={className}>
        {name}
      </th>
    )
  const active = state.sort === sortKey
  const direction = active ? (state.asc ? 'ascending' : 'descending') : 'none'
  return (
    <th scope="col" className={className} aria-sort={direction}>
      <button type="button" className="sort-button" onClick={() => onSort(sortKey)}>
        {name}
        <span aria-hidden="true">{active ? (state.asc ? ' ▲' : ' ▼') : ''}</span>
      </button>
    </th>
  )
}

type RowProps = {
  ride: RideItem
  units: f.Units
  picked: Picked[]
  onPick: (ride: Picked) => void
}

function RideRow({ ride, units, picked, onPick }: RowProps) {
  const checked = picked.some((p) => p.id === ride.id)
  return (
    <tr data-testid="ride-row">
      <td>
        <input
          type="checkbox"
          aria-label={`Select ${ride.name}`}
          checked={checked}
          disabled={!checked && picked.length >= MAX_SELECTED}
          onChange={() => onPick({ id: ride.id, name: ride.name })}
        />
      </td>
      <td>
        {f.date(ride.start, ride.local_start)}
        {ride.time_zone_source === 'none' && (
          <>
            {' '}
            <abbr title="No time zone known: the date is in UTC">UTC</abbr>
          </>
        )}
      </td>
      <td>
        <Link to={`/rides/${ride.id}`}>{ride.name}</Link>
      </td>
      <td>
        {SOURCE_LABELS[ride.source] ?? ride.source}
        {ride.zwift_world ? ` (${ride.zwift_world})` : ''}
        {ride.indoor && ride.source !== 'zwift' ? ' (indoor)' : ''}
      </td>
      <td className="num">{f.duration(ride.moving_s)}</td>
      <td className="num">{f.distance(ride.distance_m, units)}</td>
      <td className="num">{f.elevation(ride.ascent_m, units)}</td>
      <td className="num">{f.watts(ride.avg_power)}</td>
      <td className="num">{f.watts(ride.np)}</td>
      <td className="num">
        <TssValue ride={ride} />
      </td>
      <td className="num">{f.bpm(ride.avg_hr)}</td>
      <td>{ride.bike?.name ?? f.DASH}</td>
      <td>{ride.tags.join(', ') || f.DASH}</td>
    </tr>
  )
}

type TableProps = {
  rides: RideItem[]
  state: LibraryState
  units: f.Units
  picked: Picked[]
  onSort: (key: SortKey) => void
  onPick: (ride: Picked) => void
  onSelect: (rides: Picked[]) => void
  onUnselect: (rides: Picked[]) => void
}

// One page of rides, each with a box to pick it, and a box in the header for the page.
export function RideTable({
  rides,
  state,
  units,
  picked,
  onSort,
  onPick,
  onSelect,
  onUnselect,
}: TableProps) {
  return (
    <div className="table-scroll">
      <table className="wide" data-testid="ride-table">
        <caption className="visually-hidden">Rides</caption>
        <thead>
          <tr>
            <th scope="col">
              <PageCheckbox
                rides={rides.map((r) => ({ id: r.id, name: r.name }))}
                picked={picked}
                onSelect={onSelect}
                onUnselect={onUnselect}
              />
            </th>
            {[
              'Date',
              'Name',
              'Source',
              'Time',
              'Distance',
              'Climbing',
              'Avg power',
              'NP',
              'TSS',
              'Avg HR',
              'Bike',
              'Tags',
            ].map((column) => (
              <ColumnHeader
                key={column}
                name={column}
                sortKey={SORTABLE[column]}
                state={state}
                onSort={onSort}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {rides.map((ride) => (
            <RideRow key={ride.id} ride={ride} units={units} picked={picked} onPick={onPick} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

type PagerProps = {
  page: number
  pages: number
  limit: number
  onPage: (page: number) => void
  onLimit: (limit: number) => void
}

// Previous and next page, where we are, and how many rides a page shows.
export function Pager({ page, pages, limit, onPage, onLimit }: PagerProps) {
  return (
    <nav aria-label="Pages" className="pager">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {pages}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </button>
      <label>
        Rides per page{' '}
        <select value={limit} onChange={(e) => onLimit(Number(e.target.value))}>
          {[...new Set([...PAGE_SIZES, limit])]
            .sort((a, b) => a - b)
            .map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
        </select>
      </label>
    </nav>
  )
}
