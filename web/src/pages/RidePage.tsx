import { lazy, Suspense } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError, useRide, type RideDetail } from '../api/client'
import { RideDetails } from '../components/RideDetails'
import { Stats, type Stat } from '../components/Stats'
import { ZoneTable } from '../components/ZoneTable'
import * as f from '../format'
import { useUnits } from '../units'
import { usePageTitle } from '../usePageTitle'

// Charts (and ECharts with them) load only when a ride is opened.
const TraceChart = lazy(() =>
  import('../components/TraceChart').then((m) => ({ default: m.TraceChart })),
)
const BestEfforts = lazy(() =>
  import('../components/CurveChart').then((m) => ({ default: m.BestEfforts })),
)

const SOURCE_LABELS: Record<string, string> = { zwift: 'Zwift', garmin: 'Garmin', other: 'Other' }

export function RidePage() {
  const { id = '' } = useParams()
  const ride = useRide(id)
  usePageTitle(ride.data?.name ?? (ride.isError ? 'Ride not found' : 'Ride'))

  if (ride.isPending) return <p>Loading ride…</p>
  if (ride.isError) {
    const notFound = ride.error instanceof ApiError && ride.error.status === 404
    return (
      <>
        <h1>{notFound ? 'Ride not found' : "Couldn't load this ride"}</h1>
        <p role="alert">{ride.error.message}</p>
        <p>
          <Link to="/">Back to the library</Link>
        </p>
      </>
    )
  }
  return <Ride ride={ride.data} />
}

function Ride({ ride }: { ride: RideDetail }) {
  const { units } = useUnits()
  const t = ride.training
  const where = ride.indoor ? 'Indoor' : 'Outdoor'

  const summary: Stat[] = [
    { label: 'Moving time', value: f.duration(ride.moving_s) },
    { label: 'Elapsed time', value: f.duration(ride.elapsed_s) },
    { label: 'Distance', value: f.distance(ride.distance_m, units) },
    { label: 'Climbing', value: f.elevation(ride.ascent_m, units) },
    { label: 'Avg speed', value: f.speed(ride.avg_speed_mps, units) },
    { label: 'Max speed', value: f.speed(ride.max_speed_mps, units) },
    ...(ride.has_power
      ? [
          { label: 'Avg power', value: f.watts(ride.avg_power) },
          { label: 'Max power', value: f.watts(ride.max_power) },
          { label: 'NP', value: f.watts(ride.np) },
          { label: 'Work', value: f.kilojoules(ride.kj) },
        ]
      : []),
    ...(ride.has_hr
      ? [
          { label: 'Avg heart rate', value: f.bpm(ride.avg_hr) },
          { label: 'Max heart rate', value: f.bpm(ride.max_hr) },
        ]
      : []),
    ...(ride.avg_cadence !== null ? [{ label: 'Cadence', value: f.rpm(ride.avg_cadence) }] : []),
  ]

  const training: Stat[] = [
    // FTP-based figures only mean something for rides with power.
    ...(ride.has_power && t.ftp !== null
      ? [
          {
            label: 'FTP',
            value: f.watts(t.ftp),
            note: t.ftp_estimated ? '(estimated)' : undefined,
          },
        ]
      : []),
    ...(ride.has_power
      ? [
          { label: 'IF', value: f.ratio(t.intensity_factor) },
          { label: 'TSS', value: f.tss(t.tss) },
          { label: 'VI', value: f.ratio(ride.vi) },
        ]
      : []),
    ...(t.watts_per_kg !== null ? [{ label: 'W/kg', value: f.wattsPerKg(t.watts_per_kg) }] : []),
    ...(ride.decoupling_pct !== null
      ? [{ label: 'Decoupling', value: f.signedPercent(ride.decoupling_pct) }]
      : []),
  ]

  return (
    <article className="ride">
      <header>
        <h1>{ride.name}</h1>
        <p className="subtitle" data-testid="ride-subtitle">
          {f.startTime(ride.start, ride.local_start)} · {SOURCE_LABELS[ride.source]} ·{' '}
          {ride.device ?? 'Unknown device'} · {where}
        </p>
      </header>

      <section aria-labelledby="summary-heading">
        <h2 id="summary-heading">Summary</h2>
        <Stats stats={summary} testId="summary-stats" />
      </section>

      {training.length > 0 && (
        <section aria-labelledby="training-heading">
          <h2 id="training-heading">Training</h2>
          <Stats stats={training} testId="training-stats" />
        </section>
      )}

      <RideDetails ride={ride} />

      <section aria-labelledby="traces-heading">
        <h2 id="traces-heading">Over the ride</h2>
        <Suspense fallback={<p>Loading chart…</p>}>
          <TraceChart
            rideId={ride.id}
            elapsedS={ride.elapsed_s}
            hasPower={ride.has_power}
            hasHr={ride.has_hr}
          />
        </Suspense>
      </section>

      {(ride.power_zones || ride.hr_zones) && (
        <section aria-labelledby="zones-heading" className="zones-section">
          <h2 id="zones-heading">Zones</h2>
          {ride.power_zones && <ZoneTable title="Power zones" zones={ride.power_zones} />}
          {ride.hr_zones && <ZoneTable title="Heart-rate zones" zones={ride.hr_zones} />}
        </section>
      )}

      {(ride.power_curve.length > 0 || ride.hr_curve.length > 0) && (
        <section aria-labelledby="efforts-heading">
          <h2 id="efforts-heading">Best efforts</h2>
          <Suspense fallback={<p>Loading chart…</p>}>
            <BestEfforts power={ride.power_curve} hr={ride.hr_curve} />
          </Suspense>
        </section>
      )}

      {ride.laps.length > 1 && (
        <section aria-labelledby="laps-heading">
          <h2 id="laps-heading">Laps</h2>
          <div className="table-scroll">
            <table data-testid="laps-table">
              <caption className="visually-hidden">Laps</caption>
              <thead>
                <tr>
                  <th scope="col">Lap</th>
                  <th scope="col" className="num">
                    Start
                  </th>
                  <th scope="col" className="num">
                    Time
                  </th>
                  <th scope="col" className="num">
                    Distance
                  </th>
                  <th scope="col" className="num">
                    Avg power
                  </th>
                  <th scope="col" className="num">
                    Max power
                  </th>
                  <th scope="col" className="num">
                    Avg HR
                  </th>
                  <th scope="col" className="num">
                    Max HR
                  </th>
                </tr>
              </thead>
              <tbody>
                {ride.laps.map((lap) => (
                  <tr key={lap.index}>
                    <th scope="row">{lap.index + 1}</th>
                    <td className="num">{f.duration(lap.start_offset_s)}</td>
                    <td className="num">{f.duration(lap.elapsed_s)}</td>
                    <td className="num">{f.distance(lap.distance_m, units)}</td>
                    <td className="num">{f.watts(lap.avg_power)}</td>
                    <td className="num">{f.watts(lap.max_power)}</td>
                    <td className="num">{f.bpm(lap.avg_hr)}</td>
                    <td className="num">{f.bpm(lap.max_hr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </article>
  )
}
