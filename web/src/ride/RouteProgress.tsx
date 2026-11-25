import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router'
import { useRouteProgress, type RideDetail, type RideItem } from '../api/rides'
import * as f from '../shared/format'
import { TssNotes, TssValue } from '../shared/TssDisplay'
import { useUnits } from '../shared/units'
import { PROGRESS_METRICS, type ProgressMetric } from '../trends/progressMetrics'
import { ShowTable } from '../shared/ShowTable'

// Loaded with ECharts, only when there's a route to show.
const charts = () => import('../trends/TrendCharts')
const ProgressChart = lazy(() => charts().then((m) => ({ default: m.ProgressChart })))

// Every ride on this ride's route, oldest first, to see progress on it. Shown only when at
// least one other ride shares the route. Speed by default: rides on a loop may do different
// numbers of laps, so their times don't compare.
export function RouteProgress({ ride }: { ride: RideDetail }) {
  const progress = useRouteProgress(ride.id)
  const [metric, setMetric] = useState<ProgressMetric>('speed')
  if (!progress.data || progress.data.items.length < 2) return null
  const rides = progress.data.items
  return (
    <section aria-labelledby="progress-heading" data-testid="route-progress">
      <h2 id="progress-heading">Progress on this route</h2>
      <label className="inline-control">
        Show
        <select value={metric} onChange={(e) => setMetric(e.target.value as ProgressMetric)}>
          {PROGRESS_METRICS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <Suspense fallback={<p>Loading chart…</p>}>
        <ProgressChart rides={rides} rideId={ride.id} metric={metric} />
      </Suspense>
      <ShowTable name="Rides on this route">
        <ProgressTable rides={rides} rideId={ride.id} />
      </ShowTable>
    </section>
  )
}

function ProgressTable({ rides, rideId }: { rides: RideItem[]; rideId: string }) {
  const { units } = useUnits()
  return (
    <>
      <div className="table-scroll">
        <table className="wide" data-testid="progress-table">
          <caption>Rides on this route, oldest first</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Name</th>
              {['Time', 'Distance', 'Avg speed', 'Avg power', 'NP', 'Avg HR', 'TSS'].map((c) => (
                <th key={c} scope="col" className="num">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rides.map((r) => {
              const speed =
                r.distance_m !== null && r.moving_s > 0 ? r.distance_m / r.moving_s : null
              const mine = r.id === rideId
              return (
                <tr key={r.id} data-testid="progress-row">
                  <td>{f.date(r.start, r.local_start)}</td>
                  <td>
                    {mine ? (
                      <>
                        {r.name} <span className="muted">(this ride)</span>
                      </>
                    ) : (
                      <Link to={`/rides/${r.id}`}>{r.name}</Link>
                    )}
                  </td>
                  <td className="num">{f.duration(r.moving_s)}</td>
                  <td className="num">{f.distance(r.distance_m, units)}</td>
                  <td className="num">{f.speed(speed, units)}</td>
                  <td className="num">{f.watts(r.avg_power)}</td>
                  <td className="num">{f.watts(r.np)}</td>
                  <td className="num">{f.bpm(r.avg_hr)}</td>
                  <td className="num">
                    <TssValue ride={r} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <TssNotes rides={rides} />
    </>
  )
}
