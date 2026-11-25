import { lazy, Suspense } from 'react'
import type { ComparedRide } from '../api/compare'
import { useRideMaps, type RideMap } from '../api/rides'
import { useStreetMap } from './streetMap'
import type { MapRoute } from './RouteMap'

const RouteMap = lazy(() => import('./RouteMap').then((m) => ({ default: m.RouteMap })))

// Where a route's positions are: a Zwift world (made-up coordinates), or real places.
function place(map: RideMap): string {
  return map.zwift_world ?? 'real'
}

// The compared rides' routes on one map, each in its ride's colour. Only rides in the same
// place as the first one with a route can share a map (Zwift worlds aren't real places);
// the others are listed.
export function CompareMap({ rides }: { rides: ComparedRide[] }) {
  const [streetMap] = useStreetMap()
  const maps = useRideMaps(rides.map((r) => r.ride.id))
  if (maps.some((m) => m.isPending)) return null
  const mapped = rides.flatMap(({ ride }, index) => {
    const data = maps[index]?.data
    return data && data.points.length > 0 ? [{ ride, index, data }] : []
  })
  const first = mapped[0]
  if (!first) return null
  const here = place(first.data)
  const shown = mapped.filter((m) => place(m.data) === here)
  const elsewhere = mapped.filter((m) => place(m.data) !== here)
  const without = rides.filter(({ ride }) => !mapped.some((m) => m.ride.id === ride.id))
  const routes: MapRoute[] = shown.map((m) => ({
    id: m.ride.id,
    name: m.ride.name,
    points: m.data.points,
    colour: m.index,
  }))
  const zwift = here === 'real' ? null : here

  return (
    <section aria-labelledby="map-heading">
      <h2 id="map-heading">Map</h2>
      <Suspense fallback={<p>Loading map…</p>}>
        <RouteMap
          routes={routes}
          streetMap={streetMap && !zwift}
          label={`Routes of ${shown.map((m) => m.ride.name).join(', ')}`}
          testId="compare-map"
        />
      </Suspense>
      <p className="hint" data-testid="compare-map-note">
        {zwift ? `Zwift · ${zwift}: drawn on a plain background. ` : ''}
        {elsewhere.length > 0 &&
          `Not on this map (somewhere else): ${elsewhere.map((m) => m.ride.name).join(', ')}. `}
        {without.length > 0 &&
          `No positions recorded: ${without.map(({ ride }) => ride.name).join(', ')}.`}
      </p>
    </section>
  )
}
