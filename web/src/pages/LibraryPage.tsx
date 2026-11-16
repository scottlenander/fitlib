import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useRides, type RideItem, type SortKey } from '../api/client'
import * as f from '../format'
import { useUnits } from '../units'
import { usePageTitle } from '../usePageTitle'
import {
  PAGE_SIZES,
  fromParams,
  hasFilters,
  toParams,
  toQuery,
  type LibraryState,
} from './libraryQuery'

const SOURCE_LABELS: Record<string, string> = { zwift: 'Zwift', garmin: 'Garmin', other: 'Other' }

// Sortable columns: the API sorts by start, moving time, distance and average power.
const NUMERIC = new Set(['Time', 'Distance', 'Climbing', 'Avg power', 'NP', 'TSS', 'Avg HR'])

const SORTABLE: Record<string, SortKey> = {
  Date: 'start',
  Time: 'duration',
  Distance: 'distance',
  'Avg power': 'power',
}

export function LibraryPage() {
  usePageTitle('Library')
  const [params, setParams] = useSearchParams()
  const state = fromParams(params)
  const rides = useRides(toQuery(state))
  const { units } = useUnits()

  // The URL state as last set, which may be ahead of this render: two quick changes (such
  // as "Clear filters" then a new filter) must build on each other, not on the same render.
  const latest = useRef(params)
  useEffect(() => {
    latest.current = params
  }, [params])

  // Changing a filter or sort starts again from page 1.
  function update(changes: Partial<LibraryState>, keepPage = false) {
    const next = toParams({
      ...fromParams(latest.current),
      ...changes,
      ...(keepPage ? {} : { page: 1 }),
    })
    latest.current = next
    setParams(next)
  }

  function sortBy(key: SortKey) {
    // A new column starts newest/largest first; the same column flips.
    update({ sort: key, asc: state.sort === key ? !state.asc : false })
  }

  const page = rides.data
  const pages = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1
  const anyEstimated = page?.items.some((r) => r.ftp_estimated && r.tss !== null)

  return (
    <>
      <h1>Library</h1>
      <SearchBox key={state.q} initial={state.q} onSearch={(q) => update({ q })} />
      <Filters state={state} onChange={update} />

      {rides.isError && (
        <p role="alert" data-testid="form-error">
          Couldn't load rides: {rides.error.message}
        </p>
      )}
      {page && (
        <>
          <p data-testid="ride-count" aria-live="polite">
            {page.total === 0
              ? 'No rides found.'
              : `Showing ${page.offset + 1}–${page.offset + page.items.length} of ${page.total} ${page.total === 1 ? 'ride' : 'rides'}`}
          </p>
          {page.total === 0 && !hasFilters(state) && (
            <p>
              Your library is empty. <Link to="/import">Import some rides</Link>.
            </p>
          )}
          {page.items.length > 0 && (
            <div className="table-scroll">
              <table className="wide" data-testid="ride-table">
                <caption className="visually-hidden">Rides</caption>
                <thead>
                  <tr>
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
                    ].map((column) => (
                      <ColumnHeader
                        key={column}
                        name={column}
                        sortKey={SORTABLE[column]}
                        state={state}
                        onSort={sortBy}
                      />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((ride) => (
                    <RideRow key={ride.id} ride={ride} units={units} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {anyEstimated && (
            <p className="footnote">* TSS from an estimated FTP (no FTP set for that date).</p>
          )}
          {page.total > 0 && (
            <nav aria-label="Pages" className="pager">
              <button
                type="button"
                disabled={state.page <= 1}
                onClick={() => update({ page: state.page - 1 }, true)}
              >
                Previous
              </button>
              <span>
                Page {state.page} of {pages}
              </span>
              <button
                type="button"
                disabled={state.page >= pages}
                onClick={() => update({ page: state.page + 1 }, true)}
              >
                Next
              </button>
              <label>
                Rides per page{' '}
                <select
                  value={state.limit}
                  onChange={(e) => update({ limit: Number(e.target.value) })}
                >
                  {[...new Set([...PAGE_SIZES, state.limit])]
                    .sort((a, b) => a - b)
                    .map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                </select>
              </label>
            </nav>
          )}
        </>
      )}
    </>
  )
}

function SearchBox({ initial, onSearch }: { initial: string; onSearch: (q: string) => void }) {
  const [text, setText] = useState(initial)
  function submit(event: FormEvent) {
    event.preventDefault()
    onSearch(text)
  }
  return (
    <form role="search" onSubmit={submit} className="search">
      <label htmlFor="ride-search">Search</label>
      <input
        id="ride-search"
        type="search"
        value={text}
        placeholder="Name, notes, tags, bike or device"
        onChange={(e) => setText(e.target.value)}
      />
      <button type="submit">Search</button>
    </form>
  )
}

type FiltersProps = { state: LibraryState; onChange: (changes: Partial<LibraryState>) => void }

function Filters({ state, onChange }: FiltersProps) {
  return (
    <fieldset className="filters">
      <legend>Filters</legend>
      <label>
        Source
        <select
          value={state.source}
          onChange={(e) => onChange({ source: e.target.value as LibraryState['source'] })}
        >
          <option value="">Any</option>
          <option value="zwift">Zwift</option>
          <option value="garmin">Garmin</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label>
        Where
        <select
          value={state.where}
          onChange={(e) => onChange({ where: e.target.value as LibraryState['where'] })}
        >
          <option value="">Anywhere</option>
          <option value="indoor">Indoor</option>
          <option value="outdoor">Outdoor</option>
        </select>
      </label>
      <label>
        Power
        <select
          value={state.power}
          onChange={(e) => onChange({ power: e.target.value as LibraryState['power'] })}
        >
          <option value="">Any</option>
          <option value="yes">With power</option>
          <option value="no">Without power</option>
        </select>
      </label>
      <label>
        From
        <input
          type="date"
          value={state.since}
          onChange={(e) => onChange({ since: e.target.value })}
        />
      </label>
      <label>
        To
        <input
          type="date"
          value={state.until}
          onChange={(e) => onChange({ until: e.target.value })}
        />
      </label>
      <label>
        At least (minutes)
        <input
          type="number"
          min={0}
          inputMode="numeric"
          value={state.minMinutes}
          onChange={(e) => onChange({ minMinutes: e.target.value })}
        />
      </label>
      <button
        type="button"
        onClick={() =>
          onChange({
            q: '',
            source: '',
            where: '',
            since: '',
            until: '',
            power: '',
            minMinutes: '',
          })
        }
      >
        Clear filters
      </button>
    </fieldset>
  )
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

function RideRow({ ride, units }: { ride: RideItem; units: f.Units }) {
  const estimated = ride.ftp_estimated && ride.tss !== null
  return (
    <tr data-testid="ride-row">
      <td>{f.date(ride.start, ride.local_start)}</td>
      <td>
        <Link to={`/rides/${ride.id}`}>{ride.name}</Link>
      </td>
      <td>
        {SOURCE_LABELS[ride.source] ?? ride.source}
        {ride.indoor && ride.source !== 'zwift' ? ' (indoor)' : ''}
      </td>
      <td className="num">{f.duration(ride.moving_s)}</td>
      <td className="num">{f.distance(ride.distance_m, units)}</td>
      <td className="num">{f.elevation(ride.ascent_m, units)}</td>
      <td className="num">{f.watts(ride.avg_power)}</td>
      <td className="num">{f.watts(ride.np)}</td>
      <td className="num">
        {f.tss(ride.tss)}
        {estimated && <abbr title="TSS from an estimated FTP">*</abbr>}
      </td>
      <td className="num">{f.bpm(ride.avg_hr)}</td>
    </tr>
  )
}
