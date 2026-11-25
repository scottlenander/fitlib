import type { ReactNode } from 'react'
import { Link } from 'react-router'
import {
  useBestCurve,
  useEfficiency,
  useFitness,
  useFtp,
  useTrendSpan,
  useVolume,
} from '../api/trends'
import { usePageTitle } from '../app/usePageTitle'
import { ShowTable } from '../shared/ShowTable'
import { Stats } from '../shared/Stats'
import * as f from '../shared/format'
import { Chart, EfficiencyChart, FitnessChart, FtpChart, VolumeChart } from './lazyCharts'
import { trendSummary } from './summary'
import { Controls } from './TrendControls'
import {
  AGAINST,
  METRICS,
  againstRange,
  localToday,
  resolveRange,
  type DateRange,
  type TrendsState,
} from './trendsQuery'
import {
  BestEfforts,
  EfficiencyTable,
  FitnessTable,
  FtpTable,
  VolumeTable,
  WithoutTss,
} from './TrendTables'
import { useTrendsParams } from './useTrendsParams'

// /trends[?range=6w|3m|6m|1y|all | since=…&until=…][&period=month][&metric=…][&curve=hr][&against=…]
export function TrendsPage() {
  usePageTitle('Trends')
  const { state, update } = useTrendsParams()
  const span = useTrendSpan()
  const today = localToday()
  const first = span.data?.first ?? null
  const range = resolveRange(state, today, first)
  const valid = range.since <= range.until
  const ready = span.isSuccess && valid

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

type TrendsProps = {
  state: TrendsState
  range: DateRange
  first: string
  onChange: (changes: Partial<TrendsState>) => void
}

function Trends({ state, range, first, onChange }: TrendsProps) {
  const fitness = useFitness(range, true)
  const volume = useVolume(range, state.period, true)
  const ftp = useFtp(range, state.period, true)
  const efficiency = useEfficiency(range, true)
  const against = againstRange(state.against, range, first)
  const curve = useBestCurve(range, state.curve, true)
  const againstCurve = useBestCurve(against, state.curve, true)

  const days = fitness.data?.days ?? []
  const summary = trendSummary(days, ftp.data?.points ?? [])

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
