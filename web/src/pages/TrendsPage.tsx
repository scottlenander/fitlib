import { lazy, Suspense, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import {
  useBestCurve,
  useEfficiency,
  useFitness,
  useFtp,
  useTrendSpan,
  useVolume,
  type CurveBest,
  type EfficiencyPoint,
  type FitnessDay,
  type Ftp,
  type Volume,
} from '../api/client'
import { ScrollBox } from '../components/ScrollBox'
import { ShowTable } from '../components/ShowTable'
import { Stats, type Stat } from '../components/Stats'
import * as f from '../format'
import { useUnits } from '../units'
import { usePageTitle } from '../usePageTitle'
import {
  AGAINST,
  METRICS,
  PRESETS,
  againstRange,
  fromParams,
  localToday,
  periodLabel,
  resolveRange,
  rollingAverage,
  toParams,
  type DateRange,
  type TrendsState,
} from './trendsQuery'

// Charts (and ECharts with them) load only when the page is opened.
const charts = () => import('../components/TrendCharts')
const FitnessChart = lazy(() => charts().then((m) => ({ default: m.FitnessChart })))
const VolumeChart = lazy(() => charts().then((m) => ({ default: m.VolumeChart })))
const FtpChart = lazy(() => charts().then((m) => ({ default: m.FtpChart })))
const EfficiencyChart = lazy(() => charts().then((m) => ({ default: m.EfficiencyChart })))
const BestCurveChart = lazy(() => charts().then((m) => ({ default: m.BestCurveChart })))

// /trends[?range=6w|3m|6m|1y|all | since=…&until=…][&period=month][&metric=…][&curve=hr][&against=…]
export function TrendsPage() {
  usePageTitle('Trends')
  const [params, setParams] = useSearchParams()
  const search = params.toString()
  // The choice just made: the URL updates in a transition, and the controls should follow
  // at once. It only counts until the URL changes (to it, or by going back).
  const [changed, setChanged] = useState<{ from: string; to: TrendsState }>()
  const state = changed?.from === search ? changed.to : fromParams(params)
  const span = useTrendSpan()
  const today = localToday()
  const first = span.data?.first ?? null
  const range = resolveRange(state, today, first)
  const valid = range.since <= range.until
  const ready = span.isSuccess && valid

  function update(changes: Partial<TrendsState>) {
    const next = { ...state, ...changes }
    setChanged({ from: search, to: next })
    setParams(toParams(next))
  }

  return (
    <>
      <h1>Trends</h1>
      <Controls state={state} range={range} onChange={update} />
      {span.isError && <p role="alert">Couldn't load the library: {span.error.message}</p>}
      {!valid && (
        <p role="alert" data-testid="form-error">
          The first day must be on or before the last day.
        </p>
      )}
      {span.isSuccess && first === null && (
        <p data-testid="trends-empty">
          No rides yet. <Link to="/import">Import some</Link> to see trends.
        </p>
      )}
      {ready && first !== null && (
        <Trends state={state} range={range} first={first} onChange={update} />
      )}
    </>
  )
}

type ControlsProps = {
  state: TrendsState
  range: DateRange
  onChange: (changes: Partial<TrendsState>) => void
}

function Controls({ state, range, onChange }: ControlsProps) {
  return (
    <fieldset className="filters trend-controls">
      <legend>Range</legend>
      <div role="radiogroup" aria-label="Range" className="radios">
        {[...PRESETS, { id: 'custom', label: 'Custom' } as const].map((preset) => (
          <label key={preset.id}>
            <input
              type="radio"
              name="range"
              value={preset.id}
              checked={state.range === preset.id}
              onChange={() =>
                onChange(
                  preset.id === 'custom'
                    ? { range: 'custom', since: range.since, until: range.until }
                    : { range: preset.id, since: '', until: '' },
                )
              }
            />
            {preset.label}
          </label>
        ))}
      </div>
      <label>
        From
        <input
          type="date"
          value={range.since}
          required
          onChange={(e) =>
            e.target.value &&
            onChange({ range: 'custom', since: e.target.value, until: range.until })
          }
        />
      </label>
      <label>
        To
        <input
          type="date"
          value={range.until}
          required
          onChange={(e) =>
            e.target.value &&
            onChange({ range: 'custom', since: range.since, until: e.target.value })
          }
        />
      </label>
      <label>
        Group by
        <select
          value={state.period}
          onChange={(e) => onChange({ period: e.target.value as TrendsState['period'] })}
        >
          <option value="week">Week</option>
          <option value="month">Month</option>
        </select>
      </label>
    </fieldset>
  )
}

type TrendsProps = ControlsProps & { first: string }

function Trends({ state, range, first, onChange }: TrendsProps) {
  const fitness = useFitness(range, true)
  const volume = useVolume(range, state.period, true)
  const ftp = useFtp(range, state.period, true)
  const efficiency = useEfficiency(range, true)
  const against = againstRange(state.against, range, first)
  const curve = useBestCurve(range, state.curve, true)
  const againstCurve = useBestCurve(against, state.curve, true)

  const days = fitness.data?.days ?? []
  const last = days[days.length - 1]
  const lastFtp = ftp.data?.points[ftp.data.points.length - 1]
  const summary: Stat[] = [
    { label: 'Fitness', value: last ? last.fitness.toFixed(0) : f.DASH, note: 'CTL' },
    { label: 'Fatigue', value: last ? last.fatigue.toFixed(0) : f.DASH, note: 'ATL' },
    { label: 'Form', value: last ? signed(last.form) : f.DASH, note: 'TSB' },
    { label: 'TSS', value: f.tss(days.reduce((sum, d) => sum + d.tss, 0)), note: 'in range' },
    { label: 'FTP', value: f.watts(lastFtp?.ftp) },
    { label: 'Estimated FTP', value: f.watts(lastFtp?.estimated) },
  ]

  return (
    <>
      <p className="hint" data-testid="trends-range">
        {f.day(range.since)} to {f.day(range.until)}. Fitness, fatigue, form and FTP are as on{' '}
        {f.day(range.until)}.
      </p>
      <Stats stats={summary} testId="trends-summary" />

      <Section id="fitness" title="Fitness and fatigue" query={fitness}>
        {fitness.data && (
          <>
            <p className="hint">
              Fitness is your training load over 42 days, fatigue over 7 days; form is yesterday's
              fitness minus fatigue (below zero: tired, above: fresh).
            </p>
            <Chart>
              <FitnessChart days={days} range={range} />
            </Chart>
            <WithoutTss count={fitness.data.rides_without_tss} />
            <ShowTable name="Fitness, fatigue and form">
              <FitnessTable days={days} />
            </ShowTable>
          </>
        )}
      </Section>

      <Section id="volume" title="Volume" query={volume}>
        {volume.data && (
          <>
            <label className="inline-control">
              Show
              <select
                value={state.metric}
                onChange={(e) => onChange({ metric: e.target.value as TrendsState['metric'] })}
              >
                {METRICS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <Chart>
              <VolumeChart
                buckets={volume.data.buckets}
                metric={state.metric}
                period={state.period}
              />
            </Chart>
            <ShowTable name="Volume">
              <VolumeTable volume={volume.data} />
            </ShowTable>
          </>
        )}
      </Section>

      <Section id="ftp" title="FTP" query={ftp}>
        {ftp.data && (
          <>
            <p className="hint">
              Estimated FTP is 95 % of your best 20 minutes in the six weeks up to each day.
            </p>
            <Chart>
              <FtpChart ftp={ftp.data} />
            </Chart>
            <ShowTable name="FTP">
              <FtpTable ftp={ftp.data} />
            </ShowTable>
          </>
        )}
      </Section>

      <Section id="efficiency" title="Efficiency" query={efficiency}>
        {efficiency.data &&
          (efficiency.data.points.length === 0 ? (
            <p data-testid="efficiency-empty">
              No rides of 20 minutes or more with both power and heart rate in this range.
            </p>
          ) : (
            <>
              <p className="hint">
                Normalized Power per heartbeat a minute, for rides of 20 minutes or more with power
                and heart rate. Higher is more power for the same heart rate. Select a dot to open
                its ride.
              </p>
              <Chart>
                <EfficiencyChart points={efficiency.data.points} range={range} />
              </Chart>
              <ShowTable name="Efficiency">
                <EfficiencyTable points={efficiency.data.points} />
              </ShowTable>
            </>
          ))}
      </Section>

      <Section id="best" title="Best efforts" query={curve}>
        <div className="inline-controls">
          <label className="inline-control">
            Show
            <select
              value={state.curve}
              onChange={(e) => onChange({ curve: e.target.value as TrendsState['curve'] })}
            >
              <option value="power">Power</option>
              <option value="hr">Heart rate</option>
            </select>
          </label>
          <label className="inline-control">
            Against
            <select
              value={state.against}
              onChange={(e) => onChange({ against: e.target.value as TrendsState['against'] })}
            >
              {AGAINST.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {curve.data && againstCurve.data && (
          <BestEfforts
            mine={curve.data.points}
            theirs={againstCurve.data.points}
            names={[
              'This range',
              `${AGAINST.find((a) => a.id === state.against)!.label} (${f.shortDay(against.since)} ${against.since.slice(0, 4)} to ${f.shortDay(against.until)} ${against.until.slice(0, 4)})`,
            ]}
            unit={state.curve === 'power' ? 'W' : 'bpm'}
          />
        )}
      </Section>
    </>
  )
}

const signed = (value: number) => `${value > 0.5 ? '+' : ''}${value.toFixed(0)}`

type SectionProps = {
  id: string
  title: string
  query: { isPending: boolean; isError: boolean; error: Error | null }
  children: ReactNode
}

// A titled part of the page, saying when its figures are loading or couldn't be loaded.
function Section({ id, title, query, children }: SectionProps) {
  return (
    <section aria-labelledby={`${id}-heading`} data-testid={`trends-${id}`}>
      <h2 id={`${id}-heading`}>{title}</h2>
      {query.isPending && <p>Loading…</p>}
      {query.isError && <p role="alert">Couldn't load this: {query.error?.message}</p>}
      {children}
    </section>
  )
}

function Chart({ children }: { children: ReactNode }) {
  return <Suspense fallback={<p>Loading chart…</p>}>{children}</Suspense>
}

function WithoutTss({ count }: { count: number }) {
  if (!count) return null
  return (
    <p className="footnote" data-testid="without-tss">
      {count === 1 ? '1 ride has' : `${count} rides have`} no TSS (no power or FTP, and no heart
      rate or threshold heart rate) and count as 0.
    </p>
  )
}

// Each Sunday and the last day: a row a day would be hundreds of rows for a year.
function FitnessTable({ days }: { days: FitnessDay[] }) {
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

function VolumeTable({ volume }: { volume: Volume }) {
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

function FtpTable({ ftp }: { ftp: Ftp }) {
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
function EfficiencyTable({ points }: { points: EfficiencyPoint[] }) {
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

type BestProps = { mine: CurveBest[]; theirs: CurveBest[]; names: string[]; unit: string }

function BestEfforts({ mine, theirs, names, unit }: BestProps) {
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
