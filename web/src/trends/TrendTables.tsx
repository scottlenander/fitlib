// The figures behind each trends chart, as tables.
import { Link } from 'react-router'
import type { CurveBest, EfficiencyPoint, FitnessDay, Ftp, Volume } from '../api/trends'
import { ScrollBox } from '../shared/ScrollBox'
import { ShowTable } from '../shared/ShowTable'
import * as f from '../shared/format'
import { useUnits } from '../shared/units'
import { periodLabel, rollingAverage } from './trendsQuery'
import { signed } from './summary'
import { BestCurveChart, Chart } from './lazyCharts'

// Each Sunday and the last day: a row a day would be hundreds of rows for a year.
export function FitnessTable({ days }: { days: FitnessDay[] }) {
  const last = days[days.length - 1]?.day
  const rows = days.filter(
    (d) => new Date(`${d.day}T00:00:00Z`).getUTCDay() === 0 || d.day === last,
  )
  return (
    <ScrollBox label="Fitness, fatigue and form">
      <table data-testid="fitness-table">
        <caption>Fitness, fatigue and form each Sunday and on the last day</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col" className="num">
              TSS that day
            </th>
            <th scope="col" className="num">
              Fitness
            </th>
            <th scope="col" className="num">
              Fatigue
            </th>
            <th scope="col" className="num">
              Form
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.day}>
              <th scope="row">{f.day(d.day)}</th>
              <td className="num">{f.tss(d.tss)}</td>
              <td className="num">{d.fitness.toFixed(0)}</td>
              <td className="num">{d.fatigue.toFixed(0)}</td>
              <td className="num">{signed(d.form)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollBox>
  )
}

export function VolumeTable({ volume }: { volume: Volume }) {
  const { units } = useUnits()
  const withoutTss = volume.buckets.reduce((sum, b) => sum + b.rides_without_tss, 0)
  return (
    <>
      <ScrollBox label="Volume">
        <table className="wide" data-testid="volume-table">
          <caption>Volume by {volume.period}</caption>
          <thead>
            <tr>
              <th scope="col">{volume.period === 'week' ? 'Week' : 'Month'}</th>
              {['Rides', 'Time', 'Distance', 'Climbing', 'Work', 'TSS'].map((c) => (
                <th key={c} scope="col" className="num">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {volume.buckets.map((b) => (
              <tr key={b.start}>
                <th scope="row">{periodLabel(b.start, volume.period)}</th>
                <td className="num">{b.rides}</td>
                <td className="num">{f.duration(b.moving_s)}</td>
                <td className="num">{f.distance(b.distance_m, units)}</td>
                <td className="num">{f.elevation(b.ascent_m, units)}</td>
                <td className="num">{f.kilojoules(b.kj)}</td>
                <td className="num">{f.tss(b.tss)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollBox>
      <WithoutTss count={withoutTss} />
    </>
  )
}

export function FtpTable({ ftp }: { ftp: Ftp }) {
  return (
    <ScrollBox label="FTP">
      <table data-testid="ftp-table">
        <caption>FTP at the end of each {ftp.period}</caption>
        <thead>
          <tr>
            <th scope="col">Up to</th>
            <th scope="col" className="num">
              Set FTP
            </th>
            <th scope="col" className="num">
              Estimated
            </th>
          </tr>
        </thead>
        <tbody>
          {ftp.points.map((p) => (
            <tr key={p.day}>
              <th scope="row">{f.day(p.day)}</th>
              <td className="num">{f.watts(p.ftp)}</td>
              <td className="num">{f.watts(p.estimated)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollBox>
  )
}

// Links to the rides, so it needs no scroll box of its own to be reachable.
export function EfficiencyTable({ points }: { points: EfficiencyPoint[] }) {
  const average = rollingAverage(points, (p) => p.efficiency)
  return (
    <div className="table-scroll">
      <table className="wide" data-testid="efficiency-table">
        <caption>Efficiency of each ride</caption>
        <thead>
          <tr>
            <th scope="col">Ride</th>
            {['NP', 'Heart rate', 'Efficiency', '28-day average', 'Decoupling'].map((c) => (
              <th key={c} scope="col" className="num">
                {c}
              </th>
            ))}
            <th scope="col">Where</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p, i) => (
            <tr key={p.ride_id}>
              <th scope="row">
                <Link to={`/rides/${p.ride_id}`}>{f.day(p.day)}</Link>
              </th>
              <td className="num">{f.watts(p.np)}</td>
              <td className="num">{f.bpm(p.avg_hr)}</td>
              <td className="num">{p.efficiency.toFixed(2)}</td>
              <td className="num">{average[i]!.toFixed(2)}</td>
              <td className="num">{f.signedPercent(p.decoupling_pct)}</td>
              <td>{p.indoor ? 'Indoor' : 'Outdoor'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export type BestProps = { mine: CurveBest[]; theirs: CurveBest[]; names: string[]; unit: string }

export function BestEfforts({ mine, theirs, names, unit }: BestProps) {
  if (mine.length === 0 && theirs.length === 0)
    return (
      <p data-testid="best-empty">
        No {unit === 'W' ? 'power' : 'heart rate'} in this range or the one it's compared with.
      </p>
    )
  const durations = [...new Set([...mine, ...theirs].map((p) => p.duration_s))].sort(
    (a, b) => a - b,
  )
  const format = (value: number | undefined) =>
    value === undefined ? f.DASH : `${value.toFixed(0)} ${unit}`
  return (
    <>
      <Chart>
        <BestCurveChart curves={[mine, theirs]} names={names} unit={unit} />
      </Chart>
      <ShowTable name="Best efforts">
        <div className="table-scroll">
          <table className="wide" data-testid="best-table">
            <caption>Best efforts: {names.join(' against ')}</caption>
            <thead>
              <tr>
                <th scope="col">Best</th>
                <th scope="col" className="num">
                  This range
                </th>
                <th scope="col" className="num">
                  Compared with
                </th>
                <th scope="col" className="num">
                  Difference
                </th>
              </tr>
            </thead>
            <tbody>
              {durations.map((d) => {
                const a = mine.find((p) => p.duration_s === d)
                const b = theirs.find((p) => p.duration_s === d)
                return (
                  <tr key={d}>
                    <th scope="row">{f.shortDuration(d)}</th>
                    <td className="num">
                      {a ? <Link to={`/rides/${a.ride_id}`}>{format(a.value)}</Link> : f.DASH}
                    </td>
                    <td className="num">
                      {b ? <Link to={`/rides/${b.ride_id}`}>{format(b.value)}</Link> : f.DASH}
                    </td>
                    <td className="num">
                      {a && b ? f.signedPercent(((a.value - b.value) / b.value) * 100) : f.DASH}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </ShowTable>
    </>
  )
}

// Rides that add nothing to the TSS figures, said under the chart.
export function WithoutTss({ count }: { count: number }) {
  if (!count) return null
  return (
    <p className="footnote" data-testid="without-tss">
      {count === 1 ? '1 ride has' : `${count} rides have`} no TSS (no power or FTP, and no heart
      rate or threshold heart rate) and count as 0.
    </p>
  )
}
