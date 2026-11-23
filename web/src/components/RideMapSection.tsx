import { lazy, Suspense } from 'react'
import { Link } from 'react-router'
import { useRideMap, type RideDetail } from '../api/client'
import * as f from '../format'
import { useStreetMap } from '../streetMap'
import { useUnits } from '../units'

// Leaflet loads only when a map is shown.
const RouteMap = lazy(() => import('./RouteMap').then((m) => ({ default: m.RouteMap })))

type Props = {
  ride: RideDetail
  // From Ride Stats: the moment under the pointer and the stretch zoomed to (seconds).
  moment: number | null
  span: [number, number] | null
}

// The ride's route on a map, for rides that recorded positions.
export function RideMapSection({ ride, moment, span }: Props) {
  const { units } = useUnits()
  const [streetMap] = useStreetMap()
  const map = useRideMap(ride.id, ride.has_gps)
  const data = map.data
  const zwift = data?.zwift_world ?? null
  const gap = data?.start_finish_m ?? null
  const apart =
    gap === null
      ? ''
      : gap < 1000
        ? `, starts and finishes ${f.elevation(gap, units)} apart`
        : `, starts and finishes ${f.distance(gap, units)} apart`
  const label = `Route map: ${f.distance(ride.distance_m, units)}${apart}`

  return (
    <section aria-labelledby="map-heading" className="map-section">
      <h2 id="map-heading">Map</h2>
      {map.isError && <p role="alert">Couldn't load the route.</p>}
      {map.isPending && <p>Loading map…</p>}
      {data && data.points.length > 0 && (
        <>
          <Suspense fallback={<p>Loading map…</p>}>
            <RouteMap
              routes={[{ id: ride.id, name: ride.name, points: data.points }]}
              streetMap={streetMap && !zwift}
              label={label}
              cursorT={moment}
              span={span}
              testId="route-map"
            />
          </Suspense>
          <p className="hint" data-testid="map-note">
            {zwift
              ? `Zwift · ${zwift}: Zwift's positions aren't real places, so the route is drawn on a plain background.`
              : streetMap
                ? 'Street map © OpenStreetMap contributors.'
                : 'Drawn without a street map, so nothing is loaded from the internet. '}
            {!zwift && !streetMap && <Link to="/settings">Turn on the street map in Settings</Link>}
          </p>
          <p className="hint">
            Point at Ride Stats to see where you were; zoom it to pick out a stretch.
          </p>
        </>
      )}
    </section>
  )
}
