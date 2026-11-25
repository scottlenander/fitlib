import { useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router'
import { useSimilar, type RideDetail, type SimilarRide } from '../api/client'
import { MAX_RIDES, compareUrl } from '../compare/compare'
import * as f from '../shared/format'
import { TssNotes, TssValue } from '../shared/TssDisplay'
import { useUnits } from '../shared/units'

const RECOMPUTE_HINT = 'Run fitlib recompute to find rides on its route.'

type Kind = 'route' | 'effort'
const TABS: { kind: Kind; label: string }[] = [
  { kind: 'route', label: 'Same route' },
  { kind: 'effort', label: 'Similar efforts' },
]

// Rides on the same roads, and rides with a similar effort, as two tabs.
export function SimilarRides({ ride }: { ride: RideDetail }) {
  const [kind, setKind] = useState<Kind>('route')
  const tabs = useRef<(HTMLButtonElement | null)[]>([])

  // Arrow keys move between tabs, as screen reader users expect.
  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    const index = TABS.findIndex((t) => t.kind === kind)
    const next = (index + (event.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length
    setKind(TABS[next]!.kind)
    tabs.current[next]?.focus()
  }

  return (
    <section aria-labelledby="similar-heading">
      <h2 id="similar-heading">Similar rides</h2>
      <div role="tablist" aria-label="Similar rides" className="tabs" onKeyDown={onKeyDown}>
        {TABS.map((tab, i) => (
          <button
            key={tab.kind}
            ref={(el) => {
              tabs.current[i] = el
            }}
            type="button"
            role="tab"
            id={`similar-tab-${tab.kind}`}
            aria-selected={kind === tab.kind}
            aria-controls="similar-panel"
            tabIndex={kind === tab.kind ? 0 : -1}
            onClick={() => setKind(tab.kind)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="similar-panel" aria-labelledby={`similar-tab-${kind}`}>
        {kind === 'route' ? <RouteMatches ride={ride} /> : <EffortMatches ride={ride} />}
      </div>
    </section>
  )
}

function RouteMatches({ ride }: { ride: RideDetail }) {
  const similar = useSimilar(ride.id, 'route')
  const { units } = useUnits()
  if (similar.isPending) return <p>Looking for rides on this route…</p>
  if (similar.isError) return <p role="alert">Couldn't load similar rides.</p>
  if (!similar.data.has_route)
    return (
      <p data-testid="similar-empty">
        {ride.has_gps
          ? `This ride was imported before routes were recorded. ${RECOMPUTE_HINT}`
          : 'This ride has no GPS positions, so it has no route to match.'}
      </p>
    )
  if (similar.data.items.length === 0)
    return <p data-testid="similar-empty">No other rides share this ride's route.</p>

  // Newest first, so progress on the route reads down the table.
  const items = [...similar.data.items].sort((a, b) => b.ride.start.localeCompare(a.ride.start))
  // The API lists the closest matches first: same route, then most overlap.
  const closest = similar.data.items.slice(0, MAX_RIDES - 1).map((item) => item.ride.id)
  return (
    <>
      <p>
        <Link to={compareUrl([ride.id, ...closest])}>
          {closest.length === 1
            ? 'Compare with this ride'
            : `Compare with the ${closest.length} closest rides`}
        </Link>
      </p>
      <div className="table-scroll">
        <table className="wide">
          <caption className="visually-hidden">Rides on the same route</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Name</th>
              <th scope="col" className="num">
                Time
              </th>
              <th scope="col" className="num">
                Distance
              </th>
              <th scope="col" className="num">
                Avg speed
              </th>
              <th scope="col" className="num">
                Avg power
              </th>
              <th scope="col" className="num">
                Overlap
              </th>
              <th scope="col">Route</th>
              <th scope="col">
                <span className="visually-hidden">Compare</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <RouteRow key={item.ride.id} rideId={ride.id} item={item} units={units} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">
        Overlap: how much of this ride's route the other ride covered. Same route: each covers most
        of the other's.
      </p>
    </>
  )
}

type RouteRowProps = { rideId: string; item: SimilarRide; units: f.Units }

function RouteRow({ rideId, item, units }: RouteRowProps) {
  const r = item.ride
  const speed = r.distance_m !== null && r.moving_s > 0 ? r.distance_m / r.moving_s : null
  return (
    <tr data-testid="similar-row">
      <td>{f.date(r.start, r.local_start)}</td>
      <td>
        <Link to={`/rides/${r.id}`}>{r.name}</Link>
      </td>
      <td className="num">{f.duration(r.moving_s)}</td>
      <td className="num">{f.distance(r.distance_m, units)}</td>
      <td className="num">{f.speed(speed, units)}</td>
      <td className="num">{f.watts(r.avg_power)}</td>
      <td className="num">{Math.round((item.overlap ?? 0) * 100)}%</td>
      <td>{item.same_route ? 'Same' : 'Partly'}</td>
      <td>
        <CompareLink rideId={rideId} other={r} />
      </td>
    </tr>
  )
}

function EffortMatches({ ride }: { ride: RideDetail }) {
  const similar = useSimilar(ride.id, 'effort')
  if (similar.isPending) return <p>Looking for similar efforts…</p>
  if (similar.isError) return <p role="alert">Couldn't load similar rides.</p>
  if (similar.data.items.length === 0)
    return (
      <p data-testid="similar-empty">
        {ride.has_power || ride.has_hr
          ? 'No other rides to compare this effort with yet.'
          : 'This ride has no power or heart rate to compare.'}
      </p>
    )
  return (
    <>
      <div className="table-scroll">
        <table className="wide">
          <caption className="visually-hidden">Rides with a similar effort</caption>
          <thead>
            <tr>
              <th scope="col" className="num">
                Similarity
              </th>
              <th scope="col">Date</th>
              <th scope="col">Name</th>
              <th scope="col" className="num">
                Time
              </th>
              <th scope="col" className="num">
                NP
              </th>
              <th scope="col" className="num">
                TSS
              </th>
              <th scope="col">
                <span className="visually-hidden">Compare</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {similar.data.items.map((item) => (
              <tr key={item.ride.id} data-testid="similar-row">
                <td className="num">{item.similarity}</td>
                <td>{f.date(item.ride.start, item.ride.local_start)}</td>
                <td>
                  <Link to={`/rides/${item.ride.id}`}>{item.ride.name}</Link>
                </td>
                <td className="num">{f.duration(item.ride.moving_s)}</td>
                <td className="num">{f.watts(item.ride.np ?? item.ride.avg_power)}</td>
                <td className="num">
                  <TssValue ride={item.ride} />
                </td>
                <td>
                  <CompareLink rideId={ride.id} other={item.ride} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TssNotes rides={similar.data.items.map((item) => item.ride)} />
      <p className="hint">
        Similarity: 100 is an identical effort, by length, intensity, steadiness and the shape of
        the {ride.has_power ? 'power' : 'heart-rate'} curve.
      </p>
    </>
  )
}

// Opens this ride next to another on the compare page.
function CompareLink({ rideId, other }: { rideId: string; other: SimilarRide['ride'] }) {
  return (
    <Link to={compareUrl([rideId, other.id])} aria-label={`Compare with ${other.name}`}>
      Compare
    </Link>
  )
}
