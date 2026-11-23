import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router'
import {
  useBikes,
  useHealth,
  useRides,
  useTags,
  useZwiftWorlds,
  type RideItem,
  type SortKey,
} from '../api/client'
import { missingText, rideCount } from '../bulkEdit'
import { BulkEdit } from '../components/BulkEdit'
import { ConfirmDelete } from '../components/ConfirmDelete'
import type { DeletedState } from '../components/RideDetails'
import { TssNotes, TssValue } from '../components/Tss'
import { MAX_RIDES, MIN_RIDES, compareUrl } from '../compare'
import * as f from '../format'
import { useUnits } from '../units'
import { MAX_SELECTED, usePicked, type Picked } from '../selection'
import { usePageTitle } from '../usePageTitle'
import {
  NO_FILTERS,
  PAGE_SIZES,
  fromParams,
  hasFilters,
  toParams,
  toQuery,
  withSource,
  withWorld,
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
  const health = useHealth()
  const { units } = useUnits()
  const outdated = health.data?.outdated_rides ?? 0
  const selection = usePicked()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // "Deleted …": from a ride's page (navigation state) or from the selection bar.
  // Read once, then cleared from the history entry, so a reload or Back doesn't say it again.
  const location = useLocation()
  const navigate = useNavigate()
  const [fromRide] = useState(() => (location.state as DeletedState | null)?.deleted)
  useEffect(() => {
    if ((location.state as DeletedState | null)?.deleted)
      void navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
  }, [location, navigate])
  const [deletedHere, setDeletedHere] = useState<string | null>(null)
  const [missingNotice, setMissingNotice] = useState<string | null>(null)
  const deletedNotice = deletedHere ?? (fromRide ? `Deleted ${fromRide}.` : null)

  // Selected rides that turned out to be gone (deleted in another tab or the command line).
  function dropMissing(ids: string[]) {
    const gone = new Set(ids)
    selection.unselectAll(selection.picked.filter((p) => gone.has(p.id)))
    setMissingNotice(missingText(ids.length))
  }

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

  return (
    <>
      <h1>Library</h1>
      {outdated > 0 && (
        <p className="notice" data-testid="outdated-notice">
          {outdated} {outdated === 1 ? 'ride was' : 'rides were'} computed with older calculations.
          Run <code>fitlib recompute</code> to bring {outdated === 1 ? 'it' : 'them'} up to date.
        </p>
      )}
      <div aria-live="polite">
        {deletedNotice && (
          <p className="notice" data-testid="deleted-notice">
            {deletedNotice}
          </p>
        )}
        {missingNotice && (
          <p className="notice" data-testid="missing-notice">
            {missingNotice}
          </p>
        )}
      </div>
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
          {page.total > 0 && (
            <SelectionBar
              picked={selection.picked}
              editing={editing}
              onEdit={() => setEditing(!editing)}
              onDelete={() => setDeleting(true)}
              onClear={selection.clear}
            />
          )}
          {deleting && selection.picked.length > 0 && (
            <ConfirmDelete
              rides={selection.picked}
              onCancel={() => setDeleting(false)}
              onMissing={dropMissing}
              onDeleted={(count) => {
                selection.unselectAll(selection.picked)
                setDeleting(false)
                setEditing(false)
                setDeletedHere(`Deleted ${rideCount(count)}.`)
              }}
            />
          )}
          {editing && selection.picked.length > 0 && (
            <BulkEdit
              ids={selection.picked.map((p) => p.id)}
              onClose={() => setEditing(false)}
              onMissing={dropMissing}
            />
          )}
          {page.items.length > 0 && (
            <div className="table-scroll">
              <table className="wide" data-testid="ride-table">
                <caption className="visually-hidden">Rides</caption>
                <thead>
                  <tr>
                    <th scope="col">
                      <PageCheckbox
                        rides={page.items.map((r) => ({ id: r.id, name: r.name }))}
                        picked={selection.picked}
                        onSelect={selection.selectAll}
                        onUnselect={selection.unselectAll}
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
                        onSort={sortBy}
                      />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((ride) => (
                    <RideRow
                      key={ride.id}
                      ride={ride}
                      units={units}
                      picked={selection.picked}
                      onPick={selection.toggle}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <TssNotes rides={page.items} />
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

// What's selected (from any page of the library): compare 2 to 4 rides, or edit them.
type BarProps = {
  picked: Picked[]
  editing: boolean
  onEdit: () => void
  onDelete: () => void
  onClear: () => void
}

function SelectionBar({ picked, editing, onEdit, onDelete, onClear }: BarProps) {
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
function PageCheckbox({ rides, picked, onSelect, onUnselect }: PageCheckboxProps) {
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

const EFFORTS = Array.from({ length: 10 }, (_, i) => String(i + 1))

function Filters({ state, onChange }: FiltersProps) {
  const tags = useTags()
  const bikes = useBikes()
  const worlds = useZwiftWorlds()
  return (
    <fieldset className="filters">
      <legend>Filters</legend>
      <label>
        Source
        <select
          value={state.source}
          onChange={(e) => onChange(withSource(e.target.value as LibraryState['source']))}
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
      <label>
        Tag
        <select value={state.tag} onChange={(e) => onChange({ tag: e.target.value })}>
          <option value="">Any</option>
          {tags.data?.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
          {/* A tag from the URL that no ride has any more. */}
          {state.tag && !tags.data?.some((t) => t.name === state.tag) && (
            <option value={state.tag}>{state.tag}</option>
          )}
        </select>
      </label>
      <label>
        Bike
        <select value={state.bike} onChange={(e) => onChange({ bike: e.target.value })}>
          <option value="">Any</option>
          <option value="none">No bike</option>
          {bikes.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Effort from
        <select value={state.minRpe} onChange={(e) => onChange({ minRpe: e.target.value })}>
          <option value="">Any</option>
          {EFFORTS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        Effort to
        <select value={state.maxRpe} onChange={(e) => onChange({ maxRpe: e.target.value })}>
          <option value="">Any</option>
          {EFFORTS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <label>
        World
        <select value={state.world} onChange={(e) => onChange(withWorld(state, e.target.value))}>
          <option value="">Any</option>
          {worlds.data?.map((w) => (
            <option key={w.slug} value={w.slug}>
              {w.name}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={() => onChange(NO_FILTERS)}>
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
