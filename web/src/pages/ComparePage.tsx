import { lazy, Suspense, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useCompare, type Align, type ComparedRide, type Comparison } from '../api/client'
import { ScrollBox } from '../components/ScrollBox'
import { Swatch } from '../components/Swatch'
import { DEFAULT_SMOOTH, MAX_RIDES, MIN_RIDES, SMOOTHING, parseIds } from '../compare'
import { tssNotes, tssText } from '../tss'
import * as f from '../format'
import { useUnits } from '../units'
import { usePageTitle } from '../usePageTitle'

// Charts (and ECharts with them) load only when rides are compared.
const CompareCharts = lazy(() =>
  import('../components/CompareCharts').then((m) => ({ default: m.CompareCharts })),
)

// /compare?ids=a,b[,c,d][&align=time|distance][&smooth=0|10|30]
export function ComparePage() {
  usePageTitle('Compare rides')
  const [params, setParams] = useSearchParams()
  const ids = parseIds(params.get('ids'))
  const alignParam = params.get('align')
  const align: Align | undefined =
    alignParam === 'time' || alignParam === 'distance' ? alignParam : undefined
  const smoothParam = Number(params.get('smooth') ?? DEFAULT_SMOOTH)
  const smooth = (SMOOTHING as readonly number[]).includes(smoothParam)
    ? smoothParam
    : DEFAULT_SMOOTH
  // The choice just clicked: the URL updates in a transition, and the radio button should
  // follow the click at once. It only counts until the URL changes (to it, or by going back).
  const [clicked, setClicked] = useState<{ from: string | null; by: Align }>()
  const pending = clicked?.from === alignParam ? clicked.by : undefined
  const enough = ids.length >= MIN_RIDES && ids.length <= MAX_RIDES
  const comparison = useCompare(ids, align, smooth, enough)

  function change(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) next.set(key, value)
    setParams(next)
  }

  function remove(index: number) {
    const kept = ids.filter((_, i) => i !== index)
    const next = new URLSearchParams(params)
    next.set('ids', kept.join(','))
    setParams(next)
  }

  if (!enough)
    return (
      <>
        <h1>Compare rides</h1>
        <p data-testid="compare-empty">
          {ids.length > MAX_RIDES
            ? `You can compare up to ${MAX_RIDES} rides at once. `
            : `Pick at least ${MIN_RIDES} rides to compare: `}
          tick them in the <Link to="/">library</Link>, or use Compare under a ride's Similar rides.
        </p>
      </>
    )

  return (
    <>
      <h1>Compare rides</h1>
      {comparison.isError && (
        <p role="alert" data-testid="form-error">
          Couldn't compare these rides: {comparison.error.message}
        </p>
      )}
      {comparison.isPending && <p>Lining the rides up…</p>}
      {comparison.data && (
        <Compared
          comparison={comparison.data}
          align={pending ?? align ?? comparison.data.align}
          onRemove={remove}
          onAlign={(by) => {
            setClicked({ from: alignParam, by })
            change({ align: by })
          }}
          smooth={smooth}
          onSmooth={(seconds) => change({ smooth: String(seconds) })}
        />
      )}
    </>
  )
}

type ComparedProps = {
  comparison: Comparison
  // The choice shown: the one asked for, before the rides lined up that way arrive.
  align: Align
  onRemove: (index: number) => void
  onAlign: (by: Align) => void
  smooth: number
  onSmooth: (seconds: number) => void
}

function Compared({ comparison, align, onRemove, onAlign, smooth, onSmooth }: ComparedProps) {
  const rides = comparison.rides
  const first = rides[0]!.ride
  return (
    <>
      <ol className="compare-rides" aria-label="Rides compared">
        {rides.map(({ ride }, index) => (
          <li key={ride.id} data-testid="compare-ride">
            <Swatch index={index} />
            <Link to={`/rides/${ride.id}`}>{ride.name}</Link>{' '}
            <span className="muted">{f.date(ride.start, ride.local_start)}</span>
            <button
              type="button"
              aria-label={`Remove ${ride.name}`}
              onClick={() => onRemove(index)}
            >
              Remove
            </button>
          </li>
        ))}
      </ol>

      <fieldset className="filters">
        <legend>View</legend>
        <div role="radiogroup" aria-label="Line up by" className="radios">
          <span aria-hidden="true">Line up by</span>
          {(['distance', 'time'] as const).map((by) => (
            <label key={by}>
              <input
                type="radio"
                name="align"
                value={by}
                checked={align === by}
                disabled={by === 'distance' && !comparison.can_align_distance}
                onChange={() => onAlign(by)}
              />
              {by === 'distance' ? 'Distance' : 'Time'}
            </label>
          ))}
        </div>
        <label>
          Smoothing
          <select value={smooth} onChange={(e) => onSmooth(Number(e.target.value))}>
            {SMOOTHING.map((s) => (
              <option key={s} value={s}>
                {s === 0 ? 'Off' : `${s} s`}
              </option>
            ))}
          </select>
        </label>
      </fieldset>
      {!comparison.can_align_distance && (
        <p className="hint">
          Lined up by time: not every ride recorded distance, so they can't be lined up by it.
        </p>
      )}
      {comparison.align === 'distance' && (
        <p className="hint">
          Lined up by distance, so the same point on a route sits at the same place in each chart.
          Gaps are measured against {first.name}.
        </p>
      )}

      <section aria-labelledby="figures-heading">
        <h2 id="figures-heading">Figures</h2>
        <CompareTable rides={rides} />
      </section>

      <Suspense fallback={<p>Loading charts…</p>}>
        <CompareCharts comparison={comparison} />
      </Suspense>
    </>
  )
}

// One column per ride, one row per figure: the numbers behind the charts.
function CompareTable({ rides }: { rides: ComparedRide[] }) {
  const { units } = useUnits()
  const list = rides.map((r) => r.ride)
  const best = (seconds: number) =>
    list.map((r) => f.watts(r.power_curve.find((p) => p.duration_s === seconds)?.value))
  const notes = tssNotes(list.map((r) => r.training))
  const rows: [string, string[]][] = [
    ['Date', list.map((r) => f.date(r.start, r.local_start))],
    ['Moving time', list.map((r) => f.duration(r.moving_s))],
    ['Distance', list.map((r) => f.distance(r.distance_m, units))],
    ['Climbing', list.map((r) => f.elevation(r.ascent_m, units))],
    ['Avg speed', list.map((r) => f.speed(r.avg_speed_mps, units))],
    ['Avg power', list.map((r) => f.watts(r.avg_power))],
    ['NP', list.map((r) => f.watts(r.np))],
    ['IF', list.map((r) => f.ratio(r.training.intensity_factor))],
    ['TSS', list.map((r) => tssText(r.training, f.tss))],
    ['Avg HR', list.map((r) => f.bpm(r.avg_hr))],
    ['Decoupling', list.map((r) => f.signedPercent(r.decoupling_pct))],
    ['Best 1 min', best(60)],
    ['Best 5 min', best(300)],
    ['Best 20 min', best(1200)],
  ]
  return (
    <>
      <ScrollBox label="Compared figures">
        <table className="wide" data-testid="compare-table">
          <caption className="visually-hidden">Compared figures</caption>
          <thead>
            <tr>
              <td />
              {list.map((ride, index) => (
                <th key={ride.id} scope="col" className="num">
                  <Swatch index={index} /> {ride.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, values]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {values.map((value, i) => (
                  <td key={list[i]!.id} className="num">
                    {value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollBox>
      {notes.map((note) => (
        <p key={note} className="footnote">
          {note}
        </p>
      ))}
    </>
  )
}
